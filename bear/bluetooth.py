import logging
import sys
import threading
import time

from dasbus.error import DBusError, ErrorMapper, get_error_decorator
# from gi.repository import GObject
from pipewire_python.controller import Controller as PipewireController

from bear.bear import LabelBear, dbus_method
from bear.exceptions import InProgress, UnknownObject
from bear.utils import HiddenPrints
from bear.views import BlockState

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

logger = logging.getLogger()


DEVICE_INTERFACE = "org.bluez.Device1"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
BLUEZ_DBUS_NAME = "org.bluez"
ADAPTER_PATH = "/org/bluez/hci0"


class DasBusBluetoothDevice:
    def __init__(self, mac_address, bus):
        self.bus = bus
        self.mac_address = mac_address
        self.device = self.bus.get_proxy(
            BLUEZ_DBUS_NAME, self._as_object_name(mac_address)
        )

        self._sink_index = None

        self.pipewire = PipewireController()

    def _as_object_name(self, mac_address: str):
        return f"/org/bluez/hci0/dev_{mac_address.replace(':', '_')}"

    @property
    def object_path(self):
        return self._as_object_name(self.mac_address)

    @property
    def sink_name(self):
        return f"bluez_sink.{self.mac_address.replace(':', '_')}.a2dp_sink"

    def get_info(self):
        return dict(self.device.GetAll(DEVICE_INTERFACE))

    @property
    def alias(self):
        return self.device.Get(DEVICE_INTERFACE, "Alias").get_string()

    def check_connection(self):
        return self.device.Get(DEVICE_INTERFACE, "Connected").get_boolean()

    def ensure_trusted(self):
        self.device.Trusted = True
        # self.device.Set(DEVICE_INTERFACE, "Trusted", True)

    def check_sink(self):

        with HiddenPrints():
            devs = self.pipewire.get_list_interfaces(
                type_interfaces="Device",
                filtered_by_type=True,
            )

        bluetooth_device_macs = [
            d["properties"]["device.string"]
            for d in devs.values()
            if d["properties"]["device.bus"] == "bluetooth"
        ]

        return any(mac == self.mac_address for mac in bluetooth_device_macs)

    def connect(self):
        self.device.Connect()

    def connect_audio(self):
        self.connect()

    def disconnect(self):
        self.device.Disconnect()

    def pair(self):
        self.device.Pair()

    def register_property_listener(self, listener):
        self.device.PropertiesChanged.connect(listener)


class BluezAdapter:
    def __init__(self, bus):
        self.bus = bus
        self.adapter = self.bus.get_proxy(BLUEZ_DBUS_NAME, ADAPTER_PATH)

    def remove(self, dev):
        self.adapter.RemoveDevice(dev.object_path)

    def start_scan(self):
        self.adapter.StartDiscovery()

    def stop_scan(self):
        self.adapter.StopDiscovery()


class PipewirePollThread(threading.Thread):
    def __init__(self, device, success_handler, fail_handler, tries=3, interval=0.1):
        super().__init__()
        self.device = device
        self.success_handler = success_handler
        self.fail_handler = fail_handler
        self.tries = tries
        self.interval = interval

    def run(self):
        logger.info("Started polling for sink add")
        n = 0
        while self.tries > n:
            if self.device.check_sink():
                logger.info(f"Found sink after {n + 1} tries")
                self.success_handler()
                return

            n += 1
            time.sleep(self.interval)

        self.fail_handler()


class NoSinkAdded(Exception):
    pass


class BluetoothBear(LabelBear):
    def __init__(self, service, device, adapter, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.service = service
        self.device = device

        self.adapter = adapter

        self.bluetooth_connected = False
        self.sink_added = False

        self.pipewire_poll_thread = None

    def register(self):
        super().register()
        try:
            self.device.get_info()
        except UnknownObject:
            logger.error("Device seems to not be paired")

        self.device.register_property_listener(self.on_bluetooth_property_change)

    def show_fully_connected(self):
        self.view.update(self.device.alias, "headphones", BlockState.good)

    def show_half_connected(self):
        self.view.update(self.device.alias, "bluetooth", BlockState.warning)

    def show_disconnected(self):
        self.view.update("", "bluetooth", BlockState.idle)

    def show_error(self, msg="err"):
        self.view.update(msg, "bluetooth", BlockState.error)

    def on_bluetooth_property_change(self, name, changed_props, _):
        try:
            is_connected = changed_props["Connected"]
            logger.info(f"Connected changed to {is_connected}")
        except KeyError:
            return

        if is_connected:
            self.bluetooth_connected = True
            if self.sink_added:
                logger.info("Immediately found sink")
                self.show_fully_connected()
            else:
                self.show_half_connected()
                self.poll_for_sink()

        else:
            self.bluetooth_connected = False
            self.show_disconnected()

    def poll_for_sink(self):
        if not self.pipewire_poll_thread:
            self.pipewire_poll_thread = PipewirePollThread(
                self.device, self.on_sink_added, self.on_sink_failed
            )
            self.pipewire_poll_thread.start()

    def on_sink_added(self):
        self.pipewire_poll_thread = None
        self.show_fully_connected()

    def on_sink_failed(self):
        logger.error("Could not find sink")
        self.pipewire_poll_thread = None
        self.show_half_connected()

    def initialize_view(self):
        try:
            if self.device.check_connection():
                self.bluetooth_connected = True
                if self.device.check_sink():
                    self.sink_added = True
                    self.show_fully_connected()
                else:
                    self.show_half_connected()
            else:
                self.show_disconnected()
        except UnknownObject:
            self.show_error("not found?")
        except Exception as e:
            logger.exception(e)
            self.show_error()

    @dbus_method()
    def connect(self):
        if self.device.check_connection():
            logger.info("Already connected.")
            return

        self.view.update("...", "bluetooth", BlockState.warning)
        try:
            self.device.connect()
        except DBusError as e:
            logger.exception(e)
            self.show_error()

    @dbus_method()
    def disconnect(self):
        self.view.update("...", "bluetooth", BlockState.warning)
        self.device.disconnect()

    @dbus_method()
    def toggle(self):
        if self.device.check_connection():
            self.disconnect()
        else:
            self.connect()

    @dbus_method()
    def repair(self):
        try:
            if self.device.check_connection():
                self.disconnect()
            self.adapter.remove(self.device)
            logger.info(f"Removed device {self.device.mac_address}")
        except UnknownObject:
            pass
        except DBusError as e:
            logger.exception(e)

        try:
            self.adapter.start_scan()
            logger.info("Started scanning")
        except InProgress:
            logger.info("Already scanning...")
        except DBusError as e:
            logger.exception(e)

        for i in range(1, 21):

            time.sleep(3)

            if i > 3:
                self.view.update(
                    f"is device peering? ({i})", "bluetooth", BlockState.error
                )
            else:

                self.view.update(f"repairing ({i})", "bluetooth", BlockState.warning)

            try:
                new_dev = DasBusBluetoothDevice(
                    self.device.mac_address, self.device.bus
                )
                logger.info(f"Looking for {self.device.mac_address}... ({i})")
                new_dev.get_info()
                self.device = new_dev
                break
            except UnknownObject:
                continue
            except DBusError as e:
                logger.exception(e)

        else:
            self.view.update("Repair failed", "bluetooth", BlockState.error)
            logger.error("Unable to find device after {i} tries... Aborting.")
            return

        logger.info("Re-pairing with device")
        self.device.pair()
        logger.info("Reconnecting to device")
        self.device.connect()
        logger.info("Retrusting device")
        self.device.ensure_trusted()
        logger.info("Stopping scan")
        self.adapter.stop_scan()
