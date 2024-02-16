import logging
import threading

import pulsectl

from bear.bear import Bear, DebugView, bears
from bear.eww import EwwPrefixView, EwwSingleVariableView
from bear.poke import Poke

logger = logging.getLogger(__name__)


class VolumePoke(Poke):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pulse = pulsectl.Pulse("bear-volume")

    def register(self, parent):
        super().register(parent)

        self._event = None

        # the pulsectl library doens't allow us to do other pulseaudio calls
        # from other threads while its loop is running, so when an event is
        # triggered, we set it on the object, stop the loop, handle the event
        # and start the loop again. weird, but since it's ok-ish if we miss an
        # event, it's probably Good Enough?
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
        if ev.t == pulsectl.PulseEventTypeEnum.remove:
            sink = self.pulse.sink_list()[0]
        else:
            sink = self.pulse.sink_info(ev.index)

        self.current_data = {"volume": sink.volume.values[0]}
        self.poke()

    def get_initial_data(self):
        try:
            return {"volume": self.pulse.sink_list()[0].volume.values[0]}
        except IndexError:
            logger.warning("No sinks found to display volume for")
            return {"volume": 0}


@bears.recruit
class VolumeBear(Bear):
    name = "volume"
    volume = VolumePoke()
    eww = EwwPrefixView(var_names=["percentage", "icon_name"])

    def get_extra_context(self):
        ctx = super().get_extra_context()
        percentage = round(self.volume.data["volume"] * 100)
        ctx["percentage"] = percentage
        if percentage > 0:
            icon_idx = min(2, int(percentage // (100 / 3)))
            ctx["icon_name"] = f"VOLUME_ICON_{icon_idx}"
        else:
            ctx["icon_name"] = "VOLUME_MUTED_ICON"

        return ctx
