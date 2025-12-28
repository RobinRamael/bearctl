from dataclasses import dataclass
import logging
import threading

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError
from gi.repository import GLib

from bear.bear import ActionableBear, Bear, bears, dbus_method
from bear.eww import EwwPrefixView
from bear.poke import ProxyPoke
from bear.sway import FocusedWindowBear, SwayFocusedWorkspacePoke
from bear.utils import snake2camel

SYSTEMD_BUS_NAME = "org.freedesktop.systemd1"
SYSTEMD_PATH = "/org/freedesktop/systemd1"
SYSTEMD_MANAGER = "org.freedesktop.systemd1.Manager"

logger = logging.getLogger(__name__)


class ServiceStates:
    DISABLED = "disabled"
    ENABLED = "enabled"
    PAUSED = "paused"
    ISOLATED = "isolated"


class SystemdManager:
    def __init__(self, bus):
        self.bus = bus
        self.manager = self.bus.get_proxy(SYSTEMD_BUS_NAME, SYSTEMD_PATH)
        self.subscribed = False

    def ensure_subscribed(self):
        if not self.subscribed:
            try:
                self.manager.Subscribe()
            except DBusError as e:
                if not e.dbus_name == "org.freedesktop.systemd1.AlreadySubscribed":
                    raise e

    def get_unit(self, service_name):
        path = self.manager.GetUnit(service_name)
        logger.info(f"Got unit with path {path}")
        return self.bus.get_proxy(SYSTEMD_BUS_NAME, path)


session_bus = SessionMessageBus()
session_systemd = SystemdManager(session_bus)


class ServiceCtl:
    def __init__(self, service_name, systemd=None):
        self.service_name = service_name
        self.systemd = systemd or SystemdManager(SessionMessageBus())
        self.property_listeners = []
        self.unit = self.systemd.get_unit(self.service_name)

    def __getattr__(self, name):
        try:
            return self.unit.Get(
                "org.freedesktop.systemd1.Unit", snake2camel(name)
            ).unpack()
        except GLib.GError:
            raise AttributeError


@dataclass
class ServiceState:
    active_state: str
    sub_state: str

    @property
    def stopped(self):
        return self.active_state != "active"


class ServiceStatePoke(ProxyPoke):
    data_class = ServiceState
    interface_name = "org.freedesktop.systemd1.Unit"
    service_name = "org.freedesktop.systemd1"

    def __init__(
        self, service_name, property_names=["active_state", "sub_state"], **kwargs
    ):
        super().__init__(property_names=property_names, **kwargs)
        self.systemd_name = service_name

    def get_proxy(self):
        systemd = SystemdManager(self.bus)
        systemd.ensure_subscribed()
        return systemd.get_unit(self.systemd_name)

    def start(self):
        self.proxy.Start("replace")

    def stop(self):
        self.proxy.Stop("replace")


class SystemdServiceBear(Bear):
    service: ServiceStatePoke

    def get_extra_context(self):
        return {
            "state": (
                ServiceStates.ENABLED if self.is_enabled() else ServiceStates.DISABLED
            )
        }

    def is_enabled(self):
        return (
            self.service.data.active_state == "active"
            and self.service.data.sub_state == "running"
        )

    @dbus_method()
    def start(self):
        if self.is_enabled():
            logger.debug("Service was already started")
            return

        self.service.start()
        logger.info(f"Started {self.name} service")

    @dbus_method()
    def stop(self):
        if not self.is_enabled():
            logger.debug("Service was already stopped")
            return

        logger.debug(f"Stopping {self.name} service")
        self.service.stop()
        logger.info(f"Stopped {self.name} service")

    @dbus_method(int)
    def toggle(self):
        logger.debug("toggle call received")
        if self.service.data.stopped:
            self.start()
        else:
            self.stop()

    def on_left_click(self):
        self.toggle()


class PauseableSystemdServiceBear(SystemdServiceBear, ActionableBear):
    pause_interval: int = 60 * 60

    def __init__(self, *args, pause_interval=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.paused = False
        self.reviving_thread = None
        if pause_interval:
            self.pause_interval = pause_interval

        self.cancel_pause_event = threading.Event()

    def get_extra_context(self):
        ctx = super().get_extra_context()

        if self.service.data.stopped and self.paused:
            ctx["state"] = ServiceStates.PAUSED

        return ctx

    @dbus_method(int)
    def pause(self, seconds: int):
        if self.service.data.stopped:
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

        self.update()

        logger.debug(f"Paused {self.name} for {seconds} seconds")

    @dbus_method()
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
        if self.service.data.stopped:
            self.start()
            logger.info(f"service is stopped pause is {self.paused}, unpauseing.")
        else:
            self.pause(seconds)

    def on_left_click(self):
        self.toggle_pause(self.pause_interval)


@bears.recruit
class DropboxBear(SystemdServiceBear):
    name = "dropbox"
    service = ServiceStatePoke("dropbox.service")
    view = EwwPrefixView(var_names=["state"])


@bears.recruit
class GammastepBear(PauseableSystemdServiceBear):
    name = "gammastep"
    service = ServiceStatePoke("gammastep.service")
    view = EwwPrefixView(var_names=["state"])

    focused_workspace = SwayFocusedWorkspacePoke()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disabled_workspaces: set[int] = set()

    @dbus_method()
    def toggle_for_current_workspace(self):
        focused: int = self.focused_workspace.data["focused"]
        if focused in self.disabled_workspaces:
            self.disabled_workspaces.remove(focused)
            self.start()
        else:
            self.disabled_workspaces.add(focused)
            self.stop()

    def get_extra_context(self):
        ctx = super().get_extra_context()

        if self.focused_workspace.data["focused"] in self.disabled_workspaces:
            ctx["state"] = ServiceStates.ISOLATED

        return ctx

    def toggle_pause(self, seconds: int):
        # when a general pause is enabled, clear all workspace specific
        # pauses
        self.disabled_workspaces.clear()

        return super().toggle_pause(seconds)

    def post_update(self):
        super().post_update()

        if self.focused_workspace.data["focused"] in self.disabled_workspaces:
            self.stop()
        elif not self.paused:
            self.start()

    def on_right_click(self):
        self.toggle_for_current_workspace()
