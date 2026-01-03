from dataclasses import dataclass
import logging

from dataclasses_json import dataclass_json
import humanize
import transmission_rpc
from transmission_rpc.torrent import Status

from bear.bear import DebugView, bears
from bear.bear import Bear
from bear.eww import EwwJSONView
from bear.poke import PollingPoke

logger = logging.getLogger(__name__)


@dataclass_json
@dataclass
class Torrent:
    name: str
    progress: float
    eta_s: str

    rate_upload: int
    rate_download: int


class TransmissionPoke(PollingPoke):

    def poll(self):

        torrent_data = []

        (
            total_upspeed,
            total_downspeed,
            downloading_count,
            seeding_count,
            total_count,
        ) = (0, 0, 0, 0, 0)

        try:
            client = transmission_rpc.Client()
            torrents = client.get_torrents()
            for t in torrents:
                total_downspeed += t.rate_download
                total_upspeed += t.rate_upload

                total_count += 1

                if t.status in (Status.SEEDING, Status.SEED_PENDING):
                    seeding_count += 1
                elif t.status in (Status.DOWNLOADING, Status.DOWNLOAD_PENDING):
                    downloading_count += 1

                torrent_data.append(
                    Torrent(
                        name=t.name,
                        progress=t.progress,
                        eta_s=humanize.time.naturaldelta(t.eta) if t.eta else "∞",
                        rate_download=t.rate_download,
                        rate_upload=t.rate_upload,
                    ).to_dict()
                )
            if downloading_count > 0:
                status = "good"
            elif seeding_count > 0 and total_upspeed > 0:
                status = "warning"
            else:
                status = "idle"

        except transmission_rpc.TransmissionConnectError:
            status = "off"

        data = {
            "total_downspeed": (
                humanize.naturalsize(total_downspeed) if total_downspeed else 0
            ),
            "total_upspeed": (
                humanize.naturalsize(total_upspeed) if total_upspeed else 0
            ),
            "downloading_count": downloading_count,
            "seeding_count": seeding_count,
            "total_count": total_count,
            "torrents": torrent_data,
            "status": status,
        }

        return data


@bears.recruit
class TransmissionBear(Bear):
    name = "transmission"
    torrents = TransmissionPoke(interval=10)

    debug = DebugView()

    eww = EwwJSONView(var_name="transmission", from_key="torrents")
