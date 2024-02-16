import logging
import os
import shutil
from typing import Tuple

import humanize
import psutil

from bear.bear import Bear, bears
from bear.eww import EwwPrefixView
from bear.poke import Poke, PollingPoke
from bear.utils import BearLevel

logger = logging.getLogger(__name__)


class MonitorBear(Bear):
    levels: Tuple[float, float, float]
    metric: Poke
    view = EwwPrefixView(var_names=["metric", "state"])
    abstract = True

    def get_extra_context(self):
        return {"state": BearLevel.level_for(self.metric.data, self.levels)}


@bears.recruit
class LoadAverageBear(MonitorBear):
    name = "load_avg"
    metric = PollingPoke(interval=5, poller=lambda: os.getloadavg())
    levels = (2, 3.2, 3.6)

    def __init__(self, session_bus, system_bus):
        super().__init__(session_bus, system_bus)

    def get_extra_context(self):
        return {
            "state": BearLevel.level_for(self.metric.data[0], self.levels),
            "metric": f"{self.metric.data[0]:.1f} {self.metric.data[1]:.1f}",
        }


@bears.recruit
class CPUBear(MonitorBear):
    name = "cpu"
    metric = PollingPoke(interval=1, poller=lambda: psutil.cpu_percent())
    levels = (50, 80, 90)


@bears.recruit
class MemoryBear(MonitorBear):
    name = "memory"
    metric = PollingPoke(interval=1, poller=lambda: psutil.virtual_memory().percent)
    levels = (50, 80, 90)


@bears.recruit
class DiskSpaceBear(MonitorBear):
    name = "disk"
    metric = PollingPoke(interval=60, poller=lambda: shutil.disk_usage("/").free)
    levels = (1, 5, 10)

    def get_extra_context(self):
        return {
            "state": BearLevel.level_for_type_battery(
                self.metric.data / 10**9, self.levels
            ),
            "metric": humanize.naturalsize(self.metric.data),
        }
