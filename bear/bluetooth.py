from abc import abstractmethod
from dataclasses import dataclass
import logging
from typing import Any, List, Tuple, TypeVar

from dataclasses_json import dataclass_json

from bear.bear import Bear, DebugView, bears
from bear.eww import EwwJSONView
from bear.poke import (
    DBusMixin,
    DBusObjectsProvider,
    MultiPoke,
    MultiProxyPoke,
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

    @property
    def connected_devices(self):
        return [dev for dev in self.all_devices if dev.connected]

    @property
    def paired_devices(self):
        return [dev for dev in self.all_devices if dev.paired]

    @property
    def all_devices(self):
        return [poke.data for poke in self.poke_map.values()]


@bears.recruit
class BluetoothBear(Bear):
    name = "bluetooth"
    devices = BluetoothDevicesPoke()

    # adapter = BluetoothAdapter()

    debug = DebugView(keys=["connected", "paired", "primary"])

    eww = EwwJSONView(var_name="bluetooth_devices")

    def build_context(self):
        return {
            "primary": self.devices.connected_devices[0]
            if self.devices.connected_devices
            else None,
            "connected": self.devices.connected_devices,
            "paired": self.devices.paired_devices,
            "all": self.devices.all_devices,
        }
