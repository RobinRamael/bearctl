from unittest.mock import Mock

import pytest

from bear.poke import MultiPoke


class MockMultiPoke(MultiPoke):
    def create_subpoke(self, key, *args):
        return Mock(key=key)


@pytest.fixture
def multipoke(mocker):
    mpoke = MockMultiPoke()
    mpoke.register(Mock())
    patcher = mocker.patch("bear.poke.GLib.idle_add", new=lambda f, *x, **y: f())
    return mpoke


def test_add_poke(multipoke):
    handler = Mock()
    multipoke.add_handler(handler)

    multipoke.add_subpoke("key1")

    handler.assert_called_once_with()
    multipoke.poke_map["key1"].register.assert_called_once_with(multipoke)
    assert multipoke.last_change_in == "key1"


def test_remove_poke(multipoke):
    handler = Mock()
    multipoke.add_handler(handler)

    subpoke1 = Mock(last_change=50)
    multipoke._add_subpoke("key1", subpoke1)

    subpoke2 = Mock(last_change=99)
    multipoke._add_subpoke("key2", subpoke2)

    subpoke3 = Mock(last_change=32)
    multipoke._add_subpoke("key3", subpoke3)

    multipoke.remove_subpoke("key2")

    assert handler.call_count == 4
    assert multipoke.last_change_in == "key1"
