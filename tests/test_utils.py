from bear.utils import BearLevel


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
