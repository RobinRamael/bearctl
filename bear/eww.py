from datetime import datetime
import logging
import os
import subprocess
import sys
from threading import Thread
from typing import Any, Callable, List

from gi.repository import GLib

from bear.views import BearLabel

EWW_RELOAD_MATCH = "Reloaded config successfully"

logger = logging.getLogger(__name__)


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

            try:
                # flush out lines that were generated before we started listening
                if datetime.fromisoformat(line.strip().split()[0]) < listen_start:
                    continue

                if EWW_RELOAD_MATCH in line:
                    self.on_reload()
            except Exception as e:
                logger.debug(
                    "error while parsing eww output, ignoring and waiting for next line...",
                    exc_info=True,
                )

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


UPOWER_DEVICE_INTERFACE = "org.freedesktop.UPower.Device"
UPOWER_BUS_NAME = "org.freedesktop.UPower"
UPOWER_DEVICE_PATH_PREFIX = "/org/freedesktop/UPower/devices/"




# NOT_SET = object()

# class Property:
#     def __init__(self, name, initial=NOT_SET):
#         self.name = name
#         self.initial = initial


# class PropertyListener:
#     def __init__(self, proxy, properties):
#         self.proxy = proxy
#         self.properties = properties
#         self.last_data = {}

#     def register(self):
#         self.proxy.PropertiesChanged.connect(self.handler)

#     def handler(self, _, changed, __):

#         changed_props = {}

#         for prop in self.properties:
#             if prop.name in changed:
#                 prop.name


# class BatteryPropertyListener:

#     proxy = Proxy("org.freedesktop.UPower", "/org/freedesktop/UPower/devices/DisplayDevice")
#     properties = [Property("percentage")]

# class EwwDBusAgent:
#     def __init__(self, proxy, property_name, ):
