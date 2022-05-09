import threading
import time
from functools import wraps

import lxml.builder
import lxml.etree
from gi.repository import GLib

from i3status import I3StatusBlock
from systemd import ServiceCtl, SystemdManager
from utils import snake2camel


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


class Bear(metaclass=BearMeta):
    """"""

    def __init__(
        self,
        i3status: I3StatusBlock,
        name: str,
        servicectl: ServiceCtl,
    ):
        self.i3status = i3status
        self.servicectl = servicectl
        self.name = name
        # todo: dasbus can do this for us probably
        self.__dbus_xml__ = generate_dbus_xml(
            f"org.robinramael.bear.{self.dbus_name}", self._dbus_methods
        )

    def on_property_change(self, name, changed_props, invalidated_props):
        if "ActiveState" in changed_props:
            print(changed_props["ActiveState"])
            self.update_label()

    def update_label(self):
        status = self.servicectl.active_state
        sub_status = self.servicectl.sub_state

        self.i3status.set_i3_block(f"{status} ({sub_status})", "backlight_full", "Good")

    @property
    def dbus_name(self):
        return f"{snake2camel(self.name)}Bear"

    def register(self, bus):
        bus.publish_object(
            f"/org/robinramael/bear/{self.dbus_name}", self)

        bus.register_service(f"org.robinramael.bear.{self.dbus_name}")

        self.servicectl.register_listener(self.on_property_change)



class ServiceBear(Bear):

    @dbus_method
    def start(self):
        self.servicectl.start()

    @dbus_method
    def stop(self):
        self.servicectl.stop()

    @dbus_method
    def pause(self):
        print("pause!")
