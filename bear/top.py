from abc import abstractmethod
from dataclasses import dataclass, field
import logging
from operator import attrgetter
import os
import os
import re
from typing import DefaultDict, Iterable, Optional

from bear.bear import Bear, DebugView, bears
from bear.eww import EwwWidgetView
from bear.poke import PollingPoke
from bear.poke import PollingPoke

logger = logging.getLogger(__name__)


class FailedToGetStat(Exception):
    pass


def read_proc_name(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "<unknown>"


def read_proc_cmdline(pid: int) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:  # note: binary mode
            data = f.read()
        if not data:
            return []  # kernel thread — cmdline is empty
        args = data.rstrip(b"\x00").split(b"\x00")
        return [a.decode("utf-8", errors="replace") for a in args]
    except FileNotFoundError:
        return []


@dataclass
class Process:
    stat: float
    pid: int

    _name: Optional[str] = None
    _args: Optional[list[str]] = None

    @property
    def name(self) -> str:
        if not self._name:
            self._name = read_proc_name(self.pid)

        return self._name

    @property
    def useful_name(self) -> str:
        if self.name.startswith("python"):
            s = self.python_name_transform()
            return s
        else:
            return self.name

    @property
    def short_name(self):
        return self.name

    @property
    def args(self):
        if self._args is None:
            self._args = read_proc_cmdline(self.pid)

        return self._args

    def python_name_transform(self):
        if self.args[1] in ("-m", "-c"):
            if self.args[2] == "bear.main":
                return "bear-debug"
            else:
                # use process name instead of full nixos path (which is in
                # args[0])
                return f"{self.name} " + " ".join(self.args[1:])
        else:
            return self.args[1]


NAME_MAPPING = {
    "Isolated Web Co": "firefox",
    "firefox-bin": "firefox",
    "Privileged Cont": "firefox",
    "Web Content": "firefox",
    "WebExtensions": "firefox",
    "kitten": "kitty",
}

WRAPPED_RE = re.compile("\.(.*)-wrapped?")


def transform_name(name: str) -> str:

    m = WRAPPED_RE.match(name)

    if m:
        name = m.group(1)

    try:
        return NAME_MAPPING[name]
    except KeyError:
        return name


@dataclass
class GroupedProcess:
    processes: list[Process]
    name: str

    @property
    def count(self):
        return len(self.processes)

    @property
    def stat(self):
        return sum(p.stat for p in self.processes)

    def to_dict(self):
        return {
            "stat": self.stat,
            "stat_repr": f"{self.stat:.2f}",
            "name": self.name,
            "count": len(self.processes),
        }

    @classmethod
    def group(cls, processes: Iterable[Process]) -> list["GroupedProcess"]:
        name_to_proc = DefaultDict(list)

        for proc in processes:
            name_to_proc[transform_name(proc.useful_name)].append(proc)

        return [GroupedProcess(procs, name) for name, procs in name_to_proc.items()]

    def __repr__(self):
        return (
            f"{self.__class__.__name__}(name={self.name},"
            f"count={self.count}, stat={self.stat:0.2f})"
        )


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

        return sorted(
            GroupedProcess.group(results), key=attrgetter("stat"), reverse=True
        )[: self.n]


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
        return sorted(
            GroupedProcess.group(self.get_processes()),
            key=attrgetter("stat"),
            reverse=True,
        )[:n]


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
