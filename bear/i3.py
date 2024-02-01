import logging
import threading
from typing import Optional

from gi.repository import GLib
from i3ipc import Connection, Event

from bear.bear import Bear, WidgetBear
from bear.views import EwwVariable

logger = logging.getLogger()


class I3Bear(Bear):
    def __init__(
        self,
        *args,
        eww_title_var: EwwVariable,
        i3: Optional[Connection] = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.i3 = i3 or Connection()
        self.eww_title_var = eww_title_var

    def register(self):
        super().register()

        self.i3.on(Event.WINDOW_FOCUS, self.on_window_focus)

        def run_loop():
            logger.info("Starting i3 ipc loop")
            self.i3.main()

        threading.Thread(target=run_loop, daemon=True).start()

    def on_window_focus(self, _, event):
        window_title = event.ipc_data["container"]["window_properties"]["title"]
        self.eww_title_var.set(window_title)
