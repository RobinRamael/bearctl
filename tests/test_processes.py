from typing import Optional
from unittest.mock import MagicMock, mock_open, patch

import pytest


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

FAKE_STAT_LINE = (
    "1234 (python3) S 1233 1234 1234 0 -1 4194304 "
    "100 0 0 0 "
    "50 25 "  # utime=50, stime=25 → total=75
    "0 0 20 0 1 0 12345 "
    "10240 -1 18446744073709551615 "
    "0 0 0 0 0 0 0 0 0 0 0 0 17 0 0 0 0 0 0\n"
)

FAKE_STATUS_WITH_RSS = """\
Name:   python3
State:  S (sleeping)
Pid:    1234
VmPeak: 20480 kB
VmSize: 20480 kB
VmRSS:  8192 kB
Threads: 1
"""

FAKE_STATUS_KERNEL_THREAD = """\
Name:   kworker/0:0
State:  I (idle)
Pid:    12
"""

FAKE_CMDLINE = b"/usr/bin/python3\x00myscript.py\x00--verbose\x00"

FAKE_MEMINFO = """\
MemTotal:       16384000 kB
MemFree:         8192000 kB
MemAvailable:   10240000 kB
"""

FAKE_PROC_STAT_LINE = "cpu  1000 0 500 8000 100 0 50 0 0 0\n"
# sum = 9650

TOTAL_RAM_KB = 16384000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_raw_process(pid=1234, ticks=100, rss_kb=8192.0, name="python3"):
    from bear.top import _Process

    return _Process(pid=pid, process_ticks=ticks, vm_rss_kb=rss_kb, name=name)


def make_process(
    current_ticks=200,
    last_ticks=100,
    d_ticks=1000,
    rss_kb=8192.0,
    pid=1234,
    name="python3",
    total_ram_kb=TOTAL_RAM_KB,
):
    from bear.top import Process

    return Process(
        current_snapshot=make_raw_process(
            pid=pid, ticks=current_ticks, rss_kb=rss_kb, name=name
        ),
        last_snapshot=make_raw_process(pid=pid, ticks=last_ticks),
        d_ticks=d_ticks,
        total_ram_kb=total_ram_kb,
    )


def make_cmdline_mock(data: bytes):
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    m.read = lambda: data
    return m


def make_monitor(last_snapshot=None, last_ticks=9000, total_ram_kb=TOTAL_RAM_KB):
    from bear.top import ProcessMonitor

    monitor = ProcessMonitor(total_ram_kb=total_ram_kb)
    monitor._last_snapshot = last_snapshot if last_snapshot is not None else {}
    monitor._last_system_ticks = last_ticks
    return monitor


# ---------------------------------------------------------------------------
# read_proc_name
# ---------------------------------------------------------------------------


class TestReadProcName:
    def test_strips_newline(self, monkeypatch):
        monkeypatch.setattr("builtins.open", mock_open(read_data="python3\n"))
        from bear.top import read_proc_name

        assert read_proc_name(1234) == "python3"

    def test_process_vanishes(self, monkeypatch):
        monkeypatch.setattr("builtins.open", MagicMock(side_effect=FileNotFoundError))
        from bear.top import read_proc_name

        assert read_proc_name(9999) == "<unknown>"


# ---------------------------------------------------------------------------
# read_proc_cmdline
# ---------------------------------------------------------------------------


