from dataclasses import is_dataclass
import os
from typing import Iterable, Mapping


def snake2camel(s, capitalize_first=True):
    camel = "".join(word.title() for word in s.split("_"))
    if not capitalize_first:
        camel = camel[0:1].lower() + camel[1:]
    return camel


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


def in_debug_mode():
    os.environ.get("DEBUG", False)


def to_full_dict(value):
    if isinstance(value, str):
        return value
    elif isinstance(value, Mapping):
        return {k: to_full_dict(v) for k, v in value.items()}
    elif isinstance(value, Iterable):
        return [to_full_dict(x) for x in value]
    elif is_dataclass(value):
        return to_full_dict(value.to_dict())
    else:
        return value
