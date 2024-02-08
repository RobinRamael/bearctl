from datetime import datetime
import json
import logging
import os
import subprocess
import sys
from threading import Thread
from typing import Any, Callable, Dict, List, Optional

from gi.repository import GLib

from bear.bear import Bear, BearView

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

    def init(self):
        pass

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

        self.executable_var = self.var("BEARCTL")
        self.executable_var.set(location)

        subprocess.run(["eww", "update", f"BEARCTL={location}"])
        logger.info("Bootstrapped %s into eww variable", location)

    def listen_for_reloads(self):
        self.listener.listen()

    def update(self, **kwargs):
        if not kwargs:
            logger.warning("Empty update passed to eww, ignoring.")
            return

        variables = []
        for k, v in kwargs.items():
            if isinstance(v, bool):
                v = str(v).lower()
            assignment = f"{k}={v}"
            variables.append(assignment)

        logger.debug("Updating: %s", ", ".join(variables))
        subprocess.run(["eww", "update", *variables])

    def var(self, name):
        v = EwwVariable(self, name)
        self.listener.add_handler(v.refresh)
        return v


eww = EwwController()


class EwwVariable:
    def __init__(self, eww, name):
        self.eww = eww
        self.name = name
        self.last_value = None
        self.set_at_least_once = False

    def set(self, value):
        self._set_no_update(value)
        self.eww.update(**{self.name: value})

    def _set_no_update(self, value):
        self.set_at_least_once = True
        self.last_value = value

    def refresh(self):
        if self.set_at_least_once:
            logger.debug("Refreshing eww variable %s=%s", self.name, self.last_value)
            self.set(self.last_value)

        else:
            logger.info("%s was never set, not refreshing", self.name)


class EwwPrefixView(BearView):
    variables: Dict[str, EwwVariable]

    def __init__(
        self, prefix: Optional[str] = None, var_names: Optional[List[str]] = None
    ):
        self.prefix = prefix
        logger.debug("setting prefix to %s", prefix)
        self.eww: EwwController = eww or EwwController()
        if not var_names:
            raise TypeError("Missing argument var_names")
        self.var_names = var_names

    def register(self, bear: Bear):
        super().register(bear)
        if not self.prefix:
            logger.debug("setting prefix to %s", bear.name)
            self.prefix = bear.name

        self.variables = {
            name: eww.var(f"{self.prefix}_{name}") for name in self.var_names
        }

    def render(self, context: Dict[str, Any]):
        update = {}
        for name, variable in self.variables.items():
            if name in context:
                new_value = context[name]
                variable._set_no_update(new_value)
                update[variable.name] = new_value

        self.eww.update(**update)
