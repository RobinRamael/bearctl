from abc import ABC, abstractmethod
import logging
from typing import Union

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError
from gi.repository import GLib

BLINK_LENGTH_SECONDS = 1


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


POSSIBLE_I3_STATUS_NAMES = ["rs.i3status", "rs.i3status.bottom", "rs.i3status.top"]


logger = logging.getLogger(__name__)


class BlockState:
    good = "good"
    warning = "warning"
    error = "critical"
    idle = "idle"


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


class Null(BearLabel):
    def update(self, message, icon, state):
        pass


class NotificationUrgency:
    low = 0
    normal = 1
    critical = 2
    error = "critical"
    idle = "idle"


class NotificationCtl:
    def __init__(self, session_bus):
        self.notifications = session_bus.get_proxy(
            "org.freedesktop.Notifications", "/org/freedesktop/Notifications"
        )

    def notify(self, title, msg, replace_id=0, urgency=NotificationUrgency.normal):
        return self.notifications.Notify(
            "",
            replace_id,
            "face-smile",
            title,
            msg,
            [],
            [],
            0,
        )

    def close_notification(self, notification_id):
        self.notifications.CloseNotification(notification_id)

    def register_notification_callback(self, f):
        self.notifications.NotificationClosed(f)
