from dataclasses import dataclass
import logging
from typing import Any, List

from dataclasses_json import dataclass_json

from bear.bear import Bear, DebugView, bears
from bear.eww import EwwJSONView
from bear.poke import DBUSServicePoke, DBusPoke, MultiPoke, ProxyPoke

OBJ_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"
BLUEZ_DEVICE_INTERFACE = "org.bluez.Device1"
BLUEZ_SERVICE_NAME = "org.bluez"

logger = logging.getLogger(__name__)


class DBusObjectsPoke(DBusPoke):
    obj_manager: Any
    service_name: str
    obj_manager_path: str = "/"
    interface_name: str

    def __init__(
        self,
        *args,
        service_name=None,
        obj_manager_path=None,
        interface_name=None,
        use_session_bus=True,
        **kwargs,
    ):
        super().__init__(*args, use_session_bus=use_session_bus, **kwargs)

        if service_name:
            self.service_name = service_name

        if obj_manager_path:
            self.obj_manager_path = obj_manager_path

        if interface_name:
            self.interface_name = interface_name

    def get_initial_data(self):
        paths = set()
        for obj_path, interfaces in self.obj_manager.GetManagedObjects().items():
            if self.interface_name in interfaces:
                paths.add(obj_path)

        return {"objects": paths}

    def register(self):
        self.obj_manager = self.bus.get_proxy(
            self.service_name,
            self.obj_manager_path,
            interface_name=OBJ_MANAGER_INTERFACE,
        )

        super().register()

        self.obj_manager.InterfacesAdded.connect(self.on_added)
        self.obj_manager.InterfacesRemoved.connect(self.on_removed)

    def on_added(self, obj_path, interfaces):
        if self.interface_name in interfaces:
            assert obj_path not in self.current_data["objects"]
            self.current_data["new"] = obj_path
            self.current_data["removed"] = None
            self.current_data["objects"].add(obj_path)
            logger.debug(f"Object {obj_path} was added")

    def on_removed(self, obj_path, interfaces):
        if self.interface_name in interfaces:
            assert obj_path in self.current_data["objects"]
            self.current_data["new"] = None
            self.current_data["removed"] = obj_path
            self.current_data["objects"].remove(obj_path)
            logger.debug(f"Object {obj_path} was removed")


@dataclass_json
@dataclass
class Device:
    address: str
    alias: str
    connected: bool
    paired: bool
    services_resolved: bool
    trusted: bool


class BluetoothDevicesPoke(MultiPoke):
    devices = DBusObjectsPoke(
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

    def create_proxypoke(self, obj_path):
        poke = ProxyPoke(
            service_name=BLUEZ_SERVICE_NAME,
            interface_name=BLUEZ_DEVICE_INTERFACE,
            use_session_bus=False,
            obj_path=obj_path,
            property_names=self.property_names,
            data_class=Device,
        )

        return poke

    def register(self):
        super().register()

        for obj_path in self.devices.data["objects"]:
            self.add_subpoke(obj_path, self.create_proxypoke(obj_path), initial=True)

    def update(self):
        if self.devices.data["new"]:
            obj_path = self.devices.data["new"]
            self.add_subpoke(obj_path, self.create_proxypoke(obj_path))

        if self.devices.data["removed"]:
            obj_path = self.devices.data["removed"]
            self.remove_subpoke(obj_path)

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
