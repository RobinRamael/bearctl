from abc import abstractmethod
from typing import Iterable
from dataclasses import dataclass
from collections import defaultdict
import logging
from operator import attrgetter
import os
import os
import re
from typing import Optional

from bear.bear import DebugView, bears, Bear
from bear.eww import EwwJSONView
from bear.poke import PollingPoke

logger = logging.getLogger(__name__)


class FailedToGetStat(Exception):
    pass


class NoSuchProcess(Exception):
    pass


def read_proc_name(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except (FileNotFoundError, ProcessLookupError):
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


def read_vm_rss_kb(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_kb = float(line.split()[1])  # kB
                    return rss_kb
            else:
                # kernel process, default to 0 (which makes sense as those
                # don't consume user space memory)
                return 0

    except FileNotFoundError as e:
        raise FailedToGetStat from e


def read_total_cpu_ticks(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().split()
        utime = int(fields[13])
        stime = int(fields[14])
        return utime + stime
    except (FileNotFoundError, IndexError, ValueError) as e:
        raise FailedToGetStat from e


def total_ram_kb():
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                return int(line.split()[1])
        else:
            raise Exception("Unable to read total available memory.")


@dataclass
class _Process:
    process_ticks: int
    vm_rss_kb: float
    pid: int
    name: str

    _args: Optional[list[str]] = None

    @classmethod
    def from_pid(cls, pid):
        return cls(
            pid=pid,
            name=read_proc_name(pid),
            process_ticks=read_total_cpu_ticks(pid),
            vm_rss_kb=read_vm_rss_kb(pid),
        )

    @property
    def args(self) -> list[str]:
        if self._args is None:
            self._args = read_proc_cmdline(self.pid)

        return self._args


N_CORES = os.cpu_count() or 1


@dataclass
class Process:

    current_snapshot: _Process
    last_snapshot: _Process
    d_ticks: int  # number of ticks between these two snapshots
    total_ram_kb: int

    @property
    def name(self):
        return self.current_snapshot.name

    @property
    def memory_usage(self):
        return (self.current_snapshot.vm_rss_kb / self.total_ram_kb) * 100

    @property
    def cpu_usage(self) -> float:
        d_process_ticks = (
            self.current_snapshot.process_ticks - self.last_snapshot.process_ticks
        )
        return (d_process_ticks / self.d_ticks) * 100 * N_CORES

    def __repr__(self):
        return (
            f"Process(name={self.name!r}, "
            f"pid={self.current_snapshot.pid}, "
            f"cpu={self.cpu_usage:.1f}%, "
            f"mem={self.memory_usage:.1f}%)"
        )


def system_total_ticks():
    """Sum of all cpu ticks from /proc/stat (across all cores)."""
    with open("/proc/stat") as f:
        fields = f.readline().split()[1:]  # first line is aggregate 'cpu'
    return sum(int(f) for f in fields)


def active_pids():
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue

        yield int(entry.name)


class NameTransformer:
    @abstractmethod
    def transform(self, name: str) -> str:
        raise NotImplementedError


class Mapping(NameTransformer):
    def __init__(self, mapping):
        self.mapping = mapping

    def transform(self, name: str) -> str:
        return self.mapping.get(name, name)


class Regex(NameTransformer):
    def __init__(self, regex):
        self.regex = re.compile(regex)

    def transform(self, name: str) -> str:
        m = self.regex.match(name)

        if m:
            return m.group(1)
        else:
            return name


@dataclass
class GroupedProcess:
    processes: list[Process]
    name: str

    @property
    def count(self):
        return len(self.processes)

    @property
    def memory_usage(self):
        return sum(p.memory_usage for p in self.processes)

    @property
    def cpu_usage(self) -> float:
        return sum(p.cpu_usage for p in self.processes)

    def to_dict(self):
        return {
            "cpu_usage": self.cpu_usage,
            "cpu_usage_repr": f"{self.cpu_usage:.2f}",
            "memory_usage": self.memory_usage,
            "memory_usage_repr": f"{self.memory_usage:.2f}",
            "name": self.name,
            "count": len(self.processes),
        }


class ProcessGrouper:

    def __init__(self, transformers=None):
        self.transformers = transformers or []

    def transform(self, name: str) -> str:
        for transformer in self.transformers:
            name = transformer.transform(name)

        return name

    def group(self, processes: Iterable[Process]) -> list[GroupedProcess]:
        groups = defaultdict(list)
        for process in processes:
            groups[self.transform(process.name)].append(process)

        return [GroupedProcess(name=name, processes=ps) for name, ps in groups.items()]


class ProcessMonitor:

    def __init__(self, total_ram_kb, transformers=None):
        self._last_snapshot = {}
        self.total_ram_kb = total_ram_kb
        self._last_system_ticks = 0

        self.grouper = ProcessGrouper(transformers=(transformers or []))

    def start_monitoring(self):
        self._last_snapshot = self.make_snapshot()
        self._last_system_ticks = system_total_ticks()

    def make_snapshot(self):
        raw_processes = {}

        for pid in active_pids():
            try:
                process = _Process.from_pid(pid)
            except FailedToGetStat:
                logger.debug(
                    f"Tried to get stats from process {pid}, but the process vanished before we could."
                )

                continue

            raw_processes[pid] = process

        return raw_processes

    def get_processes(self) -> list[Process]:
        if not self._last_snapshot:
            raise RuntimeError("Can't get processes before start_monitoring is called")

        new_snapshot = self.make_snapshot()
        new_system_ticks = system_total_ticks()

        d_ticks = new_system_ticks - self._last_system_ticks

        if d_ticks == 0:
            logger.warning(
                "Number of ticks since last snapshot was 0. Were we suspended? Skipping. "
            )
            return []

        processes = []
        for process in new_snapshot.values():
            try:
                processes.append(
                    Process(
                        current_snapshot=process,
                        last_snapshot=self._last_snapshot[process.pid],
                        d_ticks=d_ticks,
                        total_ram_kb=self.total_ram_kb,
                    )
                )
            except KeyError:
                continue

        self._last_system_ticks = new_system_ticks
        self._last_snapshot = new_snapshot
        return processes

    def get_grouped_processes(self) -> list[GroupedProcess]:
        return self.grouper.group(self.get_processes())


class PinnedProcessPicker:
    @abstractmethod
    def is_pinned(self, process) -> bool:
        raise NotImplementedError


class LiteralPicker(PinnedProcessPicker):
    def __init__(self, *names):
        self.names = names

    def is_pinned(self, process) -> bool:
        return any(process.name == name for name in self.names)


class ProcessesPoke(PollingPoke):

    def __init__(self, *args, n=10, pinned_pickers=None, transformers=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = n
        self.process_monitor = ProcessMonitor(
            total_ram_kb=total_ram_kb(), transformers=transformers or []
        )

        self.pinned_pickers = pinned_pickers or []

    def register(self):
        # register already calls poll, so we have to have started before we do
        # the rest of the register
        self.process_monitor.start_monitoring()
        super().register()

    def is_pinned(self, process):
        return any(picker.is_pinned(process) for picker in self.pinned_pickers)

    def poll(self):
        processes = self.process_monitor.get_grouped_processes()

        top_cpu = sorted(processes, key=attrgetter("cpu_usage"), reverse=True)[: self.n]
        top_memory = sorted(processes, key=attrgetter("memory_usage"), reverse=True)[
            : self.n
        ]

        pinned = [p for p in processes if self.is_pinned(p)]

        return {"top_cpu": top_cpu, "top_memory": top_memory, "pinned": pinned}


@bears.recruit
class ProcessMonitorBear(Bear):
    name = "top"

    processes = ProcessesPoke(
        interval=1,
        n=10,
        pinned_pickers=[LiteralPicker("bearctl", "firefox")],
        transformers=[
            Regex(r"\.(.*)-wrapped?"),
            Mapping(
                {
                    "Isolated Web Co": "firefox",
                    "Isolated Servic": "firefox",
                    "firefox-bin": "firefox",
                    "Privileged Cont": "firefox",
                    "Web Content": "firefox",
                    "WebExtensions": "firefox",
                    "kitten": "kitty",
                }
            ),
        ],
    )

    eww_pinned = EwwJSONView("processes", from_key="processes")

    debug = DebugView(pprint=False)
