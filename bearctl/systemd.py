import logging

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError
from gi.repository import GLib

from .utils import snake2camel

SYSTEMD_BUS_NAME = "org.freedesktop.systemd1"
SYSTEMD_PATH = "/org/freedesktop/systemd1"
SYSTEMD_MANAGER = "org.freedesktop.systemd1.Manager"

logger = logging.getLogger(__name__)


class SystemdManager:
    def __init__(self, bus):
        self.bus = bus
        self.manager = self.bus.get_proxy(SYSTEMD_BUS_NAME, SYSTEMD_PATH)

    def get_unit(self, service_name):
        path = self.manager.GetUnit(service_name)
        logger.info(f"Got unit with path {path}")
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
        try:
            self.systemd.manager.Subscribe()
        except DBusError as e:
            if not e.dbus_name == "org.freedesktop.systemd1.AlreadySubscribed":
                raise e

        if not self.property_listeners:
            self.unit.PropertiesChanged.connect(self.on_properties_changed)

        self.property_listeners.append(func)

    def on_properties_changed(self, *args, **kwargs):
        logger.info("properties changed, notifying listeners")
        for listener in self.property_listeners:
            listener(*args, **kwargs)

        logger.info("notified all listeners")

    def __getattr__(self, name):
        try:
            return self.unit.Get(
                "org.freedesktop.systemd1.Unit", snake2camel(name)
            ).unpack()
        except GLib.GError:
            raise AttributeError

    def start(self):
        self.unit.Start("replace")

    def stop(self):
        self.unit.Stop("replace")
