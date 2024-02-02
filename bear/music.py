from dataclasses import asdict, dataclass
import json
import logging
from typing import Any, Callable, List, Optional

from gi.repository import GLib

from bear.bear import Bear
from bear.views import EwwVariable


logger = logging.getLogger(__name__)


class NoCurrentService(Exception):
    pass


MP2_BUS_NAME = "org.mpris.MediaPlayer2"
MP2_PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
MP2_PLAYER_OBJECT_PATH = "/org/mpris/MediaPlayer2"


@dataclass
class TrackMetadata:
    title: Optional[str]
    album: Optional[str]
    artists: List[str]
    art_url: Optional[str]

    def as_json(self):
        return json.dumps(
            {
                "title": self.title,
                "artist": ", ".join(self.artists),
                "album": self.album,
                "art_url": self.art_url,
            }
        )


class Player:
    def __init__(self, proxy):
        self.proxy = proxy
        self.listeners = []

    @property
    def metadata(self):
        return self.proxy.Get(MP2_PLAYER_INTERFACE, "Metadata").unpack()

    def on_metadata_change(self, metadata: dict):
        logger.info("MPRIS metadata change received")
        track = TrackMetadata(
            title=metadata.get("xesam:title", None),
            album=metadata.get("xesam:album", None),
            artists=metadata.get("xesam:artist", []),
            art_url=metadata.get("mpris:artUrl", None),
        )

        for listener in self.listeners:
            listener(track)

    def listen_for_metadata_changes(self):
        def listener(_, changed_props, __):
            if "Metadata" in changed_props:
                self.on_metadata_change(changed_props["Metadata"].unpack())

        self.proxy.PropertiesChanged.connect(listener)

        # this ensures the metadata for initial players is communicated to
        # the views,wether the GLib loop is already running when this is called
        # or not
        GLib.idle_add(
            lambda: self.on_metadata_change(self.metadata),
            priority=GLib.PRIORITY_DEFAULT,
        )

    def register_metadata_listener(self, f: Callable[[TrackMetadata], Any]):
        self.listeners.append(f)


class MPRISClient:
    def __init__(self, bus):
        self.bus = bus
        self.players = {}
        self.listeners = []
        self.last_change = None

    def register(self):
        # are there already players running?
        self.find_registered_players()

        # and then listen for changes
        self.listen_for_player_changes()

    def find_registered_players(self):
        names = self.bus.get_proxy(
            "org.freedesktop.DBus", "/org/freedesktop/DBus"
        ).ListNames()

        for name in names:
            if name.startswith(MP2_BUS_NAME):
                self.on_new_player(name)

    def listen_for_player_changes(self):
        # completely unintuitively, listening for wether the name owner changed
        # is how we figure out wether new players appear and already existing
        # ones dissappear: new ones have the old empty and dissappearing ones the new
        # empty.
        def on_owner_change(bus_name, old, new):
            assert not (old and new), "Player changed owner?!"

            if bus_name.startswith(MP2_BUS_NAME) and new:
                if new:
                    self.on_new_player(bus_name)
                if old:  # does this work?
                    self.on_player_loss(bus_name)

        self.bus.get_proxy(
            "org.freedesktop.DBus", "/org/freedesktop/DBus"
        ).NameOwnerChanged.connect(on_owner_change)

    def on_new_player(self, name):
        proxy = self.bus.get_proxy(name, MP2_PLAYER_OBJECT_PATH)
        logger.info("Found player %s", name)
        player = Player(proxy)

        player.register_metadata_listener(self.on_metadata_change)
        player.listen_for_metadata_changes()
        self.players[name] = player

    def on_metadata_change(self, track: TrackMetadata):
        logger.debug("Track changed: %s", track)
        if track != self.last_change:
            self.last_change = track
            for listener in self.listeners:
                listener(track)
        else:
            logger.info("Is duplicate, ignoring...")

    def on_player_loss(self, name):
        try:
            self.players.pop(name)
            logger.info("Removed %s from tracked players", name)
        except KeyError:
            logger.warning(
                "Did not recognize player with name %s when it dissappeared", name
            )

    def register_metadata_listener(self, f: Callable[[TrackMetadata], Any]):
        self.listeners.append(f)


class MusicBear(Bear):
    def __init__(self, bus, name: str, eww_track_variable: EwwVariable):
        super().__init__(bus, name)
        self.client = MPRISClient(bus)
        self.eww_track_variable = eww_track_variable

    def register(self):
        super().register()
        self.client.register_metadata_listener(self.on_metadata_change)
        self.client.register()

    def on_metadata_change(self, track: TrackMetadata):
        logger.info("bear listening to: %s", track)
        self.eww_track_variable.set(track.as_json())
