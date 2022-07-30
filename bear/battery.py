import enum
import logging
import subprocess

from bear.bear import Bear
from bear.views import NotificationCtl

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


class BatteryNagbar:
    def __init__(self):
        self.process = None

    @property
    def is_running(self):
        return self.process and self.process.poll() is None

    def show(self):
        if not self.is_running:
            logger.info("Showing nagbar")
            self.process = subprocess.Popen(
                [
                    "i3-nagbar",
                    "-m",
                    "Battery Low!",
                    "-b",
                    "Hibernate!",
                    "'systemctl suspend-then-hibernate'",
                ],
                stdout=subprocess.DEVNULL,
            )

    def remove(self):
        if self.is_running:
            logger.info("Killing nagbar")
            self.process.kill()
            self.process = None


class BatteryBear(Bear):
    def __init__(self, bus, name: str, battery: Battery, nag_lobound=10):
        super().__init__(bus, name)
        self.battery = battery
        self.nagbar = BatteryNagbar()
        self.nag_lobound = nag_lobound

    def register(self):
        # no need to register our own interfaces, this is read only (for now?
        # but what would we even tell upower to do?):
        # super().register()

        self.battery.register_percentage_listener(self.on_percentage_change)
        self.battery.register_battery_state_listener(self.on_battery_state_change)

    def on_percentage_change(self, perc):
        logger.info(f"Battery percentage is now {perc}")
        if perc < self.nag_lobound:
            self.nagbar.show()
        else:
            self.nagbar.remove()

    def on_battery_state_change(self, state):
        logger.info(f"Battery state is now {state}")
        if state == BatteryState.CHARGING:
            self.nagbar.remove()
        elif state == BatteryState.DISCHARGING:
            self.on_percentage_change(self.battery.percentage_charged)
