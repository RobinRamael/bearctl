from dataclasses import asdict, dataclass
from functools import partial
import json
import logging
from os import remove
from pprint import pprint
import re
from typing import Any, Callable, Dict, Hashable, List, Optional
from urllib.parse import urlparse

from gi.repository import GLib

from bear.bear import Bear, DebugView, bears
from bear.eww import EwwJSONView, EwwVariable
from bear.poke import DBUSServiceProvider, MultiPoke, MultiProxyPoke, Poke, ProxyPoke


logger = logging.getLogger(__name__)


class NoCurrentService(Exception):
    pass


MP2_BUS_NAME = "org.mpris.MediaPlayer2"
MP2_PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
MP2_PLAYER_OBJECT_PATH = "/org/mpris/MediaPlayer2"


@dataclass
class PlayerData:
    title: Optional[str]
    album: Optional[str]
    artists: List[str]
    art_url: Optional[str]
    playback_status: Optional[str]

    @classmethod
    def from_props(cls, **props):
        metadata = props["metadata"]
        return cls(
            title=metadata.get("xesam:title", None),
            album=metadata.get("xesam:album", None),
            artists=metadata.get("xesam:artist", []),
            art_url=metadata.get("mpris:artUrl", None),
            playback_status=props["playback_status"].lower(),
        )

    @property
    def summary(self):
        if not self.artists:
            return self.title

        artist_part = f" - {self.artist_repr}"
        return f"{self.title}{artist_part}"

    @property
    def visible(self):
        return bool(self.title)

    @property
    def artist_repr(self):
        return ", ".join(self.artists)

    @property
    def art_path(self):
        if not self.art_url:
            return None

        return urlparse(self.art_url).path

    def as_dict(self):
        return {
            "title": self.title,
            "artist": self.artist_repr,
            "album": self.album,
            "art_path": self.art_path,
            "playback_status": self.playback_status,
            "summary": self.summary,
            "visible": self.visible,
        }


class MPRISPlayerPropertiesPoke(MultiProxyPoke):
    players = DBUSServiceProvider(match_on=MP2_BUS_NAME)
    interface_name = MP2_PLAYER_INTERFACE
    data_class = PlayerData.from_props
    property_names = ["metadata", "playback_status"]

    def create_subpoke(self, unique_name, service_name):
        return ProxyPoke(
            service_name=service_name,
            unique_name=unique_name,
            interface_name=self.interface_name,
            obj_path=MP2_PLAYER_OBJECT_PATH,
            property_names=self.property_names,
        )


@bears.recruit
class MusicBear(Bear):
    name = "music"

    players = MPRISPlayerPropertiesPoke()

    view = EwwJSONView("current_track", from_key="track_data")

    def get_extra_context(self):
        return {"track_data": self.players.data.as_dict() if self.players.data else {}}
