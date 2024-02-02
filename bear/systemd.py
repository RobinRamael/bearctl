import logging
import threading
import time

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError
from gi.repository import GLib

from bear.bear import ActionableBear, Bear, LabelBear, WidgetBear, dbus_method
from bear.eww import EwwController, EwwServiceWidget
from bear.icons import Icons
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


class ServiceLabelBear(WidgetBear):
    def __init__(
        self, *args, servicectl: ServiceCtl, widget: EwwServiceWidget, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.servicectl = servicectl
        self.widget = widget

    def on_property_change(self, _, changed_props, __):
        if "ActiveState" in changed_props:
            logger.info(
                f"Received changed ActiveState in {self.name}, is {changed_props['ActiveState']}"
            )
            self.update_widget()

    def register(self):
        super().register()
        self.servicectl.register_listener(self.on_property_change)

    def update_widget(self):
        status = self.servicectl.active_state
        sub_status = self.servicectl.sub_state

        logger.debug(
            f"updating label for {self.name} for service state {status}/{sub_status}"
        )

        if status == "active":
            if sub_status == "running":
                self.widget.set_enabled()
            else:
                self.widget.set_disabled()

        else:
            self.widget.set_disabled()

    @dbus_method()
    def start(self):
        self.servicectl.start()
        logger.info(f"Started {self.name} service")

    @dbus_method()
    def stop(self):
        logger.debug(f"Stopping {self.name} service")
        self.servicectl.stop()
        logger.info(f"Stopped {self.name} service")

    @dbus_method(int)
    def toggle(self):
        logger.debug("toggle call received")
        if self.servicectl.stopped:
            self.start()
        else:
            self.stop()

    def on_left_click(self):
        self.toggle()


class PauseableServiceLabelBear(ServiceLabelBear, ActionableBear):
    def __init__(self, *args, pause_interval=60 * 60, **kwargs):
        super().__init__(*args, **kwargs)
        self.paused = False
        self.reviving_thread = None
        self.pause_interval = pause_interval
        self.cancel_pause_event = threading.Event()

    @dbus_method(int)
    def pause(self, seconds: int):
        if self.servicectl.stopped:
            return

        self.paused = True

        self.stop()

        def restart():
            self.paused = False

            if not self.cancel_pause_event.is_set():
                self.start()
            else:
                logger.debug("No restart needed because pause was cancelled")

            return False  # only do this once

        self.cancel_pause_event.clear()
        GLib.timeout_add_seconds(
            priority=GLib.PRIORITY_DEFAULT, interval=seconds, function=restart
        )

        self.update_widget()

        logger.debug(f"Paused {self.name} for {seconds} seconds")

    @dbus_method(int)
    def start(self):
        super().start()

        if self.paused:
            self.cancel_pause_event.set()
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

    def on_left_click(self):
        logger.info("pausing")
        self.toggle_pause(self.pause_interval)

    def update_widget(self):
        if self.paused:
            logger.info("setting widget paused")
            self.widget.set_paused()
        else:
            super().update_widget()