class TestReadProcCmdline:
    def test_parses_null_separated_args(self, monkeypatch):
        monkeypatch.setattr(
            "builtins.open", lambda *a, **kw: make_cmdline_mock(FAKE_CMDLINE)
        )
        from bear.top import read_proc_cmdline

        assert read_proc_cmdline(1234) == [
            "/usr/bin/python3",
            "myscript.py",
            "--verbose",
        ]

    def test_kernel_thread_empty_cmdline(self, monkeypatch):
        monkeypatch.setattr("builtins.open", lambda *a, **kw: make_cmdline_mock(b""))
        from bear.top import read_proc_cmdline

        assert read_proc_cmdline(2) == []

    def test_trailing_null_stripped(self, monkeypatch):
        monkeypatch.setattr(
            "builtins.open", lambda *a, **kw: make_cmdline_mock(b"/bin/sh\x00")
        )
        from bear.top import read_proc_cmdline

        assert read_proc_cmdline(1) == ["/bin/sh"]

    def test_invalid_utf8_replaced(self, monkeypatch):
        monkeypatch.setattr(
            "builtins.open", lambda *a, **kw: make_cmdline_mock(b"/bin/\xff\x00")
        )
        from bear.top import read_proc_cmdline

        result = read_proc_cmdline(1)
        assert len(result) == 1
        assert "\xff" not in result[0]

    def test_process_vanishes(self, monkeypatch):
        monkeypatch.setattr("builtins.open", MagicMock(side_effect=FileNotFoundError))
        from bear.top import read_proc_cmdline

        assert read_proc_cmdline(9999) == []


# ---------------------------------------------------------------------------
# read_total_cpu_ticks
# ---------------------------------------------------------------------------


class TestReadTotalCpuTicks:
    def test_sums_utime_and_stime(self, monkeypatch):
        monkeypatch.setattr("builtins.open", mock_open(read_data=FAKE_STAT_LINE))
        from bear.top import read_total_cpu_ticks

        assert read_total_cpu_ticks(1234) == 75  # 50 + 25

    def test_process_vanishes_raises(self, monkeypatch):
        monkeypatch.setattr("builtins.open", MagicMock(side_effect=FileNotFoundError))
        from bear.top import read_total_cpu_ticks, FailedToGetStat

        with pytest.raises(FailedToGetStat):
            read_total_cpu_ticks(9999)

    def test_malformed_stat_raises(self, monkeypatch):
        monkeypatch.setattr("builtins.open", mock_open(read_data="1234 (sh) S\n"))
        from bear.top import read_total_cpu_ticks, FailedToGetStat

        with pytest.raises(FailedToGetStat):
            read_total_cpu_ticks(1234)

    def test_non_numeric_fields_raises(self, monkeypatch):
        bad_stat = FAKE_STAT_LINE.replace("50 25", "xx yy")
        monkeypatch.setattr("builtins.open", mock_open(read_data=bad_stat))
        from bear.top import read_total_cpu_ticks, FailedToGetStat

        with pytest.raises(FailedToGetStat):
            read_total_cpu_ticks(1234)


# ---------------------------------------------------------------------------
# read_vm_rss_kb
# ---------------------------------------------------------------------------


class TestReadVmRssKb:
    def test_reads_rss(self, monkeypatch):
        monkeypatch.setattr("builtins.open", mock_open(read_data=FAKE_STATUS_WITH_RSS))
        from bear.top import read_vm_rss_kb

        assert read_vm_rss_kb(1234) == 8192.0

    def test_kernel_thread_returns_zero(self, monkeypatch):
        monkeypatch.setattr(
            "builtins.open", mock_open(read_data=FAKE_STATUS_KERNEL_THREAD)
        )
        from bear.top import read_vm_rss_kb

        assert read_vm_rss_kb(12) == 0

    def test_process_vanishes_raises(self, monkeypatch):
        monkeypatch.setattr("builtins.open", MagicMock(side_effect=FileNotFoundError))
        from bear.top import read_vm_rss_kb, FailedToGetStat

        with pytest.raises(FailedToGetStat):
            read_vm_rss_kb(9999)

    def test_does_not_pick_up_other_vm_lines(self, monkeypatch):
        # VmPeak appears before VmRSS — must not be returned instead
        monkeypatch.setattr("builtins.open", mock_open(read_data=FAKE_STATUS_WITH_RSS))
        from bear.top import read_vm_rss_kb

        assert read_vm_rss_kb(1234) == 8192.0  # not 20480


# ---------------------------------------------------------------------------
# _Process
# ---------------------------------------------------------------------------


