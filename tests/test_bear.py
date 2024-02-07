import logging
from unittest.mock import Mock

from lxml import etree, objectify

from bear.bear import Bear, dbus_method

logger = logging.getLogger()
logger.setLevel(logging.ERROR)


def assert_xml_equivalent(result, expected):
    obj1 = objectify.fromstring(expected)
    expect = etree.tostring(obj1)
    obj2 = objectify.fromstring(result)
    result = etree.tostring(obj2)
    assert expect == result


def test_xml():
    class TestBear(Bear):
        name = "test"

        @dbus_method()
        def homti(self):
            pass

        @dbus_method()
        def tom(self):
            pass

    bear = TestBear(session_bus=Mock(), system_bus=Mock())
    expected_xml = """
        <node>
            <interface name="org.robinramael.bear.TestBear">
                <method name="Homti"/>
                <method name="Tom"/>
            </interface>
        </node>
    """
    assert_xml_equivalent(bear.__dbus_xml__, expected_xml)


def test_xml_with_args():
    class TestBear(Bear):
        name = "test"

        @dbus_method()
        def homti(self, n: int, name: str):
            pass

    bear = TestBear(session_bus=Mock(), system_bus=Mock())
    expected_xml = """
        <node>
            <interface name="org.robinramael.bear.TestBear">
                <method name="Homti">
                    <arg name="n" type="i" direction="in" />
                    <arg name="name" type="s" direction="in" />
                </method>
            </interface>
        </node>
    """
    assert_xml_equivalent(bear.__dbus_xml__, expected_xml)
