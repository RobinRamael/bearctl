import logging
import threading

import pulsectl

from bear.bear import Bear, DebugView, bears
from bear.poke import Poke

logger = logging.getLogger(__name__)


class VolumePoke(Poke):
    def register(self):
        self.pulse = pulsectl.Pulse("bear-volume")
        self._event = None

        def _on_event(ev):
            self._event = ev
            raise pulsectl.PulseLoopStop

        def _run_loop():
            self._event = None
            logger.info("Pulseaudio loop thread started...")
            while True:
                self.pulse.event_mask_set(pulsectl.PulseEventMaskEnum.sink)
                self.pulse.event_callback_set(_on_event)
                logger.debug("Listening for events...")
                self.pulse.event_listen(timeout=None)
                if not self._event:
                    break

                logger.debug("Stopped listening for a bit to handle event")

                self.on_event(self._event)
                self._event = None

            logger.info("Pulseaudio loop exited wihout event being passed.")

        threading.Thread(target=_run_loop, daemon=True).start()

    def on_event(self, ev):
        logger.debug(f"Received event from pulseaudio: %", ev)
        self.current_data = {"volume": self.pulse.sink_info(ev.index).volume.values[0]}
        self.poke()


@bears.recruit
class VolumeBear(Bear):
    name = "volume"
    volume = VolumePoke()
    debug = DebugView()
