import inspect
import logging
import threading
import time
from collections import ChainMap
from functools import wraps

from dasbus.typing import get_dbus_type
from dasbus.xml import XMLGenerator as DBusXML
from gi.repository import GLib

from bear.utils import snake2camel
from bear.views import BearView

logger = logging.getLogger(__name__)


def generate_dbus_xml(interface_name: str, methods: dict):

    root = DBusXML.create_node()
    interface = DBusXML.create_interface(interface_name)

    DBusXML.add_child(root, interface)

    for method_name, method in methods.items():
        method_node = DBusXML.create_method(method_name)
        for param_name, param in list(inspect.signature(method).parameters.items())[1:]:
            DBusXML.add_child(
                method_node,
                DBusXML.create_parameter(
                    param_name, get_dbus_type(param.annotation), "in"
                ),
            )
        DBusXML.add_child(interface, method_node)

    return DBusXML.element_to_xml(root)



class BearMeta(type):
    def __new__(cls, cls_name, bases, attrs):
        dbus_methods_in_cls = {}
        for key, attr in attrs.items():
            if callable(attr) and getattr(attr, "is_dbus_method", False):
                new_method_name = snake2camel(key)
                dbus_methods_in_cls[new_method_name] = attr

        for method_name, method in dbus_methods_in_cls.items():
            attrs[method_name] = method

        all_dbus_methods = ChainMap(
            *[c._dbus_methods for c in bases], dbus_methods_in_cls
        )
        attrs["_dbus_methods"] = all_dbus_methods

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
