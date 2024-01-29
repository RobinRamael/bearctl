import os

from dasbus.loop import GLib
import psutil

from bear.bear import Bear, LabelBear
from bear.icons import Icons
from bear.views import BearLabel, BlockState


class MonitorBear(LabelBear):
    def __init__(self, *args, levels, interval: int = 5, **kwargs):
        super().__init__(*args, **kwargs)
        self.levels = levels
        self.interval = interval

    def initialize_view(self):
        self.update()

    def register(self):
        super().register()
        self.initialize_view()

        def _update():
            self.update()
            return True

        GLib.timeout_add_seconds(
            priority=GLib.PRIORITY_DEFAULT,
            function=_update,
            interval=self.interval,
        )

    def state_for(self, val):
        for level, state in zip(
            self.levels, [BlockState.idle, BlockState.info, BlockState.warning]
        ):
            if val < level:
                return state

        else:
            return BlockState.error

    def update(self):
        raise NotImplementedError


class LoadAverageBear(MonitorBear):
    def update(self):
        m1, m5, _ = os.getloadavg()

        cpu_count = os.cpu_count() or 1

        state = self.state_for(m1 / cpu_count)

        self.view.update(icon=self.icon, message=f"{m1:.1f} {m5:.1f}", state=state)


class CPUBear(MonitorBear):
    def update(self):
        cpu_perc = psutil.cpu_percent()

        self.view.update(
            icon=self.icon,
            message=f"{cpu_perc:.0f}%",
            state=self.state_for(cpu_perc),
        )


class MemoryBear(MonitorBear):
    def update(self):
        mem_perc = psutil.virtual_memory().percent

        self.view.update(
            icon=self.icon,
            message=f"{mem_perc:>3.0f}%",
            state=self.state_for(mem_perc),
        )


class BearMonitorBear(MonitorBear):
    def update(self):
        process = psutil.Process(os.getpid())
        cpu_perc = process.cpu_percent()

        mem_perc = process.memory_percent()

        self.view.update(
            icon=self.icon,
            message=f"{cpu_perc:>3.0f}% {mem_perc:.0f}%",
            state=self.state_for(cpu_perc),
        )
