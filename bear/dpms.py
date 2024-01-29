import logging
import subprocess
import threading
import time

from gi.repository import GLib

from bear.bear import ActionableBear, LabelBear, dbus_method
from bear.icons import Icons
from bear.views import BlockState, EwwServiceWidget

logger = logging.getLogger(__name__)


class DPMSBear(ActionableBear):
    def __init__(self, *args, widget: EwwServiceWidget, interval=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.poll_interval = interval
        self._was_enabled = None
        self.widget = widget

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

        GLib.timeout_add_seconds(
            priority=GLib.PRIORITY_DEFAULT,
            function=self.update_label,
            interval=self.poll_interval,
        )
        logger.debug("DPMS polling enabled")

    def initialize_view(self):
        self.update_label()

    def update_label_enabled(self):
        self.widget.set_enabled()

    def update_label_disabled(self):
        self.widget.set_disabled()

    def update_label(self):
        logger.debug("polling dpms")
        enabled = self.is_dpms_enabled()

        if self._was_enabled is None or enabled != self._was_enabled:
            logger.info(f"updating label enabled={enabled}, cache={self._was_enabled}")
            if enabled:
                self.update_label_enabled()
            else:
                self.update_label_disabled()

        else:
            logger.debug(
                f"not updating label from poll thread: enabled={enabled}, cache={self._was_enabled}"
            )

        self._was_enabled = enabled

    def enable_dpms(self):
        logger.info("enabling dpms")
        subprocess.run(["xset", "+dpms"], check=True)
        self.update_label_enabled()

    def disable_dpms(self):
        logger.info("disabling dpms")
        subprocess.run(["xset", "s", "off", "-dpms"], check=True)
        self.update_label_disabled()

    @dbus_method()
    def toggle(self):
        def _toggle():
            if self.is_dpms_enabled():
                self.disable_dpms()
            else:
                self.enable_dpms()

        GLib.idle_add(_toggle, priority=GLib.PRIORITY_HIGH_IDLE)

    def on_left_click(self):
        self.toggle()
