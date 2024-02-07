from dataclasses import dataclass
import enum
import logging
import subprocess

from bear.bear import Bear, bears
from bear.icons import Icons
from bear.views import (
    BearLabel,
    BlockState,
    NotificationCtl,
    NotificationIcons,
    NotificationUrgency,
)

UPOWER_DEVICE_INTERFACE = "org.freedesktop.UPower.Device"
UPOWER_BUS_NAME = "org.freedesktop.UPower"
UPOWER_DEVICE_PATH_PREFIX = "/org/freedesktop/UPower/devices/"

logger = logging.getLogger(__name__)


class BatteryState(enum.Enum):
    UNKNOWN = 0
    CHARGING = 1
    DISCHARGING = 2
    EMPTY = 3
    FULLY_CHARGED = 4
    PENDING_CHARGE = 5
    PENDING_DISCHARGE = 6


class Battery:
    def __init__(self, bus, device_name="DisplayDevice"):
        self.bus = bus
        self.device_name = device_name

        self.device = self.bus.get_proxy(UPOWER_BUS_NAME, self.device_path)

    @property
    def device_path(self):
        return f"{UPOWER_DEVICE_PATH_PREFIX}{self.device_name}"

    @property
    def percentage_charged(self):
        return self.device.Get(UPOWER_DEVICE_INTERFACE, "Percentage").unpack()

    @property
    def is_discharging(self):
        return self.state not in (BatteryState.CHARGING, BatteryState.PENDING_CHARGE)

    @property
    def state(self):
        return BatteryState(self.device.Get(UPOWER_DEVICE_INTERFACE, "State").unpack())

    def register_percentage_listener(self, f):
        def listener(_, changed_props, __):
            if "Percentage" in changed_props:
                f(changed_props["Percentage"].unpack())

        self.device.PropertiesChanged.connect(listener)

    def register_battery_state_listener(self, f):
        def listener(_, changed_props, __):
            if "State" in changed_props:
                f(BatteryState(changed_props["State"].unpack()))

        self.device.PropertiesChanged.connect(listener)


@dataclass
class BatteryData:
    percentage: int
    state: BatteryState


class BatteryMonitor:
    def __init__(self, view: BearLabel, bounds=(10, 30, 100)):
        self.critical_level, self.low_level, self.full_level = bounds
        assert self.critical_level <= self.low_level <= self.full_level
        self.view = view

    def block_state_for(self, perc):
        if perc > self.low_level:
            return BlockState.good

        elif perc > self.critical_level:
            return BlockState.warning
        else:
            return BlockState.error

    def icon_for(self, data: BatteryData):
        if data.state == BatteryState.CHARGING:
            icons = Icons.BATTERY_CHARGING_LEVELS
            logging.debug("using charging icons")
        else:
            icons = Icons.BATTERY_LEVELS
            logging.debug("using regular icons")

        return icons[int(data.percentage // (100 / len(icons)))]

    def on_change(self, battery_data):
        self.view.update(
            f"{battery_data.percentage:>3.0f}%",  # nothing after comma, pad to length 3
            state=self.block_state_for(battery_data.percentage),
            icon=self.icon_for(battery_data),
        )


class BatteryNotificationView:
    def __init__(self, notifications, nag_lobound):
        self.notifications = notifications
        self.notification_id = None
        self.nag_lobound = nag_lobound

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

    def on_change(self, battery_data: BatteryData):
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


class BatteryBear2(Bear):
    def __init__(
        self,
        bus,
        name: str,
        battery: Battery,
        notifications: NotificationCtl,
        view: BearLabel,
        bounds=(10, 30, 100),
    ):
        super().__init__(bus, name)
        self.battery = battery
        self.view = view

        self.notifications = BatteryNotificationView(notifications, bounds[0])
        self.monitor = BatteryMonitor(view, bounds)

    def register(self):
        super().register()

        self.battery.register_percentage_listener(self.on_percentage_change)
        self.battery.register_battery_state_listener(self.on_battery_state_change)

        self.last_data = BatteryData(
            self.battery.percentage_charged, self.battery.state
        )

        self.monitor.on_change(self.last_data)

    def on_change(self, battery_data):
        self.monitor.on_change(battery_data)
        self.notifications.on_change(battery_data)

    def on_percentage_change(self, perc):
        new_data = BatteryData(perc, self.last_data.state)
        self.on_change(new_data)
        self.last_data = new_data

    def on_battery_state_change(self, state):
        new_data = BatteryData(self.last_data.percentage, state)
        self.on_change(new_data)
        self.last_data = new_data


# class BatteryPoker(PropertiesPoker):
#     def __init__(self, battery_name, property_names=["Percentage", "State"]):
#         super().__init__(
#             self.
#             property_names,
#         )


# @bears.recruit
# class BatteryBear(Bear):
#     battery = BatteryPoker("DisplayDevice")
