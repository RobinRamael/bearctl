from abc import abstractmethod
from dataclasses import dataclass
import logging
from typing import Any, List, Tuple, TypeVar

from dataclasses_json import dataclass_json

from bear.bear import Bear, DebugView, bears, dbus_method
from bear.eww import EwwJSONView
from bear.poke import (
    DBusMixin,
    DBusObjectsProvider,
    MultiPoke,
    MultiProxyPoke,
    OBJ_MANAGER_INTERFACE,
    Provider,
    ProxyPoke,
)

BLUEZ_DEVICE_INTERFACE = "org.bluez.Device1"
BLUEZ_SERVICE_NAME = "org.bluez"

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

    def create_subpoke(self, obj_path: str, *args) -> ProxyPoke:
        poke = ProxyPoke(
            service_name=BLUEZ_SERVICE_NAME,
            interface_name=BLUEZ_DEVICE_INTERFACE,
            use_session_bus=False,
            obj_path=obj_path,
            property_names=self.property_names,
            data_class=Device,
        )

        return poke

    def get_subpoke_from_address(self, address):
        try:
            return next(
                poke for poke in self.poke_map.values() if poke.data.address == address
            )
        except StopIteration:
            raise Exception(f"No device with address {address} found.")

    @property
    def connected_devices(self):
        return [dev for dev in self.all_devices if dev.connected]

    @property
    def paired_devices(self):
        return [dev for dev in self.all_devices if dev.paired]

    @property
    def all_devices(self):
        return [poke.data for poke in self.poke_map.values()]


class BluetoothAdapterPoke(ProxyPoke):
    service_name = "org.bluez"
    interface_name = "org.bluez.Adapter1"
    use_session_bus = False

    def get_proxy(self):
        # sometimes the adapter has addres hci0, sometimes hci1, not sure why
        # that happens but we can check which one it is right now with the bluez
        # object manager:
        object_manager = self.bus.get_proxy(
            service_name=self.service_name,
            object_path="/",
            interface_name=OBJ_MANAGER_INTERFACE,
        )
        for obj_path, interfaces in object_manager.GetManagedObjects().items():
            if self.interface_name in interfaces:
                logger.info(f"Using bluetooth adapter {obj_path}")
                return self.bus.get_proxy(self.service_name, obj_path)

        raise Exception("No bluetooth adapter found.")


@bears.recruit
class BluetoothBear(Bear):
    name = "bluetooth"
    adapter = BluetoothAdapterPoke(property_names=["powered", "discovering"])
    devices = BluetoothDevicesPoke()

    debug = DebugView()

    eww = EwwJSONView(var_name="bluetooth_devices")

    def build_context(self):
        if not self.adapter.data["powered"]:
            status = "error"
        elif self.devices.connected_devices:
            status = "connected"
        elif self.adapter.data["discovering"]:
            status = "discovering"
        else:
            status = "disconnected"

        return {
            "status": status,
            "primary": self.devices.connected_devices[0]
            if self.devices.connected_devices
            else None,
        }

    @dbus_method(str)
    def toggle_connect(self, address: str):
        subpoke = self.devices.get_subpoke_from_address(address)
        device_proxy = subpoke.proxy

        if subpoke.data.connected:
            logger.info(f"disconnecting {address}")
            device_proxy.Disconnect()
        else:
            logger.info(f"connecting {address}")
            device_proxy.Connect()
