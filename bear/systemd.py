import logging
import threading
import time

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError
from gi.repository import GLib

from bear.bear import Bear, dbus_method
from bear.utils import snake2camel

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
    def pause(self, seconds: int):
        self.stop()

        def func():
            time.sleep(seconds)
            self.start()

        threading.Thread(daemon=True, target=func).run()
