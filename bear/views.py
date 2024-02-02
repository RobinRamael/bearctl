from abc import ABC, abstractmethod
from datetime import datetime
import logging
import os
import subprocess
import sys
from threading import Thread
from typing import Any, Callable, List, Union

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError
from dasbus.typing import Variant
from gi.repository import GLib

BLINK_LENGTH_SECONDS = 1


logger = logging.getLogger(__name__)


class BearLabel(ABC):
    @abstractmethod
    def update(self, message: str, icon: Union[str, None], state: str):
        raise NotImplementedError

    def update_simple_icon(self, icon, state):
        self.update(icon, None, state)

    def blink_simple_icon(
        self,
        first_icon,
        first_state,
        final_icon,
        final_state,
        interval=BLINK_LENGTH_SECONDS,
    ):
        self.update_simple_icon(first_icon, first_state)

        def final_update():
            self.update_simple_icon(final_icon, final_state)
            return False  # only execute this once (see timeout_add docs)

        GLib.timeout_add_seconds(
            priority=GLib.PRIORITY_DEFAULT,
            interval=interval,
            function=final_update,
        )


class CombinedLabel(BearLabel):
    def __init__(self, *labels):
        self.labels = labels

    def update(self, *args, **kwargs):
        for label in self.labels:
            label.update(*args, **kwargs)


POSSIBLE_I3_STATUS_NAMES = ["rs.i3status", "rs.i3status.bottom", "rs.i3status.top"]


class BlockState:
    good = "good"
    idle = "idle"
    info = "info"
    warning = "warning"
    error = "critical"


class I3StatusBlock(BearLabel):
    def __init__(self, block_name, session_bus=None):
        self.block_name = block_name
        self.bus = session_bus or SessionMessageBus()
        self._block = None

    @property
    def block(self):
        if not self._block:
            self._block = self.get_block()

        return self._block

    def get_block(self):
        for name in POSSIBLE_I3_STATUS_NAMES:
            block = self.bus.get_proxy(name, f"/{self.block_name}")

            try:
                # block is only checked when we try to find one of its attrs
                assert block.SetText
                logger.debug(f"Got {self.block_name} block proxy")
                return block
            except DBusError:
                continue

        raise Exception(
            f"Unable to find {self.block_name} anywhere in any of {POSSIBLE_I3_STATUS_NAMES}"
        )

    def update(self, message: str, icon: str, state: str):
        self.block.SetText(f"{message}", f"{message}")
        self.block.SetState(state)

        if icon:
            self.block.SetIcon(icon)


class LabelPrinter(BearLabel):
    def update(self, message, icon, state):
        print(f"msg: {message}, icon: {icon}, state: {state}")


STATE_COLORS = {
    BlockState.good: ("#B9D898", "#2E3440"),
    BlockState.warning: ("#ebcb8b", "#2e3440"),
    BlockState.error: ("#F37B86", "#0B0C0E"),
    BlockState.idle: ("#2e3440", "#A3CBF5"),
    BlockState.info: ("#7AA7E0", "#0A0B0E"),
}


class PolybarBlock(BearLabel):
    def __init__(self, block_name):
        self.block_name = block_name

    def ipc_send(self, new_label):
        # this needs to be done asynchronously because polybar is probably
        # waiting for the dbus method that called this function to return before
        # it can handle any other updates

        def f():
            logger.debug(
                f"sending ipc message action {self.block_name} send {new_label}"
            )
            subprocess.run(
                ["polybar-msg", "action", self.block_name, "send", new_label],
                stdout=subprocess.DEVNULL,
            )

        GLib.idle_add(f, priority=GLib.PRIORITY_HIGH_IDLE)

    def update(self, message: str, icon: str, state: str):
        message = message or ""
        icon = icon or ""
        bg, fg = STATE_COLORS[state]
        self.ipc_send(f"%{{B{bg}}}%{{F{fg}}}{icon}{message}%{{B- F-}}")


EWW_RELOAD_MATCH = "Reloaded config successfully"


