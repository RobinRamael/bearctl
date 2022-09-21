import logging
import subprocess
import threading
import time

from gi.repository import GLib

from bear.bear import LabelBear, dbus_method
from bear.icons import Icons
from bear.views import BlockState

logger = logging.getLogger(__name__)


class DPMSPollThread(threading.Thread):
    def __init__(self, dpms_bear, interval):
        super().__init__(daemon=True)
        self.dpms_bear = dpms_bear
        self.interval = interval

    def run(self):
        while True:
            time.sleep(self.interval)
            logger.debug("Polling dpms")
            self.dpms_bear.update_label()


class DPMSBear(LabelBear):
    def __init__(self, *args, poll_interval=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.poll_interval = poll_interval

    def is_dpms_enabled(self):
        proc = subprocess.run(["xset", "q"], check=True, stdout=subprocess.PIPE)

        for line in proc.stdout.decode().split("\n")[::-1]:
            if "DPMS is" in line:
                line = line.strip()
                if line == "DPMS is Disabled":
                    return False
                elif line == "DPMS is Enabled":
                    return True
                else:
                    raise Exception("Could not parse xset output")

        else:
            raise Exception("Unable to determine DPMS state, was not in xset output")

    def register(self):
        super().register()

        DPMSPollThread(self, self.poll_interval).start()

    def initialize_view(self):
        self.update_label()

    def update_label(self):
        if self.is_dpms_enabled():
            self.update_view("on", "", BlockState.idle)
        else:
            self.update_view("off", "", BlockState.warning)

    def enable_dpms(self):
        logger.info("enabling dpms")
        subprocess.run(["xset", "+dpms"], check=True)

    def disable_dpms(self):
        logger.info("disabling dpms")
        subprocess.run(["xset", "s", "off", "-dpms"], check=True)

    @dbus_method()
    def toggle(self):
        if self.is_dpms_enabled():
            self.disable_dpms()
        else:
            self.enable_dpms()

        self.update_label()

    def on_right_click(self):
        self.toggle()
