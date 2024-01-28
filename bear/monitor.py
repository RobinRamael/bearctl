import os

from dasbus.loop import GLib

from bear.bear import Bear, LabelBear
from bear.icons import Icons
from bear.views import BearLabel, BlockState


class MonitorBear(LabelBear):
    def __init__(self, *args, interval: int = 5, **kwargs):
        super().__init__(*args, **kwargs)
        self.interval = interval

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

    def update(self):
        raise NotImplementedError


class LoadAverageBear(MonitorBear):
    def __init__(self, *args, levels=(0.3, 0.6, 0.9), **kwargs):
        super().__init__(*args, **kwargs)
        self.levels = levels

    def initialize_view(self):
        self.update()

    def update(self):
        m1, m5, _ = os.getloadavg()

        cpu_count = os.cpu_count() or 1

        rel_m1 = m1 / cpu_count

        state = BlockState.idle

        for level, s in zip(
            self.levels, [BlockState.idle, BlockState.info, BlockState.warning]
        ):
            if rel_m1 < level:
                state = s
                break

        else:
            state = BlockState.error

        self.view.update(icon=self.icon, message=f"{m1:.1f} {m5:.1f}", state=state)
