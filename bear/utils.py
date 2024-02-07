import os
import sys


def snake2camel(s):
    return "".join(word.title() for word in s.split("_"))


class HiddenPrints:
    def __init__(self):
        self._original_stdout = None

    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout


class BearLevel:
    good = "good"
    idle = "idle"
    info = "info"
    warning = "warning"
    error = "error"

    @staticmethod
    def level_for_type_load(val, levels):
        return BearLevel.level_for(
            val, levels, more_better=False, best=BearLevel.idle, worst=BearLevel.error
        )

    @staticmethod
    def level_for_type_battery(val, levels):
        return BearLevel.level_for(
            val, levels, more_better=True, best=BearLevel.good, worst=BearLevel.error
        )

    @staticmethod
    def level_for(val, levels, more_better=False, best=None, worst=None):
        best = best or BearLevel.idle
        worst = worst or BearLevel.error

        order = [worst, BearLevel.warning, BearLevel.info, best]

        if more_better:
            states = order[:-1]
            final = order[-1]
        else:
            states = order[1:][::-1]  # cut off the first one and reverse
            final = order[0]

        for level, state in zip(levels, states):
            if val < level:
                return state

        else:
            return final

        # ... what a mess. is there any way to do this nicely? it's tested, i
        # guess...