class TestRawProcess:
    def test_constructs_from_pid(self, monkeypatch):
        monkeypatch.setattr("bear.top.read_proc_name", lambda pid: "python3")
        monkeypatch.setattr("bear.top.read_total_cpu_ticks", lambda pid: 75)
        monkeypatch.setattr("bear.top.read_vm_rss_kb", lambda pid: 8192.0)
        from bear.top import _Process

        p = _Process.from_pid(1234)
        assert p.pid == 1234
        assert p.name == "python3"
        assert p.process_ticks == 75
        assert p.vm_rss_kb == 8192.0

    def test_failed_cpu_ticks_propagates(self, monkeypatch):
        from bear.top import FailedToGetStat

        monkeypatch.setattr("bear.top.read_proc_name", lambda pid: "python3")
        monkeypatch.setattr(
            "bear.top.read_total_cpu_ticks", MagicMock(side_effect=FailedToGetStat)
        )
        monkeypatch.setattr("bear.top.read_vm_rss_kb", lambda pid: 8192.0)
        from bear.top import _Process

        with pytest.raises(FailedToGetStat):
            _Process.from_pid(1234)

    def test_failed_rss_propagates(self, monkeypatch):
        from bear.top import FailedToGetStat

        monkeypatch.setattr("bear.top.read_proc_name", lambda pid: "python3")
        monkeypatch.setattr("bear.top.read_total_cpu_ticks", lambda pid: 75)
        monkeypatch.setattr(
            "bear.top.read_vm_rss_kb", MagicMock(side_effect=FailedToGetStat)
        )
        from bear.top import _Process

        with pytest.raises(FailedToGetStat):
            _Process.from_pid(1234)

    def test_args_lazy_loaded(self, monkeypatch):
        monkeypatch.setattr("bear.top.read_proc_name", lambda pid: "python3")
        monkeypatch.setattr("bear.top.read_total_cpu_ticks", lambda pid: 75)
        monkeypatch.setattr("bear.top.read_vm_rss_kb", lambda pid: 8192.0)
        mock_cmdline = MagicMock(return_value=["/usr/bin/python3", "script.py"])
        monkeypatch.setattr("bear.top.read_proc_cmdline", mock_cmdline)
        from bear.top import _Process

        p = _Process.from_pid(1234)
        mock_cmdline.assert_not_called()
        _ = p.args
        mock_cmdline.assert_called_once_with(1234)
        _ = p.args
        assert mock_cmdline.call_count == 1  # cached, not re-read


# ---------------------------------------------------------------------------
# Process
# ---------------------------------------------------------------------------


class TestProcess:
    def test_cpu_usage_basic(self):
        from bear.top import N_CORES

        p = make_process(current_ticks=200, last_ticks=100, d_ticks=1000)
        assert p.cpu_usage == pytest.approx(10.0 * N_CORES)

    def test_cpu_usage_idle(self):
        p = make_process(current_ticks=100, last_ticks=100, d_ticks=1000)
        assert p.cpu_usage == pytest.approx(0.0)

    def test_cpu_usage_fully_saturated_single_core(self):
        from bear.top import N_CORES

        p = make_process(
            current_ticks=123,
            last_ticks=0,
            d_ticks=N_CORES * 123,
        )
        assert p.cpu_usage == pytest.approx(100.0)

    def test_cpu_usage_multithreaded_exceeds_100(self):
        from bear.top import N_CORES

        p = make_process(
            current_ticks=4 * 100,
            last_ticks=0,
            d_ticks=N_CORES * 100,
        )
        assert p.cpu_usage == pytest.approx(400.0)

    def test_memory_usage_basic(self):
        p = make_process(rss_kb=8192000.0, total_ram_kb=16384000)
        assert p.memory_usage == pytest.approx(50.0)

    def test_memory_usage_kernel_thread_zero(self):
        p = make_process(rss_kb=0.0, total_ram_kb=16384000)
        assert p.memory_usage == pytest.approx(0.0)

    def test_memory_usage_full_ram(self):
        p = make_process(rss_kb=16384000.0, total_ram_kb=16384000)
        assert p.memory_usage == pytest.approx(100.0)

    def test_name_comes_from_current_snapshot(self):
        from bear.top import Process

        p = Process(
            current_snapshot=make_raw_process(name="current"),
            last_snapshot=make_raw_process(name="old"),
            d_ticks=1000,
            total_ram_kb=TOTAL_RAM_KB,
        )
        assert p.name == "current"

    def test_repr_contains_key_fields(self):
        p = make_process(pid=42, current_ticks=200, last_ticks=100, name="myapp")
        r = repr(p)
        assert "myapp" in r
        assert "42" in r
        assert "cpu=" in r
        assert "mem=" in r

    def test_repr_formats_as_percentages(self):
        p = make_process()
        r = repr(p)
        assert "%" in r