class EwwLogsListener:
    def __init__(
        self,
    ):
        self.handlers: List[Callable[[], Any]] = []

    def listen(self):
        Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        proc = subprocess.Popen(["eww", "logs"], stdout=subprocess.PIPE)

        listen_start = datetime.now().astimezone()

        while True:
            line: str = proc.stdout.readline().decode()

            # flush out lines that were generated before we started listening
            if datetime.fromisoformat(line.strip().split()[0]) < listen_start:
                continue

            if EWW_RELOAD_MATCH in line:
                self.on_reload()

    def add_handler(self, handler):
        self.handlers.append(handler)

    def on_reload(self):
        logger.info("eww reloaded, notifying handlers")
        for h in self.handlers:
            h()


class EwwController:
    def __init__(self):
        self.listener = EwwLogsListener()

    def bootstrap(self):
        try:
            location = os.environ["BEARCTL_EXECUTABLE"]
            logger.debug("Found %s in env var", location)
        except KeyError:
            location = sys.argv[0]
            logger.debug("Found %s in sys.args", location)

        if not os.access(location, os.X_OK):
            logger.warning("%s is not executable, skipping...", location)
            return

        subprocess.run(["eww", "update", f"BEARCTL={location}"])
        logger.info("Bootstrapped %s into eww variable", location)

    def listen_for_reloads(self):
        self.listener.listen()

    def update(self, **kwargs):
        variables = [f"{k}={v}" for k, v in kwargs.items()]

        logger.debug("Updating: %s", ", ".join(variables))
        subprocess.run(["eww", "update", *variables])

    def var(self, name):
        v = EwwVariable(self, name)
        self.listener.add_handler(v.refresh)
        return v


class EwwVariable:
    def __init__(self, eww, name):
        self.eww = eww
        self.name = name
        self.last_value = None
        self.set_at_least_once = False

    def set(self, value):
        self.set_at_least_once = True
        self.last_value = value
        self.eww.update(**{self.name: value})

    def refresh(self):
        if self.set_at_least_once:
            logger.info("Refreshing eww variable %s=%s", self.name, self.last_value)
            self.set(self.last_value)

        else:
            logger.info("%s was never set, not refreshing", self.name)


class EwwStateBlock(BearLabel):
    def __init__(self, eww, block_name):
        self.block_name = block_name
        self.eww = eww
        self.label = eww.var(f"{self.block_name}_label")
        self.state = eww.var(f"{self.block_name}_state")

    def update(self, message: str, icon: str, state: str):
        self.label.set(message)
        self.state.set(state)


class EwwServiceStates:
    DISABLED = "disabled"
    ENABLED = "enabled"
    PAUSED = "paused"


class EwwServiceWidget:
    def __init__(self, eww: EwwController, service_name: str):
        super().__init__()
        self.service_name = service_name
        self.eww = eww
        self.state_var = eww.var(f"{self.service_name}_state")

    def set_paused(self):
        self.state_var.set(EwwServiceStates.PAUSED)

    def set_enabled(self):
        self.state_var.set(EwwServiceStates.ENABLED)

    def set_disabled(self):
        self.state_var.set(EwwServiceStates.DISABLED)


class Null(BearLabel):
    def update(self, message, icon, state):
        pass


class NotificationUrgency:
    low = 0
    normal = 1
    critical = 2


def generate_icons():
    import importlib.resources as resources

    icons = resources.files("bear.resources")

    class _Icons:
        battery_error = str(icons / "battery_error.svg")

    return _Icons()


NotificationIcons = generate_icons()


class NotificationCtl:
    def __init__(self, session_bus):
        self.notifications = session_bus.get_proxy(
            "org.freedesktop.Notifications", "/org/freedesktop/Notifications"
        )

    def notify(
        self, title, msg, replace_id=0, urgency=NotificationUrgency.normal, icon=""
    ):
        return self.notifications.Notify(
            "",
            replace_id,
            icon,
            title,
            msg,
            [],
            [("urgency", Variant.new_byte(urgency))],
            0,
        )

    def close_notification(self, notification_id):
        self.notifications.CloseNotification(notification_id)

    def register_notification_callback(self, f):
        self.notifications.NotificationClosed(f)
