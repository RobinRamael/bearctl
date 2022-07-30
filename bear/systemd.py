import logging
import threading
import time

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError
from gi.repository import GLib

from bear.bear import LabelBear, dbus_method
from bear.utils import snake2camel
from bear.views import BlockState

SYSTEMD_BUS_NAME = "org.freedesktop.systemd1"
SYSTEMD_PATH = "/org/freedesktop/systemd1"
SYSTEMD_MANAGER = "org.freedesktop.systemd1.Manager"

logger = logging.getLogger(__name__)

PAUSE_ICON = "\uf04c"


class SystemdManager:
    def __init__(self, bus):
        self.bus = bus
        self.manager = self.bus.get_proxy(SYSTEMD_BUS_NAME, SYSTEMD_PATH)

    def get_unit(self, service_name):
        path = self.manager.GetUnit(service_name)
        logger.info(f"Got unit with path {path}")
        return self.bus.get_proxy(SYSTEMD_BUS_NAME, path)


class ServiceCtl:
    def __init__(self, service_name, systemd=None):
        self.service_name = service_name
        self.systemd = systemd or SystemdManager(SessionMessageBus())
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
        logger.debug("properties changed, notifying listeners")
        for listener in self.property_listeners:
            listener(*args, **kwargs)

        logger.debug("notified all listeners")

    def __getattr__(self, name):
        try:
            return self.unit.Get(
                "org.freedesktop.systemd1.Unit", snake2camel(name)
            ).unpack()
        except GLib.GError:
            raise AttributeError

    @property
    def stopped(self):
        return self.active_state != "active"

    def start(self):
        self.unit.Start("replace")

    def stop(self):
        self.unit.Stop("replace")


class ServiceLabelBear(LabelBear):
    def __init__(self, *args, servicectl: ServiceCtl, **kwargs):
        super().__init__(*args, **kwargs)
        self.servicectl = servicectl

    def on_property_change(self, name, changed_props, _):
        if "ActiveState" in changed_props:
            logger.info(
                f"Received changed ActiveState in {self.name}, is {changed_props['ActiveState']}"
            )
            self.update_label()

    def register(self):
        super().register()
        self.servicectl.register_listener(self.on_property_change)

    def update_label(self):
        status = self.servicectl.active_state
        sub_status = self.servicectl.sub_state

        logger.debug(
            f"updating label for {self.name} for service state {status}/{sub_status}"
        )

        if status == "active":
            if sub_status == "running":
                self.view.update_simple_icon(self.icon, BlockState.good)
            else:
                self.view.update("f{self.icon} {sub_status}", None, BlockState.warning)

        else:
            self.view.update_simple_icon(self.icon, BlockState.error)

    def initialize_view(self):
        self.update_label()

    @dbus_method()
    def start(self):
        self.servicectl.start()
        logger.info(f"Started {self.name} service")

    @dbus_method()
    def stop(self):
        logger.debug(f"Stopping {self.name} service")
        self.servicectl.stop()
        logger.info(f"Stopped {self.name} service")


class RevivingThread(threading.Thread):
    def __init__(self, servicectl, seconds):
        super().__init__(daemon=True)
        self.seconds = seconds
        self.cancel_event = threading.Event()
        self.servicectl = servicectl

    def run(self):
        time.sleep(self.seconds)
        logger.debug("Reviving thread woke up")
        if not self.cancel_event.is_set():
            logger.debug("Restarting after pause")
            self.servicectl.start()
        else:
            logger.debug("Reviving thread was cancelled, not restarting the service.")


class PauseableServiceLabelBear(ServiceLabelBear):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.paused = False
        self.reviving_thread = None

    @dbus_method(int)
    def pause(self, seconds: int):
        if self.servicectl.stopped:
            return

        self.stop()

        self.reviving_thread = RevivingThread(self.servicectl, seconds)
        self.reviving_thread.start()
        self.paused = True

        logger.debug(f"Paused {self.name} for {seconds} seconds")

    @dbus_method(int)
    def start(self):
        super().start()

        self.paused = False

        if self.reviving_thread:
            logger.debug("Cancelling reviving thread.")
            self.reviving_thread.cancel_event.set()

    @dbus_method(int)
    def toggle_pause(self, seconds: int):
        logger.debug("toggle_pause call received")
        if self.servicectl.stopped:
            self.start()
            logger.info(f"service is stopped pause is {self.paused}, unpauseing.")
        else:
            self.pause(seconds)

    def update_label(self):
        if self.paused:
            self.view.update_simple_icon(PAUSE_ICON, BlockState.warning)
        else:
            super().update_label()
