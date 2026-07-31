"""Hour-clock widget for the sjebbestie finance app on bmo.

Polls sjebbestie's token-guarded timer-status endpoint and pushes the running
timer's elapsed time + project into eww; left-click opens the app in the browser.
The endpoint is reachable on the LAN as bmo.local and off-LAN over Tailscale.
"""

import datetime
import json
import logging
import os
import socket
import subprocess
import threading
import time
import urllib.request

from bear.bear import ActionableBear, DebugView, bears
from bear.eww import EwwPrefixView
from bear.poke import Poke

logger = logging.getLogger(__name__)


LAN_HOST = "bmo.local"
LAN_BASE = f"http://{LAN_HOST}"
# bmo's Tailscale IP (MagicDNS off, so bmo.local doesn't resolve off-LAN).
TS_BASE = "http://100.91.85.116"
STATUS_PATH = "/sjebbestie/api/time-tracker/status/"
APP_PATH = "/sjebbestie/"

# The status poll is throttled to this; the elapsed clock still ticks every 1s.
FETCH_INTERVAL = 5

TOKEN_FILE = os.path.expanduser("~/.config/sjebbestie/timer-token")

IDLE = {"running": False, "project": "", "elapsed": ""}


def read_token() -> str:
    """Shared secret for the status endpoint: env override, else the 0600 file."""
    token = os.environ.get("SJEBBESTIE_TIMER_TOKEN")
    if token:
        return token.strip()
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except OSError:
        logger.warning("no sjebbestie timer token at %s", TOKEN_FILE)
        return ""


def resolve_base() -> str:
    """LAN host when it's reachable (we're home), else the Tailscale IP."""
    try:
        socket.create_connection((LAN_HOST, 80), timeout=1).close()
        return LAN_BASE
    except OSError:
        return TS_BASE


def parse_status(data: dict) -> dict:
    """API JSON -> {running, project, started_at(epoch|None)}, tolerant of gaps."""
    running = bool(data.get("running"))
    started_at = None
    iso = data.get("started_at")
    if running and iso:
        try:
            started_at = datetime.datetime.fromisoformat(iso).timestamp()
        except ValueError:
            logger.warning("could not parse started_at %r", iso)
            running = False
    return {
        "running": running,
        "project": data.get("project_name") or "",
        "started_at": started_at,
    }


def format_elapsed(started_at: float | None) -> str:
    """H:MM:SS since started_at; empty when idle."""
    if not started_at:
        return ""
    elapsed = int(time.time() - started_at)
    if elapsed < 0:
        return ""
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def fetch_status() -> dict:
    """GET the timer status with the token header; any failure -> idle."""
    token = read_token()
    if not token:
        return {"running": False, "project": "", "started_at": None}
    url = resolve_base() + STATUS_PATH
    try:
        req = urllib.request.Request(url, headers={"X-Timer-Token": token})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.load(resp)
    except Exception as e:
        logger.debug("sjebbestie status fetch failed: %s", e)
        return {"running": False, "project": "", "started_at": None}
    return parse_status(data)


def open_app() -> None:
    """Open the app in the default browser.

    The bearctl service PATH has neither a browser nor xdg-open, and in a sway
    session xdg-open finds a browser by scanning PATH for its binary (not via the
    .desktop association), so give the launch a PATH that has both. Detach it so
    it outlives this call.
    """
    env = dict(os.environ)
    extra = [
        os.path.expanduser("~/.nix-profile/bin"),
        f"/etc/profiles/per-user/{os.environ.get('USER', 'robin')}/bin",
        "/run/current-system/sw/bin",
    ]
    env["PATH"] = ":".join(extra + [env.get("PATH", "")])
    url = resolve_base() + APP_PATH
    logger.info("opening %s", url)
    subprocess.Popen(
        ["xdg-open", url],
        env=env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class SjebbestieTimerPoke(Poke):
    """Ticks the elapsed clock every second, off the GLib main loop.

    Re-fetches the status endpoint only every FETCH_INTERVAL seconds (the clock
    itself is computed locally from the cached start time), and pokes bears only
    when a display value actually changes -- so an idle timer causes no re-renders
    and a running one ticks once per second.
    """

    def register(self):
        super().register()
        threading.Thread(target=self._run, daemon=True).start()

    def get_initial_data(self):
        return dict(IDLE)

    def _run(self):
        status = {"running": False, "project": "", "started_at": None}
        last_fetch = 0.0
        while True:
            now = time.time()
            if now - last_fetch >= FETCH_INTERVAL:
                status = fetch_status()
                last_fetch = now

            new_data = {
                "running": status["running"],
                "project": status["project"],
                "elapsed": format_elapsed(status["started_at"]),
            }
            if new_data != self.current_data:
                self.current_data = new_data
                self.poke()

            time.sleep(1)


@bears.recruit
class SjebbestieBear(ActionableBear):
    name = "sjebbestie"

    timer = SjebbestieTimerPoke()

    view = EwwPrefixView(var_names=["running", "project", "elapsed"])
    debug = DebugView()

    def on_left_click(self):
        open_app()
