import logging
import threading
from typing import Any, Callable, Optional

import i3ipc

from bear.bear import Bear, bears
from bear.eww import EwwPrefixView
from bear.poke import Poke

logger = logging.getLogger()


class _I3:
    connection: Optional[i3ipc.Connection]

    def __init__(self):
        self.connection = None
        self.listened_to = False
        self.running = False

    def get_connection(self) -> i3ipc.Connection:
        if not self.connection:
            self.connection = i3ipc.Connection()
        return self.connection

    def on(self, event_type, handler):
        conn = self.get_connection()
        conn.on(event_type, handler)
        self.listened_to = True

    def ensure_listening(self):
        if not self.listened_to:
            logger.info("Not starting i3 loop because no handlers were set")
            return

        if self.running:
            logger.debug("I3 loop already running")
            return

        def run_loop():
            logger.info("Starting i3 ipc loop")
            self.get_connection().main()

        threading.Thread(target=run_loop, daemon=True).start()
        self.running = True


i3 = _I3()
sway = i3


class I3Poke(Poke):
    event_type: i3ipc.Event

    def __init__(
        self,
        *args,
        i3: Optional[i3ipc.Connection] = None,
        event_type=None,
        data_from_event: Optional[Callable[[i3ipc.Event], Any]] = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.data_transform = data_from_event

        if event_type:
            self.event_type = event_type

    def register(self):
        super().register()
        logger.debug("Registered i3 poke")

        i3.on(self.event_type, self.listener)
        i3.ensure_listening()

    def data_from_event(self, event):
        if self.data_transform:
            return self.data_transform(event)
        else:
            raise TypeError(
                "No way to get data from i3 event, override data_from_event "
                "or pass the kwarg into the constructor"
            )

    def listener(self, _, event):
        logger.debug("i3 listener triggered")
        new_data = self.data_from_event(event)

        if self.current_data != new_data:
            self.current_data = new_data
            self.poke()


def get_title(ev):
    return {
        "title": ev.ipc_data["container"]["name"],
    }


@bears.recruit
class FocusedWindowBear(Bear):
    name = "focused"

    i3_focus = I3Poke(event_type=i3ipc.Event.WINDOW, data_from_event=get_title)

    view = EwwPrefixView(var_names=["title"])
