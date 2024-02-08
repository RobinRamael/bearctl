from abc import ABC, abstractmethod
from collections import ChainMap
from copy import copy
from functools import wraps
import inspect
import logging
from re import L
import threading
import time
from typing import Dict, List, Type

from dasbus.connection import SessionMessageBus, SystemMessageBus
from dasbus.typing import get_dbus_type
from dasbus.xml import XMLGenerator as DBusXML
from gi.repository import GLib

from bear.exceptions import DoubleBearException
from bear.utils import snake2camel
from bear.utils import snake2camel

logger = logging.getLogger(__name__)


def generate_dbus_xml(interface_name: str, methods: dict):
    root = DBusXML.create_node()
    interface = DBusXML.create_interface(interface_name)

    DBusXML.add_child(root, interface)

    for method_name, method in methods.items():
        method_node = DBusXML.create_method(method_name)
        for param_name, param in list(inspect.signature(method).parameters.items())[1:]:
            DBusXML.add_child(
                method_node,
                DBusXML.create_parameter(
                    param_name, get_dbus_type(param.annotation), "in"
                ),
            )
        DBusXML.add_child(interface, method_node)

    return DBusXML.element_to_xml(root)


def dbus_method(*args):
    if len(args) == 1 and type(args[0]) != type:
        logger.warning("Did you call the dbus_args decorator correctly?")

    def decorator(func):
        func.is_dbus_method = True
        func.dbus_args = args

        @wraps(func)
        def decorated(*args, **kwargs):
            func(*args, **kwargs)

        return decorated

    return decorator


class BearClient:
    def __init__(self, bear_class, proxy):
        self.bear_class = bear_class
        self.proxy = proxy

    def call(self, name: str, args):
        bear_method = getattr(self.bear_class, snake2camel(name))

        assert len(bear_method.dbus_args) == len(args), "incorrect n of arguments"

        transformed_args = []

        for arg, transformer in zip(args, bear_method.dbus_args):
            transformed_args.append(transformer(arg))

        if args:
            logger.info(f"transformed args {args} to {transformed_args}")

        camelName = snake2camel(name)

        logger.info("Calling %s on %s", camelName, self.bear_class.name)

        return getattr(self.proxy, camelName)(*transformed_args)


class BearMeta(type):
    def __new__(cls, cls_name, bases, attrs):
        # print(f"{cls_name}.__new__")
        dbus_methods_in_cls = {}
        for key, attr in attrs.items():
            if callable(attr) and getattr(attr, "is_dbus_method", False):
                new_method_name = snake2camel(key)
                dbus_methods_in_cls[new_method_name] = attr

        for method_name, method in dbus_methods_in_cls.items():
            attrs[method_name] = method

        all_dbus_methods = ChainMap(
            *[c._dbus_methods for c in bases], dbus_methods_in_cls
        )
        attrs["_dbus_methods"] = all_dbus_methods

        # we want views to be inheritable, but each bear still
        # needs their own version of the view to register:
        class_views = []
        for c in bases:
            for v in c._class_views:
                class_views.append(copy(v))

        attrs["_class_views"] = class_views

        # this is not the case for pokes (yet?) in my thinking, a poke _should_
        # be shareable, no? one poke can happen to multiple different bears
        attrs["_class_pokes"] = []

        obj = super().__new__(cls, cls_name, bases, attrs)
        return obj


