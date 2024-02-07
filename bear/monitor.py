import logging
import os
from typing import Tuple

import psutil

from bear.bear import Bear, bears
from bear.eww import EwwPrefixView
from bear.poke import Poke, PollingPoke

logger = logging.getLogger(__name__)


class BearLevel:
    good = "good"
    idle = "idle"
    info = "info"
    warning = "warning"
    error = "critical"


class MonitorBear(Bear):
    levels: Tuple[float, float, float]
    metric: Poke
    view = EwwPrefixView(var_names=["metric", "state"])
    abstract = True

    def state_for(self, val):
        for level, state in zip(
            self.levels, [BearLevel.idle, BearLevel.info, BearLevel.warning]
        ):
            if val < level:
                return state

        else:
            return BearLevel.error

    def get_extra_context(self):
        return {"state": self.state_for(self.metric.data)}


@bears.recruit
class LoadAverageBear(MonitorBear):
    name = "load_avg"
    metric = PollingPoke(interval=5, poller=lambda: os.getloadavg())
    levels = (2, 3.2, 3.6)

    def __init__(self, session_bus, system_bus):
        super().__init__(session_bus, system_bus)

    def get_extra_context(self):
        return {
            "state": self.state_for(self.metric.data[0]),
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
