from dataclasses import dataclass
from typing import Dict

from dataclasses_json import dataclass_json

from bear.utils import BearLevel
from bear.utils import to_full_dict


def test_level_for_idle():
    result = BearLevel.level_for(9, (10, 30, 60))
    assert result == BearLevel.idle


def test_level_for_info():
    result = BearLevel.level_for(15, (10, 30, 60))
    assert result == BearLevel.info


def test_level_for_warning():
    result = BearLevel.level_for(53, (10, 30, 60))
    assert result == BearLevel.warning


def test_level_for_error():
    result = BearLevel.level_for(104, (10, 30, 60))
    assert result == BearLevel.error


def test_level_for_good_reversed():
    result = BearLevel.level_for(
        65, (10, 30, 60), more_better=True, best=BearLevel.good
    )

    assert result == BearLevel.good


def test_level_for_info_reversed():
    result = BearLevel.level_for(35, (10, 30, 60), more_better=True)

    assert result == BearLevel.info


def test_level_for_warning_reversed():
    result = BearLevel.level_for(15, (10, 30, 60), more_better=True)

    assert result == BearLevel.warning


def test_level_for_error_reversed():
    result = BearLevel.level_for(6, (10, 30, 60), more_better=True)

    assert result == BearLevel.error


@dataclass_json
@dataclass
class Data:
    value: int


@dataclass_json
@dataclass
class Complex:
    mapping: Dict[str, str]
    value: int
    child: Data


def test_simple():
    data = {"foo": Data(value=3)}

    assert to_full_dict(data), {"foo": {"value": 3}}


def test_dict_in_list():
    data = [{"foo": "bar"}]

    assert to_full_dict(data), data


def test_list():
    data = {"bar": [Data(3), Data(2)]}

    assert to_full_dict(data), {"bar": [{"value": 3}, {"value": 2}]}


def test_complex():
    data = [Complex({"frob": "baz"}, 42, Data(4))]

    assert to_full_dict(data), [
        {"mapping": {"frob": "baz"}, "value": 42, "child": {"value": 4}}
    ]
