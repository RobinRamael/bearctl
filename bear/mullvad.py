import json
import logging
import subprocess
import threading
import time

from bear.bear import ActionableBear, DebugView, bears, dbus_method
from bear.eww import EwwPrefixView
from bear.poke import Poke

logger = logging.getLogger(__name__)


# states reported by `mullvad status --json`. "blocked" shows up when the
# tunnel is down but traffic is still being blocked by the kill switch.
CONNECTED = "connected"
CONNECTING = "connecting"
DISCONNECTED = "disconnected"
DISCONNECTING = "disconnecting"
BLOCKED = "blocked"
ERROR = "error"

ICON_NAMES = {
    CONNECTED: "MULLVAD_CONNECTED",
    CONNECTING: "MULLVAD_CONNECTING",
    DISCONNECTED: "MULLVAD_DISCONNECTED",
    DISCONNECTING: "MULLVAD_CONNECTING",
    BLOCKED: "MULLVAD_BLOCKED",
    ERROR: "MULLVAD_ERROR",
}


def poll_mullvad() -> dict:
    """Return a flat dict of mullvad state, merged straight into bear context."""
    try:
        result = subprocess.run(
            ["mullvad", "status", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        data = json.loads(result.stdout.decode())
    except FileNotFoundError:
        logger.error("mullvad executable not found")
        return {"state": ERROR, "hostname": None, "country": None, "city": None}
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("could not parse mullvad status: %s", e)
        return {"state": ERROR, "hostname": None, "country": None, "city": None}

    state = data.get("state", ERROR)

    # `details` is an object when (dis)connect(ing)/connected, but a plain
    # string (e.g. "nothing") when disconnected, so guard the lookups.
    details = data.get("details")
    location = details.get("location") if isinstance(details, dict) else None
    location = location or {}

    return {
        "state": state,
        "hostname": location.get("hostname"),
        "country": location.get("country"),
        "city": location.get("city"),
    }


class MullvadStatusPoke(Poke):
    """Reactive status source.

    Spawns one long-lived `mullvad status listen` and pokes whenever the daemon
    reports a transition, instead of polling on a fixed interval. `listen`
    doesn't speak JSON, so each header line is used purely as a change trigger
    and the structured status is re-read with `poll_mullvad()`.
    """

    def register(self):
        super().register()
        threading.Thread(target=self._listen, daemon=True).start()

    def get_initial_data(self):
        return poll_mullvad()

    def _listen(self):
        while True:
            try:
                proc = subprocess.Popen(
                    ["mullvad", "status", "listen"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                logger.error("mullvad executable not found; status will not update")
                return

            logger.debug("listening for mullvad state changes")
            while True:
                raw = proc.stdout.readline()
                if not raw:
                    break  # process exited

                # transitions start with a header line at column 0 (e.g.
                # "Connected", "Connecting"); indented lines are just details.
                line = raw.decode()
                if line and not line[0].isspace():
                    self._refresh()

            logger.warning("`mullvad status listen` exited, restarting in 1s")
            self._refresh()
            time.sleep(1)

    def _refresh(self):
        new_data = poll_mullvad()
        if new_data != self.current_data:
            self.current_data = new_data
            self.poke()


@bears.recruit
class MullvadBear(ActionableBear):
    name = "mullvad"

    status = MullvadStatusPoke()

    view = EwwPrefixView(var_names=["status", "icon_name", "location"])
    debug = DebugView()

    @property
    def connected(self) -> bool:
        return self.status.data["state"] == CONNECTED

    def get_extra_context(self):
        ctx = super().get_extra_context()
        data = self.status.data

        state = data["state"]
        ctx["status"] = state
        ctx["icon_name"] = ICON_NAMES.get(state, ICON_NAMES[ERROR])

        if state in (CONNECTED, CONNECTING) and data.get("hostname"):
            where = ", ".join(
                part for part in (data.get("city"), data.get("country")) if part
            )
            ctx["location"] = (
                f"{data['hostname']} ({where})" if where else data["hostname"]
            )
        else:
            ctx["location"] = ""

        return ctx

    @dbus_method()
    def connect(self):
        self._run("connect")

    @dbus_method()
    def disconnect(self):
        self._run("disconnect")

    @dbus_method()
    def toggle(self):
        self._run("disconnect" if self.connected else "connect")

    def _run(self, command: str):
        # run off the main loop so a slow daemon can't stall rendering. no need
        # to re-poll here: the resulting transition arrives via status listen.
        def target():
            logger.info("running `mullvad %s`", command)
            result = subprocess.run(
                ["mullvad", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode != 0:
                logger.error(
                    "`mullvad %s` failed: %s", command, result.stderr.decode().strip()
                )

        threading.Thread(target=target).start()

    def on_left_click(self):
        self.toggle()
