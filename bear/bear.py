import inspect
import logging
import threading
import time
from collections import ChainMap
from functools import wraps

from dasbus.typing import get_dbus_type
from dasbus.xml import XMLGenerator as DBusXML
from gi.repository import GLib

from bear.exceptions import DoubleBearException
from bear.utils import snake2camel
from bear.views import BearLabel

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


def dbus_method(*args):
    def decorator(func):
        func.is_dbus_method = True
        func.dbus_args = args

        @wraps(func)
        def decorated(*args, **kwargs):
            func(*args, **kwargs)

        return decorated

    return decorator


class BearClient:
    def __init__(self, bear, proxy):
        self.bear = bear
        self.proxy = proxy

    def call(self, name: str, args):

        bear_method = getattr(self.bear, snake2camel(name))

        assert len(bear_method.dbus_args) == len(args), "incorrect n of arguments"

        transformed_args = []

        for arg, transformer in zip(args, bear_method.dbus_args):
            transformed_args.append(transformer(arg))

        if args:
            logger.info(f"transformed {args} to {transformed_args}")

        return getattr(self.proxy, snake2camel(name))(*transformed_args)


class Bear(metaclass=BearMeta):
    _dbus_methods = {}  # should always be overwritten in BearMeta

    def __init__(self, bus, name: str):
        self.bus = bus
        self.name = name
        # todo: dasbus can do this for us probably
        self.__dbus_xml__ = generate_dbus_xml(
            f"org.robinramael.bear.{self.dbus_name}", self._dbus_methods
        )

    @property
    def dbus_name(self):
        return f"{snake2camel(self.name)}Bear"

    def register(self):
        self.bus.publish_object(f"/org/robinramael/bear/{self.dbus_name}", self)
        path = f"org.robinramael.bear.{self.dbus_name}"
        try:
            self.bus.register_service(path)
        except ConnectionError:
            raise DoubleBearException(
                f"Failed to register path {path}. Is another instance of bearctl running?"
            )

    def get_client(self):
        proxy = self.bus.get_proxy(
            (f"org.robinramael.bear.{self.dbus_name}"),
            f"/org/robinramael/bear/{self.dbus_name}",
        )

        return BearClient(self, proxy)


class LabelBear(Bear):
    def __init__(self, bus, name, icon, view):
        super().__init__(bus, name)
        self.view = view
        self.icon = icon

    def update_view(self, msg, icon, status):
        self.view.update(msg, icon, status)

    def register(self):
        super().register()
        try:
            self.initialize_view()
        except Exception as e:
            logger.critical(f"Failed to initalize view for {self.name}: {e}")

    @dbus_method(str)
    def action(self, name: str):
        if name == "right_click":
            self.on_right_click()
        elif name == "left_click":
            self.on_left_click()
        elif name == "left_click":
            self.on_left_click()
        elif name == "double_left":
            self.on_double_left_click()
        else:
            raise Exception(f"Bear {self.name} rcvd unknown action {name}")

    def on_right_click(self):
        pass

    def on_left_click(self):
        pass

    def on_double_left_click(self):
        pass

    def initialize_view(self):
        pass
