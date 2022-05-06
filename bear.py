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
        self.dbus = generate_dbus_xml("org.robinramael.bear.Redshift", self._dbus_methods)
        # assert self.dbus == self.hop_dbus

    def update_label(self):
        status = self.servicectl.active_state

        self.i3status.set_i3_block(status, "backlight_full", "Good")

    def on_property_change(self):
        pass

    def register(self, bus):
        # breakpoint()
        bus.publish(f"org.robinramael.bear.{self.name}", ("/org/robinramael/bear/redshift", self, self.dbus))

    # dbus = """<node><interface name="org.robinramael.bear.Redshift"><method name="Start"/><method name="Stop"/></interface></node>"""



class ServiceBear(Bear):
    @dbus_method
    def start(self):
        self.servicectl.start()

    @dbus_method
    def stop(self):
        self.servicectl.stop()
