from unittest.mock import Mock

from lxml import etree, objectify

from bearctl.bear import Bear, ServiceBear, dbus_method


def assert_xml_equivalent(result, expected):

    obj1 = objectify.fromstring(expected)
    expect = etree.tostring(obj1)
    obj2 = objectify.fromstring(result)
    result = etree.tostring(obj2)
    assert expect == result


def test_xml():
    class TestBear(Bear):
        @dbus_method
        def homti(self):
            pass

        @dbus_method
        def tom(self):
            pass

    bear = TestBear(bus=Mock(), name="test", view=Mock(), icon="bear")
    print(bear.__dbus_xml__)
    expected_xml = """
        <node>
            <interface name="org.robinramael.bear.TestBear">
                <method name="Homti"/>
                <method name="Tom"/>
            </interface>
        </node>
    """
    assert_xml_equivalent(bear.__dbus_xml__, expected_xml)
