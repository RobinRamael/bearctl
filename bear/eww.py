from datetime import datetime
import json
import logging
import os
import subprocess
import sys
from threading import Thread
import time
from typing import Any, Callable, Dict, List, Optional

from bear.bear import Bear, BearView
from bear.utils import in_debug_mode, to_full_dict

EWW_RELOAD_MATCH = "Reloaded config successfully"

logger = logging.getLogger(__name__)


class EwwLogsListener:
    def __init__(self, executable, config_path):
        self.executable = executable
        self.handlers: List[Callable[[], Any]] = []
        self.config_path = config_path

    def listen(self):
        Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        if self.config_path:
            cmd = [self.executable, "-c", self.config_path, "logs"]
        else:
            cmd = [self.executable, "logs"]

        version = subprocess.run(
            [self.executable, "--version"], stdout=subprocess.PIPE
        ).stdout.decode()

        logger.info(f"Using {version} in {self.executable}")

        cmd_str = " ".join(cmd)

        logger.info(f"Listening for eww reloads with '{cmd_str}'")

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)

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
    def __init__(self, dry_run=False):
        try:
            self.executable: str = os.environ["EWW_EXECUTABLE"]
        except KeyError:
            self.executable = "eww"

        self.config_path = os.environ.get("EWW_CONFIG", None)

        self.listener = EwwLogsListener(self.executable, self.config_path)

        self.dry_run = dry_run

    def bootstrap(self):
        logger.info(f"Using eww executable {self.executable}")
        if self.config_path:
            logger.info(f"Using eww config dir {self.config_path}")
        else:
            logger.info(f"Using default eww config dir")

        try:
            executable_location = os.environ["BEARCTL_EXECUTABLE"]
            logger.debug("Found %s in env var", executable_location)
        except KeyError:
            executable_location = sys.argv[0]
            logger.debug("Found %s in sys.args", executable_location)

        if not os.access(executable_location, os.X_OK):
            logger.warning("%s is not executable, skipping...", executable_location)
            return

        if in_debug_mode():
            command = f"DEBUG=1 {executable_location}"
        else:
            command = executable_location

        self.executable_var = self.var("BEARCTL")
        logger.info("fSetting eww variable BEARCTL={command}")
        self.executable_var.set(command)

        self.debug_mode_var = self.var("DEBUG")
        debug_enabled = str(in_debug_mode()).lower()
        logger.info(f"Setting eww variable DEBUG={debug_enabled}")
        self.debug_mode_var.set(debug_enabled)

        self.eww_command = self.var("EWW_CMD")
        eww_cmd = f"{self.executable} -c {self.config_path}"
        logger.info(f"Setting eww variable EWW_CMD={eww_cmd}")
        self.eww_command.set(eww_cmd)

        logger.info("Bootstrapped %s into eww variable", executable_location)

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

        self.run("update", *variables)

    def run(self, *args):
        if self.dry_run:
            logger.debug("eww dry run set to True, not actually running eww executable")
            return

        if self.config_path:
            command = [self.executable, "-c", self.config_path, *args]
        else:
            command = [self.executable, *args]

        t_0 = time.time()

        subprocess.run(command)

        t_e = time.time()

        command_str = " ".join(args)

        logger.debug(f"Ran eww command '{command_str}' in {t_e - t_0} seconds")

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


class EwwJSONView(BearView):
    def __init__(self, var_name, from_key=None):
        self.var_name = var_name
        self.eww: EwwController = eww or EwwController()
        self.from_key = from_key

    def register(self, bear: Bear):
        super().register(bear)
        self.var = self.eww.var(self.var_name)

    def render(self, context: Any):
        if self.from_key:
            value = context[self.from_key]
        else:
            value = context

        self.var.set(json.dumps(to_full_dict(value)))


class EwwWindowView(EwwJSONView):

    def __init__(self, var_name, window_name, from_key=None, start_opened=False):
        super().__init__(var_name, from_key)

        self.window_name = window_name

        self.visible = self.eww.var(f"{window_name}-window-visible")
        self.visible.set(start_opened)

    def open(self):
        self.visible.set(True)

    def close(self):
        pass
        self.visible.set(False)
