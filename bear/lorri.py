import json
import logging
import subprocess
import threading
import time

from dasbus.connection import SessionMessageBus
from gi.repository import GLib

from bear.bear import LabelBear
from bear.icons import Icons
from bear.views import BlockState

logger = logging.getLogger(__name__)


# the lorri stream-events command also send the last few
# (currently three but who knows?) events immediately. We want to
# ignore those. Since it's unlikely that the user will trigger a
# lorri event with 0.5 seconds, that seems like a good choice.
INITIAL_HOLDOFF_TIME = 0.5


class LorriBear(LabelBear):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._last_events = {}

    def register(self):
        def loop():
            proc = subprocess.Popen(
                ["lorri", "internal", "stream-events"], stdout=subprocess.PIPE
            )
            t_0 = time.time()
            while True:
                line = proc.stdout.readline()

                # see INITIAL_HOLDOFF_TIME comment
                if time.time() - t_0 < INITIAL_HOLDOFF_TIME:
                    continue

                data = json.loads(line)
                GLib.idle_add(self.handle_event, data)

        threading.Thread(target=loop, daemon=True).start()

    def handle_event(self, data):

        assert len(data.keys()) == 1

        status, info = list(data.items())[0]

        triggering_file = info["nix_file"]

        # if we receive the same event for the same triggering file more than
        # once in a row, we can ignore it for our lowly notification purposes.
        # Lorri often triggers things twice because of vim save weirdness
        if triggering_file in self._last_events:
            event = self._last_events[triggering_file]
            if event == status:
                logger.debug(f"{status} ignored for {triggering_file}")
                return

        self._last_events[triggering_file] = status

        if status == "Started":
            self.handle_started(info)
        elif status == "Completed":
            self.handle_completed(info)
        elif status == "Failure":
            self.handle_failure(info)
        else:
            logger.warning(f"Received unknown status {status}, skipping.")

    def handle_started(self, info):
        logger.info(f"Lorri 'Started' event rcvd for {info['nix_file']}")
        self.view.update_simple_icon(Icons.TROWEL_BRICKS, BlockState.warning)

    def handle_completed(self, info):
        logger.info(f"Lorri 'Completed' event rcvd for {info['nix_file']}")
        self.view.blink_simple_icon(
            Icons.TROWEL_BRICKS, BlockState.good, Icons.TROWEL, BlockState.idle
        )

    def handle_failure(self, info):
        logger.info(f"Lorri 'Failure' event rcvd for {info['nix_file']}")
        self.view.blink_simple_icon(
            Icons.TROWEL_BRICKS, BlockState.error, Icons.TROWEL, BlockState.idle, 2
        )

    def initialize_view(self):
        self.view.update_simple_icon(Icons.TROWEL, BlockState.idle)
