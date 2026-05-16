from abc import abstractmethod
from dataclasses import dataclass
from operator import attrgetter
import os
import os
import re
from typing import Optional

from bear.bear import Bear, DebugView, bears
from bear.eww import EwwWidgetView
from bear.poke import PollingPoke
from bear.poke import PollingPoke

# unused for now
NAME_MAPPING = {
    "Isolated Web Co": "firefox",
    "firefox-bin": "firefox",
    "Privileged Cont": "firefox",
    "Web Content": "firefox",
    "WebExtensions": "firefox",
}

WRAPPED_RE = re.compile("\.(.*)-wrapped")


class FailedToGetStat(Exception):
    pass


def read_proc_name(pid):
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "<unknown>"


@dataclass
class Process:
    stat: float
    pid: int

    _name: Optional[str] = None

    @property
    def name(self) -> str:
        if not self._name:
            self._name = read_proc_name(self.pid)

        return self._name

    @property
    def short_name(self):
        return self.name

    def to_dict(self):
        return {"stat": self.stat, "stat_repr": f"{self.stat:.2f}", "name": self.name}


class TopPoke(PollingPoke):
    def __init__(self, *args, n=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = n

    @abstractmethod
    def read_proc_stat(self, pid: int) -> float:
        raise NotImplemented

    def get_processes(self) -> list[Process]:
        processes = []
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue

            pid = int(entry.name)

            try:
                value = self.read_proc_stat(pid)
                processes.append(Process(stat=value, pid=pid))
            except FailedToGetStat:
                pass

        return processes


def system_total_ticks():
    """Sum of all cpu ticks from /proc/stat (across all cores)."""
    with open("/proc/stat") as f:
        fields = f.readline().split()[1:]  # first line is aggregate 'cpu'
    return sum(int(f) for f in fields)


def _build_process_dict(processes) -> dict[int, Process]:
    return {p.pid: p for p in processes}


class TopCPUPoke(TopPoke):

    def register(self):
        # first get the initial values, only then start polling, this ensure the
        # initial values here are used for the initial data (set deep in
        # register call) which then makes at least a tiny amount of sense:
        self._last_snapshot = _build_process_dict(self.get_processes())
        self._last_total_ticks = system_total_ticks()

        super().register()

    def read_proc_stat(self, pid):
        try:
            with open(f"/proc/{pid}/stat") as f:
                fields = f.read().split()
            utime = int(fields[13])
            stime = int(fields[14])
            return utime + stime
        except (FileNotFoundError, IndexError, ValueError) as e:
            raise FailedToGetStat from e

    def poll(self):
        current_processes = self.get_processes()
        new_total_ticks = system_total_ticks()

        total_ticks_since_last = new_total_ticks - self._last_total_ticks
        assert total_ticks_since_last, "No ticks passed since last snapshot??"

        results = []
        for p in current_processes:
            try:
                ticks_since_last = p.stat - self._last_snapshot[p.pid].stat
            except KeyError:  # process spawned after last snapshot was made
                ticks_since_last = p.stat

            cpu_perc = (ticks_since_last / total_ticks_since_last) * 100
            results.append(Process(pid=p.pid, stat=cpu_perc))

        self._last_snapshot = _build_process_dict(current_processes)
        self._last_total_ticks = new_total_ticks

        return sorted(results, key=attrgetter("stat"), reverse=True)[: self.n]


def total_ram_kb():
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                return int(line.split()[1])
        else:
            raise Exception("Unable to read total available memory.")


_TOTAL_RAM_KB = total_ram_kb()


class TopMemoryPoke(TopPoke):

    def read_proc_stat(self, pid) -> float:
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_kb = float(line.split()[1])  # kB
                        return (rss_kb / _TOTAL_RAM_KB) * 100
                else:
                    # kernel process, default to 0 (which makes sense as those
                    # don't consume user space memory)
                    return 0

        except FileNotFoundError as e:
            raise FailedToGetStat from e

    def poll(self, n=10):
        return sorted(self.get_processes(), key=attrgetter("stat"), reverse=True)[:n]


@bears.recruit
class TopMemoryBear(Bear):
    name = "top_memory"
    processes = TopMemoryPoke(interval=1, n=10)

    view = EwwWidgetView(
        var_name="top_memory", from_key="processes", widget_name="top-memory"
    )

    debug = DebugView()


@bears.recruit
class TopCPUBear(Bear):
    name = "top_cpu"
    processes = TopCPUPoke(interval=1, n=10)

    view = EwwWidgetView(
        var_name="top_cpu", from_key="processes", widget_name="top-cpu"
    )
    debug = DebugView()
