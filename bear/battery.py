import enum
import logging
import subprocess

from bear.bear import Bear
from bear.views import NotificationCtl, NotificationIcons, NotificationUrgency

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


class BatteryBear(Bear):
    def __init__(
        self,
        bus,
        name: str,
        battery: Battery,
        notifications: NotificationCtl,
        nag_lobound=10,
    ):
        super().__init__(bus, name)
        self.battery = battery
        self.nag_lobound = nag_lobound
        self.notifications = notifications
        self.notification_id = None

    def register(self):
        # no need to register our own interfaces, this is read only (for now?
        # but what would we even tell upower to do?):
        # super().register()

        self.battery.register_percentage_listener(self.on_percentage_change)
        self.battery.register_battery_state_listener(self.on_battery_state_change)

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

    def on_percentage_change(self, perc):
        if perc < self.nag_lobound and self.battery.is_discharging:
            logger.info(f"Battery percentage is now %s, notifying a bear", perc)
            self.notify()
        else:
            self.close_notification()

    def on_battery_state_change(self, state):
        logger.info(f"Battery state is now {state}")
        if state in (BatteryState.CHARGING, BatteryState.PENDING_CHARGE):
            self.close_notification()
        elif state == BatteryState.DISCHARGING:
            self.on_percentage_change(self.battery.percentage_charged)
        else:
            logger.warning("Unhandled battery state %s", state)
