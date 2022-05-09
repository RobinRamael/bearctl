from dasbus.connection import SessionMessageBus
from gi.repository import GLib

SYSTEMD_BUS_NAME = "org.freedesktop.systemd1"
SYSTEMD_PATH = "/org/freedesktop/systemd1"
SYSTEMD_MANAGER = "org.freedesktop.systemd1.Manager"

from utils import snake2camel


class SystemdManager:
    def __init__(self, bus):
        self.bus = bus
        self.manager = self.bus.get_proxy(SYSTEMD_BUS_NAME, SYSTEMD_PATH)

    def get_unit(self, service_name):
        path = self.manager.GetUnit(service_name)
        print(path)
        return self.bus.get_proxy(SYSTEMD_BUS_NAME, path)


class ServiceCtl:
    def __init__(self, service_name, systemd=None, bus=None):
        self.bus = bus or SessionMessageBus()
        self.service_name = service_name
        self.systemd = systemd or SystemdManager(self.bus)
        self.property_listeners = []
        self.unit = self.systemd.get_unit(self.service_name)

    def get_properties(self):
        return self.unit.GetAll("org.freedesktop.systemd1.Service")

    def register_listener(self, func):
        if not self.property_listeners:
            self.systemd.manager.Subscribe()
            self.unit.PropertiesChanged.connect(self.on_properties_changed)

        self.property_listeners.append(func)

    def on_properties_changed(self, *args, **kwargs):
        for listener in self.property_listeners:
            listener(*args, **kwargs)

    def __getattr__(self, name):
        try:
            return self.unit.Get("org.freedesktop.systemd1.Unit", snake2camel(name)).unpack()
        except GLib.GError:
            raise AttributeError

    def start(self):
        print("start!")

    def stop(self):
        print("stop!")
