from dataclasses import dataclass
import enum
import logging
import subprocess

from bear.bear import Bear, BearView, bears
from bear.eww import EwwPrefixView
from bear.icons import Icons
from bear.notifications import NotificationCtl, NotificationIcons, NotificationUrgency
from bear.poke import ProxyPoke
from bear.utils import BearLevel

UPOWER_DEVICE_INTERFACE = "org.freedesktop.UPower.Device"
UPOWER_BUS_NAME = "org.freedesktop.UPower"
UPOWER_DEVICE_PATH_PREFIX = "/org/freedesktop/UPower/devices/"

logger = logging.getLogger(__name__)


class BatteryState:
    UNKNOWN = 0
    CHARGING = 1
    DISCHARGING = 2
    EMPTY = 3
    FULLY_CHARGED = 4
    PENDING_CHARGE = 5
    PENDING_DISCHARGE = 6


@dataclass
class BatteryData:
    percentage: int
    state: int

    @property
    def is_charging(self):
        return self.state in (
            BatteryState.CHARGING,
            BatteryState.FULLY_CHARGED,
        )


class BatteryPoker(ProxyPoke):
    property_names = ["percentage", "state"]
    interface_name = UPOWER_DEVICE_INTERFACE
    data_class = BatteryData
    service_name = UPOWER_BUS_NAME

    def __init__(self, battery_name):
        super().__init__(use_session_bus=False)
        self.battery_name = battery_name
        self.obj_path = f"{UPOWER_DEVICE_PATH_PREFIX}{self.battery_name}"


class BatteryNotificationView(BearView):
    notifications: NotificationCtl

    def __init__(self, nag_lobound):
        super().__init__()
        self.notification_id = None
        self.nag_lobound = nag_lobound

    def register(self, bear: Bear):
        super().register(bear)
        self.notifications = NotificationCtl(bear.session_bus)

    def notify(self):
        self.notification_id = self.notifications.notify(
            "Battery Low",
            "Computerbear says chaaaarge",
            replace_id=self.notification_id or 0,
            urgency=NotificationUrgency.critical,
            icon=NotificationIcons.battery_error,
        )
        logger.info(f"Launched notification with id {self.notification_id}")

    def close_notification(self):
        if self.notification_id:
            self.notifications.close_notification(self.notification_id)
            logger.info(f"Closed notification with id {self.notification_id}")
            self.notification_id = None

    def render(self, context):
        battery_data = context["data"]

        if battery_data.state in (BatteryState.CHARGING, BatteryState.PENDING_CHARGE):
            self.close_notification()
        elif battery_data.state == BatteryState.DISCHARGING:
            if battery_data.percentage < self.nag_lobound:
                logger.info(
                    f"Battery percentage is now %s, notifying a bear",
                    battery_data.percentage,
                )
                self.notify()
            else:
                self.close_notification()
        else:
            logger.warning("Unhandled battery state %s", battery_data.state)


@bears.recruit
class BatteryBear(Bear):
    name = "battery"
    battery = BatteryPoker("DisplayDevice")
    view = EwwPrefixView(var_names=["is_charging", "icon_name", "percentage", "status"])
    notification = BatteryNotificationView(nag_lobound=10)
    levels = (10, 20, 100)

    def get_extra_context(self):
        ctx = super().get_extra_context()

        ctx["is_charging"] = self.battery.data.is_charging
        if self.battery.data.percentage == 100:
            ctx["icon_name"] = "BATTERY_FULL_ICON"
        else:
            icon_state = "CHARGING" if self.battery.data.is_charging else "DISCHARGING"
            icon_idx = int(self.battery.data.percentage // 10)
            ctx["icon_name"] = f"BATTERY_{icon_state}_ICON_{icon_idx}"

        ctx["percentage"] = f"{self.battery.data.percentage:.0f}"

        ctx["status"] = BearLevel.level_for_type_battery(
            self.battery.data.percentage, self.levels
        )

        ctx["data"] = self.battery.data

        return ctx