# ---------------------------------------------------------------------------
# active_pids
# ---------------------------------------------------------------------------


class TestActivePids:
    def _make_entry(self, name):
        e = MagicMock()
        e.name = name
        return e

    def test_yields_only_numeric_entries(self, monkeypatch):
        entries = [
            self._make_entry("1"),
            self._make_entry("234"),
            self._make_entry("cpuinfo"),
            self._make_entry("meminfo"),
            self._make_entry("net"),
        ]
        monkeypatch.setattr("bear.top.os.scandir", lambda path: entries)
        from bear.top import active_pids

        assert list(active_pids()) == [1, 234]

    def test_empty_proc(self, monkeypatch):
        monkeypatch.setattr("bear.top.os.scandir", lambda path: [])
        from bear.top import active_pids

        assert list(active_pids()) == []

    def test_all_non_numeric(self, monkeypatch):
        entries = [self._make_entry(n) for n in ["stat", "net", "sys", "fs"]]
        monkeypatch.setattr("bear.top.os.scandir", lambda path: entries)
        from bear.top import active_pids

        assert list(active_pids()) == []

    def test_scans_proc_directory(self, monkeypatch):
        scanned = []

        def fake_scandir(path):
            scanned.append(path)
            return []

        monkeypatch.setattr("bear.top.os.scandir", fake_scandir)
        from bear.top import active_pids

        list(active_pids())
        assert scanned == ["/proc"]


# ---------------------------------------------------------------------------
# ProcessMonitor.make_snapshot
# ---------------------------------------------------------------------------


class TestMakeSnapshot:
    def test_returns_dict_keyed_by_pid(self, monkeypatch):
        p1 = make_raw_process(pid=1, ticks=10)
        p2 = make_raw_process(pid=2, ticks=20)
        monkeypatch.setattr("bear.top.active_pids", lambda: iter([1, 2]))
        monkeypatch.setattr(
            "bear.top._Process.from_pid", lambda pid: {1: p1, 2: p2}[pid]
        )
        from bear.top import ProcessMonitor

        snap = ProcessMonitor(total_ram_kb=TOTAL_RAM_KB).make_snapshot()
        assert snap == {1: p1, 2: p2}

    def test_failed_stat_is_skipped(self, monkeypatch):
        from bear.top import FailedToGetStat

        p2 = make_raw_process(pid=2, ticks=20)

        def fake_from_pid(pid):
            if pid == 1:
                raise FailedToGetStat
            return p2

        monkeypatch.setattr("bear.top.active_pids", lambda: iter([1, 2]))
        monkeypatch.setattr("bear.top._Process.from_pid", fake_from_pid)
        from bear.top import ProcessMonitor

        snap = ProcessMonitor(total_ram_kb=TOTAL_RAM_KB).make_snapshot()
        assert 1 not in snap
        assert 2 in snap

    def test_all_failed_returns_empty(self, monkeypatch):
        from bear.top import FailedToGetStat

        monkeypatch.setattr("bear.top.active_pids", lambda: iter([1, 2, 3]))
        monkeypatch.setattr(
            "bear.top._Process.from_pid", MagicMock(side_effect=FailedToGetStat)
        )
        from bear.top import ProcessMonitor

        snap = ProcessMonitor(total_ram_kb=TOTAL_RAM_KB).make_snapshot()
        assert snap == {}

    def test_empty_proc_returns_empty(self, monkeypatch):
        monkeypatch.setattr("bear.top.active_pids", lambda: iter([]))
        from bear.top import ProcessMonitor

        snap = ProcessMonitor(total_ram_kb=TOTAL_RAM_KB).make_snapshot()
        assert snap == {}


