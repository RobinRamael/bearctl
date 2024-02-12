from unittest.mock import Mock

import pytest

from bear.poke import MultiPoke


@pytest.fixture
def multipoke():
    mpoke = MultiPoke()
    mpoke.session_bus = Mock()
    mpoke.system_bus = Mock()
    mpoke.register()
    return mpoke


def test_add_poke(multipoke):
    handler = Mock()
    multipoke.add_handler(handler)

    subpoke = Mock()
    multipoke.add_subpoke("key1", subpoke)

    handler.assert_called_once_with()
    subpoke.register.assert_called_once_with()
    assert multipoke.last_change_in == "key1"


def test_remove_poke(multipoke):
    handler = Mock()
    multipoke.add_handler(handler)

    subpoke1 = Mock(last_change=50)
    multipoke.add_subpoke("key1", subpoke1)

    subpoke2 = Mock(last_change=99)
    multipoke.add_subpoke("key2", subpoke2)

    subpoke3 = Mock(last_change=32)
    multipoke.add_subpoke("key3", subpoke3)

    multipoke.remove_subpoke("key2")

    assert handler.call_count == 4
    assert multipoke.last_change_in == "key1"
