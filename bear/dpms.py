from collections import namedtuple
import logging
import subprocess

from gi.repository import GLib

from bear.bear import ActionableBear, bears, dbus_method
from bear.eww import EwwPrefixView
from bear.poke import PollingPoke
from bear.systemd import ServiceStates

logger = logging.getLogger(__name__)


class DPMSPoke(PollingPoke):
    single_value = False

    def poll(self):
        proc = subprocess.run(["xset", "q"], check=True, stdout=subprocess.PIPE)

        for line in proc.stdout.decode().split("\n")[::-1]:
            if "DPMS is" in line:
                line = line.strip()
                if line == "DPMS is Disabled":
                    return {"enabled": False}
                elif line == "DPMS is Enabled":
                    return {"enabled": True}
                else:
                    raise Exception("Could not parse xset output")

        else:
            raise Exception("Unable to determine DPMS state, was not in xset output")

    def enable(self):
        logger.debug("enabling dpms")

        def _enable():
            subprocess.run(["xset", "+dpms"], check=True)
            logger.info("dpms successfully enabled")

        GLib.idle_add(_enable, priority=GLib.PRIORITY_DEFAULT)

        self.set_data({"enabled": True})

    def disable(self):
        logger.debug("disabling dpms")

        def _disable():
            subprocess.run(["xset", "s", "off", "-dpms"], check=True)
            logger.info("dpms successfully enabled")

        GLib.idle_add(_disable, priority=GLib.PRIORITY_DEFAULT)

        self.set_data({"enabled": False})


@bears.recruit
class DPMSBear(ActionableBear):
    name = "dpms"
    dpms = DPMSPoke(interval=5)
    view = EwwPrefixView(var_names=["state"])

    def get_extra_context(self):
        return {
            "state": ServiceStates.ENABLED
            if self.dpms.data["enabled"]
            else ServiceStates.DISABLED
        }

    @dbus_method()
    def toggle(self):
        if self.dpms.data["enabled"]:
            self.dpms.disable()
        else:
            self.dpms.enable()

    def on_left_click(self):
        self.toggle()
