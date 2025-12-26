from collections import defaultdict
from dataclasses import dataclass
import logging
import subprocess
import threading
import time
from typing import Hashable, TypeVar

from dasbus.error import DBusError

from bear.bear import Bear, DebugView, bears, dbus_method
from bear.eww import EwwJSONView
from bear.notifications import NotificationCtl, NotificationUrgency
from bear.poke import DBusObjectsProvider, MultiProxyPoke, Poke, ProxyPoke
from bear.utils import dbus_error
from dataclasses_json import dataclass_json

BLUEZ_DEVICE_INTERFACE = "org.bluez.Device1"
BLUEZ_SERVICE_NAME = "org.bluez"

BLUEZ_ADAPTER_INTERFACE = "org.bluez.Adapter1"

logger = logging.getLogger(__name__)


K = TypeVar("K")


@dataclass_json
@dataclass
class Device:
    address: str
    alias: str
    connected: bool
    paired: bool
    services_resolved: bool
    trusted: bool


class BluetoothDevicesPoke(MultiProxyPoke):
    devices = DBusObjectsProvider(
        service_name=BLUEZ_SERVICE_NAME,
        interface_name=BLUEZ_DEVICE_INTERFACE,
        use_session_bus=False,
    )

    property_names = [
        "address",
        "alias",
        "connected",
        "paired",
        "services_resolved",
        "trusted",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.availability_events = defaultdict(threading.Event)

    def create_subpoke(self, obj_path: str) -> ProxyPoke:
        logger.info(f"New device {obj_path} registered as subpoke")
        poke = ProxyPoke(
            service_name=BLUEZ_SERVICE_NAME,
            interface_name=BLUEZ_DEVICE_INTERFACE,
            use_session_bus=False,
            obj_path=obj_path,
            property_names=self.property_names,
            data_class=Device,
        )

        return poke

    def add_subpoke(self, key, *args):
        super().add_subpoke(key, *args)
        self.availability_events[key].set()

    def remove_subpoke(self, key) -> Poke:
        poke = super().remove_subpoke(key)
        self.availability_events[key].clear()
        return poke

    def get_subpoke_from_address(self, address):
        try:
            return next(
                poke for poke in self.poke_map.values() if poke.data.address == address
            )
        except StopIteration:
            raise NoSuchDevice(address)

    def wait_for_device(self, address, adapter_obj_path, timeout):

        obj_path = device_path(adapter_obj_path, address)

        success = self.availability_events[obj_path].wait(timeout)

        if not success:
            raise NoSuchDevice(address)

    @property
    def connected_devices(self):
        return [dev for dev in self.all_devices if dev.connected]

    @property
    def paired_devices(self):
        return [dev for dev in self.all_devices if dev.paired]

    @property
    def all_devices(self):
        return [poke.data for poke in self.poke_map.values()]


class BluetoothAdapterPoke(MultiProxyPoke):
    provider = DBusObjectsProvider(
        service_name=BLUEZ_SERVICE_NAME,
        interface_name=BLUEZ_ADAPTER_INTERFACE,
        use_session_bus=False,
    )

    property_names = ["powered", "discovering", "power_state"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter_enabled = threading.Event()

    def poke(self):
        # check the power state of the adapter. it has to be 'on', not
        # 'off-enabling', 'off' or 'on-disabling' before the adapter is useable

        if self.data and self.data["power_state"] == "on":
            logger.debug("adaper power state set to on.")
            self.adapter_enabled.set()
        else:
            self.adapter_enabled.clear()

        super().poke()

    def wait_for_adapter(self, timeout):
        """
        Wait for the bluetooth adapter to be fully powered (PowerStatus=on,
        not any of the others))
        """
        success = self.adapter_enabled.wait(timeout=timeout)

        if not success:
            raise AdapterNotResponsive()

    @property
    def obj_path(self):
        # warning: this assumes only one adapter is ever present!
        assert (
            len(self.poke_map) == 1
        ), "More than 1 bluetooth adapter not currently supported"

        return next(iter(self.poke_map))

    def create_subpoke(self, key: Hashable, *args) -> Poke:
        return ProxyPoke(
            service_name=BLUEZ_SERVICE_NAME,
            interface_name=BLUEZ_ADAPTER_INTERFACE,
            use_session_bus=False,
            obj_path=key,
            property_names=self.property_names,
        )


@bears.recruit
class BluetoothBear(Bear):
    busy = False

    name = "bluetooth"
    adapter = BluetoothAdapterPoke()
    devices = BluetoothDevicesPoke()

    debug = DebugView()

    eww = EwwJSONView(var_name="bluetooth_devices")

    notifications: NotificationCtl

    def build_context(self):

        message = ""

        if self.adapter.data and self.adapter.data.get("powered", False):
            if self.busy:
                status = "connecting"
                message = "..."
            elif self.devices.connected_devices:
                status = "connected"
            elif self.adapter.data["discovering"]:
                status = "discovering"
                message = "scan"
            else:
                status = "enabled"

        else:
            message = "off"
            status = "disconnected"

        return {
            "status": status,
            "message": message,
            "primary": (
                self.devices.connected_devices[0]
                if self.devices.connected_devices and not self.busy
                else None
            ),
        }

    def set_busy(self, busy):
        self.busy = busy
        self.update()

    def register(self):
        super().register()

        self.notifications = NotificationCtl(self.session_bus)

    def show_error(self, exc):
        self.notifications.notify_and_close(
            title="Bluetooth Error",
            msg=getattr(exc, "message", "Unknown error, check logs."),
            urgency=NotificationUrgency.critical,
        )

    @dbus_method(str)
    def toggle_connect(self, address: str):
        threading.Thread(target=lambda: self._toggle_connect(address)).start()

    def _toggle_connect(self, address: str):
        self.set_busy(True)

        try:
            self._ensure_bluetooth_enabled()

            self.devices.wait_for_device(address, self.adapter.obj_path, 2)

            subpoke = self.devices.get_subpoke_from_address(address)
            device_proxy = subpoke.proxy
            if subpoke.data.connected:
                logger.info(f"disconnecting {address}")
                device_proxy.Disconnect()
            else:
                logger.info(f"connecting {address}")
                device_proxy.Connect()

        except (AdapterNotResponsive, NoSuchDevice, BluezFailed) as e:
            logger.error(e.message)
            self.show_error(e)
            return

        except BluezNotReady as e:
            logger.warning("Bluez is not ready. Did it work anyway?")

        except Exception as e:
            msg = getattr(e, "message", str(e))
            logger.critical(f"Unknown error when (dis)connecting: {msg}", exc_info=e)
            self.show_error(e)

        finally:
            self.set_busy(False)

    @dbus_method()
    def ensure_bluetooth_enabled(self):
        threading.Thread(target=self._ensure_bluetooth_enabled).start()

    def _ensure_bluetooth_enabled(self):

        if not is_bluetooth_enabled():
            logger.info("Bluetooth was not enabled, enabling")
            enable_bluetooth()

            self.adapter.wait_for_adapter(timeout=5)

            logger.info("Bluetooth successfully enabled")

        elif not self.adapter.poke_map:
            logger.warning(
                "Bluetooth looks enabled but no controller was found. "
                "Attempting percussive maintenance..."
            )

            self.percussive_maintenance()

            logger.info("Percussive maintenance done. Did it work?")

            try:
                self.adapter.wait_for_adapter(timeout=5)
            except AdapterNotResponsive:
                raise NoController(
                    f"Bluetooth looks enabled but no controller was found and "
                    "modprobe percussive maintenance didn't fix that."
                )

            logger.info(
                "Bluetooth successfully enabled after applying "
                "percussive maintenance! Neato."
            )

        else:
            logger.debug("Bluetooth was enabled, not doing anything.")

    def percussive_maintenance(self):
        rmmod_result = subprocess.run(
            ["sudo", "rmmod", "btusb"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if rmmod_result.returncode is not 0:
            raise NoController(
                f"Bluetooth looks enabled but no controller was found and "
                f"rmmod failed with stderr '{rmmod_result.stderr}' "
                f"and stdout '{rmmod_result.stdout}'"
            )

        modprobe_result = subprocess.run(
            ["sudo", "modprobe", "btusb"], stdout=subprocess.PIPE
        )

        if modprobe_result.returncode is not 0:
            raise NoController(
                f"Bluetooth looks enabled but no controller was found and "
                f"rmmod failed with stderr '{modprobe_result.stderr}' "
                f"and stdout '{modprobe_result.stdout}'"
            )


def parse_bluetooth_cmd(output) -> bool:
    status = output.strip().split("=")[-1].strip()

    assert status in ["on", "off (software)"]

    return status == "on"


def enable_bluetooth():
    output = subprocess.run(["bluetooth", "on"], stdout=subprocess.PIPE).stdout.decode()

    if not parse_bluetooth_cmd(output):
        raise Exception(f"Could not parse output of bluetooth command, was '{output}'")


def is_bluetooth_enabled() -> bool:
    output = subprocess.run(["bluetooth"], stdout=subprocess.PIPE).stdout.decode()

    return parse_bluetooth_cmd(output)


def device_path(adapter_path, addr):
    addr_s = "_".join(addr.split(":"))

    return f"{adapter_path}/dev_{addr_s}"


class NoSuchDevice(Exception):
    address: str

    def __init__(self, address):
        super().__init__()
        self.address = address

    @property
    def message(self):
        return f"No device with address {self.address} found among paired devices."


class AdapterNotResponsive(Exception):
    message = "The bluetooth adapter seems unresponsive"


class NoController(Exception):
    def __init__(self, message):
        super().__init__()
        self.message = message


# generated with claude.ai
BLUEZ_BR_ERRORS = {
    "br-connection-unknown": "Unknown connection failure, general catch-all error",
    "br-connection-profile-unavailable": "The required Bluetooth profile (like A2DP for audio) is not available or failed to load",
    "br-connection-adapter-not-powered": "The Bluetooth adapter is not powered on",
    "br-connection-refused": "Connection was refused by the remote device. Is it connected to something else?",
    "br-connection-page-timeout": "Page timeout occurred (device didn't respond in time)",
    "br-connection-create-socket": "Failed to create the connection socket",
    "br-connection-invalid-arguments": "Invalid arguments provided for the connection",
    "br-connection-not-supported": "Connection type not supported",
    "br-connection-already-connected": "Device is already connected",
    "br-connection-bad-socket": "Socket is in a bad state",
    "br-connection-memory-alloc": "Memory allocation failed",
    "br-connection-busy": "Resource is busy",
    "br-connection-timeout": "Connection attempt timed out",
    "br-connection-sync-connect-limit": "Synchronous connection limit reached",
    "br-connection-term-by-remote": "Connection terminated by remote device",
    "br-connection-term-by-local": "Connection terminated by local host",
    "br-connection-proto-error": "Protocol error occurred",
}


@dbus_error("org.bluez.Error.Failed")
class BluezFailed(DBusError):

    @property
    def message(self):
        (error_id,) = self.args
        return BLUEZ_BR_ERRORS.get(error_id, "Unknown error?! Check logs.")


@dbus_error("org.bluez.Error.NotReady")
class BluezNotReady(DBusError):

    @property
    def message(self):
        (error_id,) = self.args
        return BLUEZ_BR_ERRORS.get(error_id, f"Unknown error {error_id}")