# ---------------------------------------------------------------------------
# ProcessMonitor.get_processes
# ---------------------------------------------------------------------------


class TestGetProcesses:
    def test_basic_returns_process_objects(self, monkeypatch):
        from bear.top import Process, ProcessMonitor

        old = make_raw_process(pid=1, ticks=100)
        new = make_raw_process(pid=1, ticks=200)
        monkeypatch.setattr(ProcessMonitor, "make_snapshot", lambda self: {1: new})
        monkeypatch.setattr("bear.top.system_total_ticks", lambda: 10000)
        monitor = make_monitor(last_snapshot={1: old}, last_ticks=9000)
        result = monitor.get_processes()
        assert len(result) == 1
        assert isinstance(result[0], Process)

    def test_cpu_delta_calculated_correctly(self, monkeypatch):
        from bear.top import ProcessMonitor, N_CORES

        old = make_raw_process(pid=1, ticks=0)
        new = make_raw_process(pid=1, ticks=100)
        monkeypatch.setattr(ProcessMonitor, "make_snapshot", lambda self: {1: new})
        monkeypatch.setattr("bear.top.system_total_ticks", lambda: 10000)
        monitor = make_monitor(last_snapshot={1: old}, last_ticks=9000)
        result = monitor.get_processes()
        # d_process=100, d_system=1000 → 10% * N_CORES
        assert result[0].cpu_usage == pytest.approx(10.0 * N_CORES)

    def test_new_process_during_interval_skipped(self, monkeypatch):
        from bear.top import ProcessMonitor

        new = make_raw_process(pid=99, ticks=50)
        monkeypatch.setattr(ProcessMonitor, "make_snapshot", lambda self: {99: new})
        monkeypatch.setattr("bear.top.system_total_ticks", lambda: 10000)
        monitor = make_monitor(last_snapshot={}, last_ticks=9000)
        # empty last_snapshot triggers the RuntimeError guard — give it a real
        # pid so the guard doesn't fire, then override snapshot manually
        monitor._last_snapshot = {1: make_raw_process(pid=1)}
        monkeypatch.setattr(ProcessMonitor, "make_snapshot", lambda self: {99: new})
        result = monitor.get_processes()
        assert result == []

    def test_vanished_process_excluded(self, monkeypatch):
        from bear.top import ProcessMonitor

        old_1 = make_raw_process(pid=1, ticks=100)
        old_2 = make_raw_process(pid=2, ticks=100)
        new_1 = make_raw_process(pid=1, ticks=200)
        monkeypatch.setattr(ProcessMonitor, "make_snapshot", lambda self: {1: new_1})
        monkeypatch.setattr("bear.top.system_total_ticks", lambda: 10000)
        monitor = make_monitor(last_snapshot={1: old_1, 2: old_2}, last_ticks=9000)
        result = monitor.get_processes()
        assert len(result) == 1
        assert result[0].current_snapshot.pid == 1

    def test_updates_state_after_call(self, monkeypatch):
        from bear.top import ProcessMonitor

        old = make_raw_process(pid=1, ticks=100)
        new = make_raw_process(pid=1, ticks=200)
        monkeypatch.setattr(ProcessMonitor, "make_snapshot", lambda self: {1: new})
        monkeypatch.setattr("bear.top.system_total_ticks", lambda: 10000)
        monitor = make_monitor(last_snapshot={1: old}, last_ticks=9000)
        monitor.get_processes()
        assert monitor._last_snapshot == {1: new}
        assert monitor._last_system_ticks == 10000

    def test_raises_before_start_monitoring(self):
        from bear.top import ProcessMonitor

        monitor = ProcessMonitor(total_ram_kb=TOTAL_RAM_KB)
        with pytest.raises(RuntimeError, match="start_monitoring"):
            monitor.get_processes()

    def test_total_ram_passed_to_processes(self, monkeypatch):
        from bear.top import ProcessMonitor

        old = make_raw_process(pid=1, ticks=100)
        new = make_raw_process(pid=1, ticks=200)
        monkeypatch.setattr(ProcessMonitor, "make_snapshot", lambda self: {1: new})
        monkeypatch.setattr("bear.top.system_total_ticks", lambda: 10000)
        monitor = make_monitor(
            last_snapshot={1: old}, last_ticks=9000, total_ram_kb=99999
        )
        result = monitor.get_processes()
        assert result[0].total_ram_kb == 99999


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def make_proc_open(
    pid_stats: dict[int, tuple[int, int, float]], sys_tick_sequence: list[int]
):
    """
    Returns a fake open() serving /proc files.

    pid_stats:        {pid: (utime, stime, rss_kb)}
    sys_tick_sequence: values served in order on each /proc/stat read
    """
    stat_call = {"n": 0}

    def fake_open(path, mode="r", *args, **kwargs):
        if path == "/proc/stat":
            ticks = sys_tick_sequence[min(stat_call["n"], len(sys_tick_sequence) - 1)]
            stat_call["n"] += 1
            return mock_open(read_data=f"cpu  {ticks} 0 0 0 0 0 0 0 0 0\n")()

        if path == "/proc/meminfo":
            return mock_open(read_data=FAKE_MEMINFO)()

        for pid, (utime, stime, rss_kb) in pid_stats.items():
            if path == f"/proc/{pid}/stat":
                line = FAKE_STAT_LINE.replace("50 25", f"{utime} {stime}")
                return mock_open(read_data=line)()
            if path == f"/proc/{pid}/status":
                data = FAKE_STATUS_WITH_RSS.replace("8192", str(int(rss_kb)))
                return mock_open(read_data=data)()
            if path == f"/proc/{pid}/comm":
                return mock_open(read_data="python3\n")()

        raise FileNotFoundError(f"unexpected path in integration test: {path}")

    return fake_open


