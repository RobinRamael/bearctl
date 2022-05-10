import logging
import threading
import time
from functools import wraps

import lxml.builder
import lxml.etree
from gi.repository import GLib

from .systemd import ServiceCtl, SystemdManager
from .utils import snake2camel
from .views import BearView, I3StatusBlock, Printer

logger = logging.getLogger(__name__)


def generate_dbus_xml(interface_name: str, methods: dict):
    E = lxml.builder.ElementMaker()

    method_nodes = []

    for name, method in methods.items():
        method_nodes.append(E.method(name=name.capitalize()))

    node = E.node(E.interface(*method_nodes, name=interface_name))
    return lxml.etree.tostring(node).decode()


class BearMeta(type):
    def __new__(cls, cls_name, bases, attrs):
        dbus_methods = {}
        for key, attr in attrs.items():
            if callable(attr) and getattr(attr, "is_dbus_method", False):
                new_method_name = snake2camel(key)
                dbus_methods[new_method_name] = attr

        for method_name, method in dbus_methods.items():
            attrs[method_name] = method

        attrs["_dbus_methods"] = dbus_methods

        obj = super().__new__(cls, cls_name, bases, attrs)
        return obj


def dbus_method(func):
    func.is_dbus_method = True

    @wraps(func)
    def decorated(*args, **kwargs):
        func(*args, **kwargs)

    return decorated


class BearClient:
    def __init__(self, proxy):
        self.proxy = proxy

    def call(self, name: str):
        return getattr(self.proxy, snake2camel(name))()


class Bear(metaclass=BearMeta):
    _dbus_methods = {}  # should always be overwritten in BearMeta

    def __init__(self, bus, name: str, view: BearView, icon: str):
        self.bus = bus
        self.view = view
        self.name = name
        self.icon = icon
        # todo: dasbus can do this for us probably
        self.__dbus_xml__ = generate_dbus_xml(
            f"org.robinramael.bear.{self.dbus_name}", self._dbus_methods
        )

    def update_view(self, msg, icon, status):
        self.view.update(msg, icon, status)

    @property
    def dbus_name(self):
        return f"{snake2camel(self.name)}Bear"

    def register(self):
        self.bus.publish_object(f"/org/robinramael/bear/{self.dbus_name}", self)
        self.bus.register_service(f"org.robinramael.bear.{self.dbus_name}")

    def get_client(self):
        proxy = self.bus.get_proxy(
            (f"org.robinramael.bear.{self.dbus_name}"),
            f"/org/robinramael/bear/{self.dbus_name}",
        )

        return BearClient(proxy)


class ServiceBear(Bear):
    def __init__(self, *args, servicectl: ServiceCtl, **kwargs):
        super().__init__(*args, **kwargs)
        self.servicectl = servicectl

    def on_property_change(self, name, changed_props, _):
        if "ActiveState" in changed_props:
            logger.info(
                f"Received changed ActiveState, is {changed_props['ActiveState']}"
            )
            self.update_label()

    def register(self):
        super().register()
        self.servicectl.register_listener(self.on_property_change)

    def update_label(self):
        status = self.servicectl.active_state
        sub_status = self.servicectl.sub_state

        self.update_view(f"{status} ({sub_status})", self.icon, "Good")

    @dbus_method
    def start(self):
        logger.info(f"Starting {self.dbus_name}")
        self.servicectl.start()

    @dbus_method
    def stop(self):
        logger.info(f"Stopping {self.dbus_name}")
        self.servicectl.stop()

class PauseableServiceBear(ServiceBear):

    @dbus_method
    def pause(self):
        self.stop()

        def func():
            self.start()


