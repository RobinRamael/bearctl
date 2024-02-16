import logging
from os import access
from typing import List, Optional

from dasbus.connection import SystemMessageBus

from bear.bear import Bear, DebugView, bears
from bear.eww import EwwPrefixView
from bear.poke import DBusMixin, DBusObjectsProvider, ObjectManager, Poke, ProxyPoke


logger = logging.getLogger(__name__)


NETWORK_MANAGER_SERVICE_NAME = "org.freedesktop.NetworkManager"
ACTIVE_CONNECTION_INTERFACE = "org.freedesktop.NetworkManager.Connection.Active"
DEVICE_INTERFACE = "org.freedesktop.NetworkManager.Device"
NETWORK_MANAGER_OBJECT_MANAGER_PATH = "/org/freedesktop"
WIRELESS_INTERFACE = "org.freedesktop.NetworkManager.Device.Wireless"
ACCESS_POINT_INTERFACE = "org.freedesktop.NetworkManager.AccessPoint"


nm_obj_manager = ObjectManager(
    SystemMessageBus(),
    NETWORK_MANAGER_SERVICE_NAME,
    NETWORK_MANAGER_OBJECT_MANAGER_PATH,
)


class NoSuchDevice(Exception):
    pass


def get_device_path_for(ip_interface: str) -> str:
    for obj_path, proxy in nm_obj_manager.get_objects_of_interface(DEVICE_INTERFACE):
        if proxy.Interface == ip_interface:
            return obj_path
    else:
        raise NoSuchDevice


def is_wireless_device(obj_path: str) -> bool:
    bus = SystemMessageBus()

    proxy = bus.get_proxy(NETWORK_MANAGER_SERVICE_NAME, obj_path)

    try:
        proxy.ActiveAccessPoint
        return True
    except:
        return False


class WirelessStrenghtPoke(Poke, DBusMixin):
    device_poke: ProxyPoke
    access_point_poke: Optional[ProxyPoke]

    def __init__(self, ip_interface: str):
        super().__init__()
        self.ip_interface = ip_interface
        self.access_point_poke = None

    def register(self, parent):
        super().register(parent)
        self.session_bus = parent.session_bus
        self.system_bus = parent.system_bus

        device_object_path = get_device_path_for(self.ip_interface)

        self.device_poke = ProxyPoke(
            service_name=NETWORK_MANAGER_SERVICE_NAME,
            interface_name=WIRELESS_INTERFACE,
            use_session_bus=False,
            obj_path=device_object_path,
            property_names=["active_access_point"],
        )

        self.device_poke.register(self)
        self.device_poke.add_handler(self.access_point_changed)

        self.set_access_point_subpoke(self.device_poke.data["active_access_point"])

    def set_access_point_subpoke(self, obj_path):
        self.access_point_poke = ProxyPoke(
            service_name=NETWORK_MANAGER_SERVICE_NAME,
            interface_name=ACCESS_POINT_INTERFACE,
            obj_path=obj_path,
            use_session_bus=False,
            property_names=["strength"],
        )
        self.access_point_poke.register(self)
        self.access_point_poke.add_handler(self.poke)

    def access_point_changed(self):
        if self.access_point_poke:
            self.access_point_poke.unregister()

        access_point_path = self.device_poke.data["active_access_point"]
        if access_point_path != "/":
            self.set_access_point_subpoke(access_point_path)
        else:
            self.access_point_poke = None
        self.poke()

    def get_data_dict(self) -> dict:
        if not self.access_point_poke:
            return {}
        return self.access_point_poke.get_data_dict()


class ActiveConnectionsPoke(Poke, DBusMixin):
    use_session_bus = False
    connection_poke: Optional[ProxyPoke]
    access_point_poke: Optional[ProxyPoke]

    def __init__(self, ip_interface):
        super().__init__()
        self.ip_interface = ip_interface
        self.connection_poke = None

    provider = DBusObjectsProvider(
        service_name=NETWORK_MANAGER_SERVICE_NAME,
        obj_manager_path="/org/freedesktop",
        interface_name=ACTIVE_CONNECTION_INTERFACE,
        use_session_bus=False,
    )

    property_names = ["id", "Devices"]

    def register(self, parent):
        self.device_object_path = get_device_path_for(self.ip_interface)

        self.session_bus = parent.session_bus
        self.system_bus = parent.system_bus
        super().register(parent)

    def add_subpoke(self, obj_path: str, *args):
        proxy: Any = self.bus.get_proxy(
            service_name=NETWORK_MANAGER_SERVICE_NAME, object_path=obj_path
        )

        if self.device_object_path and self.device_object_path in proxy.Devices:
            self.set_connection_subpoke(obj_path)

        self.poke()

    def remove_subpoke(self, connection_obj_path):
        if not self.connection_poke:
            return

        if connection_obj_path != self.connection_poke.obj_path:
            return

        self.unset_connection_subpoke()

        self.poke()

    def get_data_dict(self):
        if not self.connection_poke:
            return {"id": None}

        return {"id": self.connection_poke.data.get("id", None)}


