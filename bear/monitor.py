from collections import defaultdict
from dataclasses import dataclass
import logging
import os
import re
import shutil
from typing import Tuple

from dataclasses_json import dataclass_json
import humanize
import psutil

from bear.bear import Bear, bears, dbus_method
from bear.eww import EwwPrefixView, EwwWidgetView
from bear.poke import PausablePollingPoke, PollingPoke
from bear.utils import BearLevel

logger = logging.getLogger(__name__)


class MonitorBear(Bear):
    levels: Tuple[float, float, float]
    metric: PollingPoke
    view = EwwPrefixView(var_names=["metric", "state"])
    abstract = True

    def refresh(self):
        self.metric.do_poll()
        super().refresh()

    def get_extra_context(self):
        return {"state": BearLevel.level_for(self.metric.data, self.levels)}


@bears.recruit
class LoadAverageBear(MonitorBear):
    name = "load_avg"
    metric = PollingPoke(interval=5, poller=lambda: os.getloadavg())
    levels = (2, 3.2, 3.6)

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


@dataclass_json
@dataclass
class ProcessAggregate:
    name: str
    cpu: float
    mem: float
    # procs: list[dict]
    count: int


NAME_MAPPING = {
    "Isolated Web Co": "firefox",
    "firefox-bin": "firefox",
    "Privileged Cont": "firefox",
    "Web Content": "firefox",
    "WebExtensions": "firefox",
}

WRAPPED_RE = re.compile("\.(.*)-wrapped")


class ProcessesPoke(PausablePollingPoke):
    def __init__(self, *args, sort_by="cpu", **kwargs):
        super().__init__(*args, **kwargs)

        self.sort_by = sort_by

    def poll(self):
        # Get all processes sorted by CPU usage
        proc_aggrs = {}

        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "cmdline"]
        ):
            try:
                # Get process info
                p = proc.info

                name = p["name"]
                m = WRAPPED_RE.match(name)
                if m:
                    name = m.group(1)

                name = NAME_MAPPING.get(name, name)

                if name not in proc_aggrs:
                    proc_aggrs[name] = ProcessAggregate(
                        name=name,
                        cpu=p["cpu_percent"],
                        mem=p["memory_percent"],
                        count=1,
                    )
                else:
                    aggr = proc_aggrs[name]
                    aggr.mem += p["memory_percent"]
                    aggr.cpu += p["cpu_percent"]
                    aggr.count += 1

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        # Sort by CPU usage (descending)
        return sorted(
            proc_aggrs.values(), key=lambda p: getattr(p, self.sort_by), reverse=True
        )[:10]


class TopBear(Bear):
    processes: ProcessesPoke
    view: EwwWidgetView

    @dbus_method()
    def show_widget(self):
        logger.info(f"{self}.show_widget")
        self.processes.unpause()
        self.update()
        self.view.open()

    @dbus_method()
    def hide_widget(self):
        logger.info(f"{self}.hide_widget")
        self.processes.pause()
        self.view.close()


# @bears.recruit
# class TopCPUBear(TopBear):
#     name = "top_cpu"

#     processes = ProcessesPoke(interval=5, start_paused=True, sort_by="cpu")

#     view = EwwWidgetView(
#         var_name="processes", from_key="processes", widget_name="top-cpu"
#     )


# @bears.recruit
# class TopMemoryBear(TopBear):
#     name = "top_memory"

#     processes = ProcessesPoke(interval=5, start_paused=True, sort_by="mem")

#     view = EwwWidgetView(
#         var_name="processes", from_key="processes", widget_name="top-memory"
#     )
