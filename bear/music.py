from dataclasses import asdict, dataclass
import json
import logging
from os import remove
import re
from typing import Any, Callable, Dict, List, Optional

from gi.repository import GLib

from bear.bear import Bear, DebugView, bears
from bear.eww import EwwVariable
from bear.poke import DBUSServicePoke, MultiPropertiesPoke


logger = logging.getLogger(__name__)


class NoCurrentService(Exception):
    pass


MP2_BUS_NAME = "org.mpris.MediaPlayer2"
MP2_PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
MP2_PLAYER_OBJECT_PATH = "/org/mpris/MediaPlayer2"


class MPRISPlayerPropertiesPoke(MultiPropertiesPoke):
    players = DBUSServicePoke(match_on=MP2_BUS_NAME)
    interface_name = MP2_PLAYER_INTERFACE

    def __init__(self, property_names=None):
        super().__init__(property_names=property_names)
        self.registered_player_names: Dict[str, Any] = {}

    def register(self):
        super().register()
        for name in self.players.data["names"]:
            self.add_proxy(self.bus.get_proxy(name, MP2_PLAYER_OBJECT_PATH))

    def update(self):
        new_player_name = self.players.data.get("added_service")
        if new_player_name:
            logger.info(f"adding player {new_player_name}")
            self.add_proxy(self.bus.get_proxy(new_player_name, MP2_PLAYER_OBJECT_PATH))

        removed_player_name = self.players.data.get("removed_service")
        if removed_player_name:
            logger.info(f"removing player {removed_player_name}")
            self.remove_proxy(removed_player_name, MP2_PLAYER_OBJECT_PATH)


@bears.recruit
class MusicBear(Bear):
    name = "music"
    new_player = MPRISPlayerPropertiesPoke(
        property_names=["metadata", "playback_status"]
    )

    # debug = DebugView()


@dataclass
class TrackData:
    title: Optional[str]
    album: Optional[str]
    artists: List[str]
    art_url: Optional[str]
    playback_status: Optional[str]

    def as_json(self):
        return json.dumps(
            {
                "title": self.title,
                "artist": ", ".join(self.artists),
                "album": self.album,
                "art_url": self.art_url,
                "playback_status": self.playback_status,
            }
        )


class Player:
    def __init__(self, proxy):
        self.proxy = proxy
        self.listeners = []
        self.last_data: Optional[TrackData] = None

    @property
    def metadata(self):
        return self.proxy.Get(MP2_PLAYER_INTERFACE, "Metadata").unpack()

    def on_metadata_change(self, metadata: dict):
        logger.info("MPRIS metadata change received")
        track = TrackData(
            title=metadata.get("xesam:title", None),
            album=metadata.get("xesam:album", None),
            artists=metadata.get("xesam:artist", []),
            art_url=metadata.get("mpris:artUrl", None),
            playback_status=self.last_data.playback_status if self.last_data else None,
        )

        self.last_data = track

        for listener in self.listeners:
            listener(track)

    def on_playback_status_change(self, status: str):
        logger.info("MPRIS playback status change received")
        track = TrackData(
            title=self.last_data.title,
            album=self.last_data.album,
            artists=self.last_data.artists,
            art_url=self.last_data.art_url,
            playback_status=status.lower(),
        )

        self.last_data = track
        for listener in self.listeners:
            listener(track)

    def listen_for_changes(self):
        def listener(_, changed_props, __):
            if "Metadata" in changed_props:
                self.on_metadata_change(changed_props["Metadata"].unpack())
            if "PlaybackStatus" in changed_props:
                self.on_playback_status_change(changed_props["PlaybackStatus"].unpack())

        self.proxy.PropertiesChanged.connect(listener)

        # this ensures the metadata for initial players is communicated to
        # the views,wether the GLib loop is already running when this is called
        # or not
        GLib.idle_add(
            lambda: self.on_metadata_change(self.metadata),
            priority=GLib.PRIORITY_DEFAULT,
        )

    def register_listener(self, f: Callable[[TrackData], Any]):
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

        player.register_listener(self.on_player_change)
        player.listen_for_changes()
        self.players[name] = player

    def on_player_change(self, track: TrackData):
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

    def register_listener(self, f: Callable[[TrackData], Any]):
        self.listeners.append(f)


class MusicBear2(Bear):
    def __init__(self, bus, name: str, eww_track_variable: EwwVariable):
        super().__init__(bus, name)
        self.client = MPRISClient(bus)
        self.eww_track_variable = eww_track_variable

    def register(self):
        super().register()
        self.client.register_listener(self.on_player_change)
        self.client.register()

    def on_player_change(self, track: TrackData):
        logger.info("bear listening to: %s", track)
        self.eww_track_variable.set(track.as_json())
