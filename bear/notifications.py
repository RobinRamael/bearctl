import threading
import time

from dasbus.typing import Variant


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

    def notify_and_close(
        self,
        title,
        msg,
        replace_id=0,
        urgency=NotificationUrgency.normal,
        icon="",
        seconds=5,
    ):

        notification_id = self.notify(
            title,
            msg,
            replace_id=replace_id,
            urgency=urgency,
            icon=icon,
        )

        def close():
            time.sleep(seconds)
            self.close_notification(notification_id)

        threading.Thread(target=close).start()

    def close_notification(self, notification_id):
        self.notifications.CloseNotification(notification_id)

    def register_notification_callback(self, f):
        self.notifications.NotificationClosed(f)