class Bear(metaclass=BearMeta):
    _dbus_methods = {}  # should always be overwritten in BearMeta
    _class_pokes = {}  # idem
    _class_views = []
    name: str
    abstract = False  # we want this to be the default for newsly written bears,
    # but of course this base bear _is_ abstract. all this does is signal to
    # views and pokes not to register with this bear. since the base class
    # doesnt' set any views or pokes on itself, this can be False

    session_bus: SessionMessageBus
    system_bus: SystemMessageBus

    def __init__(self, session_bus, system_bus):
        self.session_bus = session_bus
        self.system_bus = system_bus
        # todo: dasbus can do this for us probably
        dbus_name = self.get_dbus_name()
        self.__dbus_xml__ = generate_dbus_xml(
            f"org.robinramael.bear.{dbus_name}", self._dbus_methods
        )

        self.pokes = self._class_pokes[:]

        for poke in self.pokes:
            assert not hasattr(poke, "bear")
            poke.bear = self
            poke.session_bus = self.session_bus
            poke.system_bus = self.system_bus

        self.views: List[BearView] = self._class_views[:]
        if not self.views:
            logger.warning("Bear %s has no views set!", self.name)

    @classmethod
    def get_dbus_name(cls):
        return f"{snake2camel(cls.name)}Bear"

    def register(self):
        dbus_name = self.get_dbus_name()
        obj_name = f"/org/robinramael/bear/{dbus_name}"
        self.session_bus.publish_object(obj_name, self)
        logger.debug(f"published object {obj_name}")
        path = f"org.robinramael.bear.{dbus_name}"
        try:
            self.session_bus.register_service(path)
            logger.debug(f"registered service {path}")
        except ConnectionError:
            raise DoubleBearException(
                f"Failed to register path {path}. Is another instance of bearctl running?"
            )

        for poke in self.pokes:
            poke.add_handler(self.update)
            poke.register()

        for view in self.views:
            view.register(self)

    @classmethod
    def get_client(cls, bus):
        dbus_name = cls.get_dbus_name()
        proxy = bus.get_proxy(
            (f"org.robinramael.bear.{dbus_name}"),
            f"/org/robinramael/bear/{dbus_name}",
        )

        return BearClient(cls, proxy)

    def refresh(self):
        pass

    def get_extra_context(self):
        return {}

    def build_context(self):
        context = {}
        for poke in self.pokes:
            poke_data = poke.get_data_dict()
            # overlapping_keys = poke_data.keys() & context.keys()
            # if overlapping_keys:
            #     logger.warning("Overlapping keys in poke data: %s", overlapping_keys)

            context.update(poke_data)

        extra_context = self.get_extra_context()
        context.update(extra_context)
        return context

    def update(self):
        context = self.build_context()

        for view in self.views:
            view.render(context)

    def poke(self):
        raise NotImplementedError


class ViewableBear(Bear):
    def __init__(self, bus, name, view):
        super().__init__(bus, name)
        self.view = view

    # legacy purposes. can this be removed?
    def update_view(self, msg, icon, status):
        self.view.update(msg, icon, status)

    def register(self):
        super().register()
        try:
            self.initialize_view()
        except Exception as e:
            logger.exception(f"Failed to initalize view for {self.name}...")

    def initialize_view(self):
        pass

    def refresh(self):
        self.initialize_view()

    def initialize_view(self):
        self.update_widget()

    def refresh(self):
        self.initialize_view()

    def update_widget(self):
        raise NotImplementedError


class ActionableBear(Bear):
    @dbus_method(str)
    def action(self, name: str):
        logger.info(f"Called {name} action on {self.name}")
        if name == "right_click":
            self.on_right_click()
        elif name == "left_click":
            self.on_left_click()
        elif name == "left_click":
            self.on_left_click()
        elif name == "double_left":
            self.on_double_left_click()
        else:
            raise Exception(f"Bear {self.name} rcvd unknown action {name}")

    def on_right_click(self):
        pass

    def on_left_click(self):
        pass

    def on_double_left_click(self):
        pass


class LabelBear(ViewableBear, ActionableBear):
    def __init__(self, bus, name, icon, view, icon_off=None):
        super().__init__(bus, name, view)
        self.view = view
        self.icon = icon
        self.icon_off = icon_off or icon


class BearView(ABC):
    def __set_name__(self, owner: Bear, name):
        owner._class_views.append(self)

    @abstractmethod
    def render(self, context):
        raise NotImplementedError

    def register(self, bear: Bear):
        pass


class DebugView(BearView):
    def render(self, context):
        from pprint import pprint

        pprint(context)


class Bears:
    def __init__(self, system_bus, session_bus):
        self.bear_classes: Dict[str, Type[Bear]] = {}
        self.bears: Dict[str, Bear] = {}
        self.session_bus = session_bus
        self.system_bus = system_bus

    def recruit(self, bear_class: Type[Bear]):
        logger.info(f"Recruiting bear of class {bear_class.__name__}")
        self.bear_classes[bear_class.name or str(bear_class)] = bear_class
        return bear_class

    def initialize(self, bear_name):
        logger.debug(f"registering {bear_name} bear")
        bear = self.bear_classes[bear_name](self.session_bus, self.system_bus)
        bear.register()

        GLib.idle_add(lambda: bear.update(), priority=GLib.PRIORITY_DEFAULT)

        self.bears[bear.name] = bear
        logger.info(f"succesfully registered {bear.name} bear")

    def initalize_all(self):
        for name in self.bear_classes.keys():
            self.initialize(name)

    def initialize_some(self, names):
        for name in names:
            self.initialize(name)

    def get_client(self, name) -> BearClient:
        return self.bear_classes[name].get_client(self.session_bus)


bears = Bears(session_bus=SessionMessageBus(), system_bus=SystemMessageBus())