class DevicePoke(ProxyPoke):
    use_session_bus = False
    connection_poke: Optional[ProxyPoke]
    access_point_poke: Optional[ProxyPoke]

    def __init__(self, ip_interface):
        obj_path = get_device_path_for(ip_interface)

        self.wireless = is_wireless_device(obj_path)

        if self.wireless:
            interfaces = [DEVICE_INTERFACE, WIRELESS_INTERFACE]
            property_names = ["active_connection", "active_access_point"]
        else:
            interfaces = [DEVICE_INTERFACE]
            property_names = ["active_connection"]

        super().__init__(
            service_name=NETWORK_MANAGER_SERVICE_NAME,
            obj_path=obj_path,
            interface_names=interfaces,
            property_names=property_names,
        )

        self.connection_poke = None
        self.access_point_poke = None

    def register(self, parent):
        super().register(parent)
        self.check_children()

    def check_children(self):
        if (
            not self.connection_poke
            or self.connection_poke.obj_path != self.data["active_connection"]
        ):
            self.set_connection_subpoke(self.data["active_connection"])

        if self.wireless and (
            not self.access_point_poke
            or self.access_point_poke.obj_path != self.data["active_access_point"]
        ):
            self.set_access_point_subpoke(self.data["active_access_point"])

    def poke(self):
        self.check_children()

        super().poke()

    def set_connection_subpoke(self, obj_path):
        self.unset_connection_subpoke()

        if obj_path == "/":
            return

        self.connection_poke = ProxyPoke(
            service_name=NETWORK_MANAGER_SERVICE_NAME,
            interface_name=ACTIVE_CONNECTION_INTERFACE,
            use_session_bus=False,
            obj_path=obj_path,
            property_names=["id"],
        )
        self.connection_poke.register(self)

        self.connection_poke.add_handler(self.poke)
        self.poke()

    def set_access_point_subpoke(self, obj_path):
        self.unset_access_point_subpoke()

        if obj_path == "/":
            return

        self.access_point_poke = ProxyPoke(
            service_name=NETWORK_MANAGER_SERVICE_NAME,
            interface_name=ACCESS_POINT_INTERFACE,
            obj_path=obj_path,
            use_session_bus=False,
            property_names=["strength"],
        )
        self.access_point_poke.register(self)
        self.access_point_poke.add_handler(self.poke)
        self.poke()

    def unset_connection_subpoke(self):
        if self.connection_poke:
            self.connection_poke.unregister()
            self.connection_poke = None

    def unset_access_point_subpoke(self):
        if self.access_point_poke:
            self.access_point_poke.unregister()
            self.access_point_poke = None

    def get_data_dict(self) -> dict:
        data = super().get_data_dict()
        data["id"] = (
            self.connection_poke.data.get("id", None) if self.connection_poke else None
        )

        data["strength"] = (
            self.access_point_poke.data.get("strength", None)
            if self.access_point_poke
            else None
        )

        return data


class AccessPointPoke(ProxyPoke):
    def __init__(self, obj_path):
        super().__init__(
            service_name=NETWORK_MANAGER_SERVICE_NAME,
            obj_path=obj_path,
            interface_name=ACCESS_POINT_INTERFACE,
            property_names=["active_access_point"],
        )


@bears.recruit
class NetworkBear(Bear):
    name = "network"

    device = DevicePoke(ip_interface="wlp4s0")

    eww = EwwPrefixView(prefix="network", var_names=["id", "strength"])
    debug = DebugView()

    def get_extra_context(self):
        if not self.device.data.get("id", None):
            status = "disconnected"
        else:
            status = "connected"

        return {"status": status}
