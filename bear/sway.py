import logging
import threading
from typing import Any, Callable, List, Optional

from i3ipc import (
    Con as I3Container,
    Connection as I3Connection,
    Event as I3Event,
    WindowEvent as I3WindowEvent,
    WorkspaceEvent,
)

from bear.bear import Bear, DebugView, bears, dbus_method
from bear.eww import EwwJSONView, EwwPrefixView
from bear.poke import Poke

logger = logging.getLogger(__name__)


class _I3:
    connection: I3Connection

    def __init__(self):
        self.connection = None
        self.handlers = set()
        self.running = False

    def get_connection(self) -> I3Connection:
        if not self.connection:
            self.connection = I3Connection()
        return self.connection

    def on(self, event_type, handler):
        conn = self.get_connection()
        conn.on(event_type, handler)
        self.handlers.add(handler)

    def off(self, handler):
        conn = self.get_connection()
        conn.off(handler)
        self.handlers.remove(handler)

    def command(self, s):
        conn = self.get_connection()
        conn.command(s)

    def ensure_listening(self):
        if not self.handlers:
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
    event_types: List[I3Event] = []

    def __init__(
        self,
        *args,
        event_types=None,
        data_from_event: Optional[Callable[[I3Event], Any]] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.data_transform = data_from_event

        if event_types:
            self.event_types = event_types

    def register(self):
        super().register()
        logger.debug("Registered i3 poke")

        for event_type in self.event_types:
            i3.on(event_type, self.listener)

    def post_init(self):
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
    if ev.change == "init":
        logger.debug("init workspace event received")
        return {"title": ""}

    if ev.change == "close":
        logger.debug("close window event received")
        return {"title": ""}

    logger.debug("change window event received")
    return {
        "title": ev.ipc_data["container"]["name"],
    }


@bears.recruit
class FocusedWindowBear(Bear):
    name = "focused"

    i3_focus = I3Poke(
        event_types=[I3Event.WINDOW, I3Event.WORKSPACE_INIT], data_from_event=get_title
    )

    view = EwwPrefixView(var_names=["title"])


class I3ActiveWorkspacesPoke(I3Poke):
    event_types = [
        I3Event.WORKSPACE_INIT,
        I3Event.WORKSPACE_EMPTY,
    ]

    def get_initial_data(self):
        workspaces = sway.get_connection().get_workspaces()

        return {"workspaces": {w.ipc_data["num"] for w in workspaces}}

    def listener(self, _, event: WorkspaceEvent):
        ws = event.ipc_data["current"]["num"]

        if event.change == "empty":
            self.current_data["workspaces"].remove(ws)

        elif event.change == "init":
            self.current_data["workspaces"].add(ws)

        else:
            raise Exception(f"Unhandled event type: {event.change}")

        self.poke()


class I3FocusedWorkspacePoke(I3Poke):
    event_types = [I3Event.WORKSPACE_FOCUS]

    def get_initial_data(self):
        workspaces = sway.get_connection().get_workspaces()

        return {
            "focused": next(
                (ws.ipc_data["num"] for ws in workspaces if ws.ipc_data["focused"]),
                None,
            )
        }

    def data_from_event(self, event):
        return {"focused": event.ipc_data["current"]["num"]}


def get_urgent_workspace(ev):
    return {"urgent": ev.ipc_data["current"]["num"]}


class I3UrgentWorkspacePoke(I3Poke):
    event_types = [I3Event.WORKSPACE_URGENT, I3Event.WORKSPACE_FOCUS]
    initial = {"urgent": None, "focused": None}

    def listener(self, _, event):
        if event.change == "urgent":
            urgent_ws = event.ipc_data["current"]["num"]
            if urgent_ws != self.current_data["focused"]:
                self.current_data["urgent"] = urgent_ws
            self.poke()
        else:
            if event.change == "focus":
                focused_ws = event.ipc_data["current"]["num"]
                if focused_ws == self.current_data["urgent"]:
                    self.current_data["urgent"] = None
                    self.poke()
                self.current_data["focused"] = focused_ws

    def get_data_dict(self):
        return {"urgent": self.current_data["urgent"]}


@bears.recruit
class WorkspaceBear(Bear):
    name = "workspace"
    # current_mode = I3Poke(event_types=[I3Event.MODE])

    focused = I3FocusedWorkspacePoke()
    urgent = I3UrgentWorkspacePoke()

    workspaces = I3ActiveWorkspacesPoke()

    view = EwwJSONView(var_name="sway_workspaces", from_key="workspaces")

    def get_extra_context(self):
        ws_data = []

        for ws_num in sorted(list(self.workspaces.data["workspaces"])):
            ws_data.append(
                {
                    "index": ws_num,
                    "focused": ws_num == self.focused.data["focused"],
                    "urgent": ws_num == self.urgent.data["urgent"],
                }
            )

        return {"workspaces": ws_data}


class WorkspaceURLOpener:
    def __init__(self):
        self._current_container: Optional[I3Container] = None
        self._waiting_for_window = False

        self._match_to_workspace: dict[str, int] = {}

    def register_handler(self):
        sway.on(I3Event.WINDOW, self.handle_opened)
        sway.ensure_listening()

    def unregister_handler(self):
        sway.off(self.handle_opened)

    def handle_opened(self, _, event: I3WindowEvent):
        if not self._match_to_workspace:
            logger.debug("Opener isn't waiting for anything, skipping.")
            return

        if (
            not hasattr(event.container, "app_id")
            or event.container.app_id != "firefox"
        ):
            logger.debug("Event was not on firefox window, skipping.")
            return

        if not event.change == "title":
            logger.debug(f"Event was not title change, but {event.change}, skipping.")
            return

        for match in list(self._match_to_workspace.keys()):
            if match in event.ipc_data["container"]["name"]:
                logger.debug(
                    f"Matched '{match}' with new title {event.ipc_data['container']['name']}"
                )
                ws = self._match_to_workspace[match]
                logger.info(f"Moving container to workspace {ws}")
                event.container.command(f"move to workspace {ws}")
                self._match_to_workspace.pop(match)  # remove from dict

        if not self._match_to_workspace:
            logger.debug("Match dict empty again, unregistering handler")
            self.unregister_handler()

    def open_firefox_window_in(self, url: str, workspace: int, title_match: str):
        logger.debug(f"Opening {url} in firefox")

        if not self._match_to_workspace:
            logger.debug("Match dict no longer empty, registering handler")
            self.register_handler()

        self._match_to_workspace[title_match] = workspace
        sway.command(f"exec firefox --new-window {url}")


@bears.recruit
class OpenerBear(Bear):
    name = "opener"

    workspace_opener = WorkspaceURLOpener()

    @dbus_method(str, int, str)
    def open_url_in_workspace(self, url: str, workspace: int, title_match: str):
        logger.info(
            f"dbus called opener.open_url_in_workspace({url}, {workspace}, {title_match})"
        )
        self.workspace_opener.open_firefox_window_in(url, workspace, title_match)