def make_scandir(pids: list[int]):
    def fake_scandir(path):
        entries = []
        for pid in pids:
            e = MagicMock()
            e.name = str(pid)
            entries.append(e)
        noise = MagicMock()
        noise.name = "cpuinfo"
        entries.append(noise)
        return entries

    return fake_scandir


def make_integration_monitor(monkeypatch, pids, pid_stats, sys_tick_sequence):
    """Construct and start a monitor with fully mocked /proc."""
    monkeypatch.setattr("bear.top.os.scandir", make_scandir(pids))
    monkeypatch.setattr("builtins.open", make_proc_open(pid_stats, sys_tick_sequence))
    from bear.top import ProcessMonitor

    monitor = ProcessMonitor(total_ram_kb=TOTAL_RAM_KB)
    monitor.start_monitoring()
    return monitor


class TestProcessMonitorIntegration:
    def test_single_process_cpu_and_mem(self, monkeypatch):
        from bear.top import N_CORES

        monitor = make_integration_monitor(
            monkeypatch,
            pids=[1234],
            pid_stats={1234: (50, 25, 8192)},  # initial: 75 ticks
            sys_tick_sequence=[9000, 10000],  # d_sys = 1000
        )
        monkeypatch.setattr("bear.top.os.scandir", make_scandir([1234]))
        monkeypatch.setattr(
            "builtins.open",
            make_proc_open({1234: (150, 25, 8192)}, [10000]),  # d_process = 100
        )
        processes = monitor.get_processes()
        assert len(processes) == 1
        p = processes[0]
        assert p.name == "python3"
        assert p.cpu_usage == pytest.approx(10.0 * N_CORES)
        assert p.memory_usage == pytest.approx((8192 / TOTAL_RAM_KB) * 100)

    def test_process_appearing_mid_interval_excluded(self, monkeypatch):
        monitor = make_integration_monitor(
            monkeypatch,
            pids=[1234],
            pid_stats={1234: (50, 25, 8192)},
            sys_tick_sequence=[9000, 10000],
        )
        monkeypatch.setattr("bear.top.os.scandir", make_scandir([1234, 5678]))
        monkeypatch.setattr(
            "builtins.open",
            make_proc_open({1234: (100, 25, 8192), 5678: (50, 10, 4096)}, [10000]),
        )
        processes = monitor.get_processes()
        pids = [p.current_snapshot.pid for p in processes]
        assert 5678 not in pids
        assert 1234 in pids

    def test_process_vanishing_mid_interval_excluded(self, monkeypatch):
        monitor = make_integration_monitor(
            monkeypatch,
            pids=[1234, 5678],
            pid_stats={1234: (50, 25, 8192), 5678: (30, 10, 2048)},
            sys_tick_sequence=[9000, 10000],
        )
        monkeypatch.setattr("bear.top.os.scandir", make_scandir([1234]))
        monkeypatch.setattr(
            "builtins.open", make_proc_open({1234: (100, 25, 8192)}, [10000])
        )
        processes = monitor.get_processes()
        assert len(processes) == 1
        assert processes[0].current_snapshot.pid == 1234

    def test_kernel_thread_zero_memory(self, monkeypatch):
        def fake_open_start(path, mode="r", *args, **kwargs):
            if path == "/proc/stat":
                return mock_open(read_data="cpu  9000 0 0 0 0 0 0 0 0 0\n")()
            if path == "/proc/2/stat":
                return mock_open(read_data=FAKE_STAT_LINE)()
            if path == "/proc/2/status":
                return mock_open(read_data=FAKE_STATUS_KERNEL_THREAD)()
            if path == "/proc/2/comm":
                return mock_open(read_data="kworker\n")()
            raise FileNotFoundError(path)

        monkeypatch.setattr("bear.top.os.scandir", make_scandir([2]))
        monkeypatch.setattr("builtins.open", fake_open_start)
        from bear.top import ProcessMonitor

        monitor = ProcessMonitor(total_ram_kb=TOTAL_RAM_KB)
        monitor.start_monitoring()

        def fake_open_poll(path, mode="r", *args, **kwargs):
            if path == "/proc/stat":
                return mock_open(read_data="cpu  10000 0 0 0 0 0 0 0 0 0\n")()
            if path == "/proc/2/stat":
                return mock_open(read_data=FAKE_STAT_LINE)()
            if path == "/proc/2/status":
                return mock_open(read_data=FAKE_STATUS_KERNEL_THREAD)()
            if path == "/proc/2/comm":
                return mock_open(read_data="kworker\n")()
            raise FileNotFoundError(path)

        monkeypatch.setattr("builtins.open", fake_open_poll)
        processes = monitor.get_processes()
        assert len(processes) == 1
        assert processes[0].memory_usage == pytest.approx(0.0)

    def test_snapshot_state_updated_between_polls(self, monkeypatch):
        """Second poll uses the updated snapshot, not the original."""
        from bear.top import N_CORES

        monitor = make_integration_monitor(
            monkeypatch,
            pids=[1234],
            pid_stats={1234: (0, 0, 8192)},
            sys_tick_sequence=[0],
        )
        # first poll: ticks 0→100, sys 0→1000
        monkeypatch.setattr("bear.top.os.scandir", make_scandir([1234]))
        monkeypatch.setattr(
            "builtins.open", make_proc_open({1234: (100, 0, 8192)}, [1000])
        )
        first = monitor.get_processes()

        assert first[0].cpu_usage == pytest.approx(10.0 * N_CORES)

        # second poll: ticks 100→200, sys 1000→2000
        # monkeypatch.setattr("bear.top.os.scandir", make_scandir([1234]))
        monkeypatch.setattr(
            "builtins.open", make_proc_open({1234: (200, 0, 8192)}, [2000])
        )
        second = monitor.get_processes()
        assert second[0].cpu_usage == pytest.approx(10.0 * N_CORES)
