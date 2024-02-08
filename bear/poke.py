from abc import ABC, abstractmethod
import logging
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar

from dasbus.connection import ObjectProxy
from gi.repository import GLib

from bear.bear import Bear
from bear.utils import snake2camel

T = TypeVar("T", bound=Type)

logger = logging.getLogger(__name__)


class Poke(ABC, Generic[T]):
    data_class: Type
    bear: Bear
    name: str
    current_data: Dict[str, Any]

    def __init__(self, data_class: Optional[T] = None):
        self.handlers = []
        self.current_data = {}

        if data_class:
            self.data_class = data_class
        elif not hasattr(self, "data_class"):
            self.data_class = dict

    def poke(self):
        for handler in self.handlers:
            handler()

    def add_handler(self, h):
        self.handlers.append(h)

    def __set_name__(self, owner, name):
        owner._class_pokes.append(self)
        self.name = name

    @property
    def data(self) -> T:
        return self.data_class(**self.current_data)

    def get_data_dict(self) -> dict:
        return self.current_data

    def get_initial_data(self):
        return {}

    def set_data(self, new_data):
        self.current_data.update(new_data)
        self.poke()

    @abstractmethod
    def register(self):
        self.current_data = self.get_initial_data()
        logger.debug(f"Initial data for {self} set to {self.current_data}")


class PropertiesPoke(Poke, Generic[T]):
    proxy: Any  # aka stop being annoying, python type annotations
    interface_name: str
    obj_path: str
    service_name: str
    property_names: List[str] = []  # should be overwritten in implementing class

    def __init__(
        self,
        service_name=None,
        obj_path=None,
        interface_name=None,
        property_names=None,
        use_session_bus=True,
        capitalize_first=True,
    ):
        super().__init__()

        if not self.property_names:
            self.property_names = property_names or []

        self.use_session_bus = use_session_bus

        if service_name:
            self.service_name = service_name

        if obj_path:
            self.obj_path = obj_path

        if interface_name:
            self.interface_name = interface_name

        self.capitalize_first = capitalize_first

    @property
    def bus(self):
        if self.use_session_bus:
            return self.bear.session_bus
        else:
            return self.bear.system_bus

    def register(self):
        self.proxy = self.get_proxy()
        self.register_on(self.proxy)
        self.current_data = self.get_initial_data()

    def get_proxy(self):
        if not self.service_name:
            raise TypeError(f"Need service name to build dbus proxy for {self}")

        if not self.obj_path:
            raise TypeError(f"Need obj_path to build dbus proxy for {self}")

        return self.bus.get_proxy(self.service_name, self.obj_path)

    def register_on(self, proxy):
        proxy.PropertiesChanged.connect(self.on_property_change)

    def get_initial_data(self):
        props = self.proxy.GetAll(self.interface_name)
        data = {}
        for prop in self.property_names:
            data[prop] = props[self.transform_variable(prop)].unpack()

        return data

    def transform_variable(self, s: str) -> str:
        return snake2camel(s, capitalize_first=self.capitalize_first)

    def on_property_change(self, _, changed, __):
        if not self.property_names:
            logger.warn(
                f"Change was detected in {self}, but no property names were set."
            )

        change_detected = False
        for prop in self.property_names:
            try:
                changed_value = changed[self.transform_variable(prop)].unpack()
                if changed_value != self.current_data[prop]:
                    self.current_data[prop] = changed_value
                    change_detected = True
            except KeyError:
                pass

        if change_detected:
            logger.debug(f"Property change in {self}, poking bears...")
            logger.debug(f"current data is now {self.current_data}")
            self.poke()

    def __str__(self):
        return (
            f"{self.__class__.__name__}({self.interface_name}, {self.property_names})"
        )


P = TypeVar("P")


class PollingPoke(Poke, Generic[P]):
    def __init__(
        self,
        interval,
        poller: Optional[Callable[[], P]] = None,
        single_value: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.interval = interval
        self.current_data = {}
        self.poller = poller
        self.single_value = single_value

    def register(self):
        super().register()

        GLib.timeout_add_seconds(
            priority=GLib.PRIORITY_DEFAULT,
            function=self._do_poll,
            interval=self.interval,
        )
        logger.debug(f"polling enabled in {self}")

    def get_initial_data(self):
        return self.poll()

    def __str__(self):
        if self.poller:
            return f"{self.__class__.__name__}(poller={self.poller})"
        else:
            return f"{self.__class__.__name__}()"

    def _do_poll(self):
        prev_data = self.current_data
        logger.debug(f"polling in {self}")
        self.current_data = self.poll()

        if prev_data != self.current_data:
            self.poke()
        else:
            logger.debug(
                f"No state change, not poking any bears, state was {self.current_data}"
            )

        return True

    def get_data_dict(self) -> dict:
        if self.single_value:
            return {self.name: self.current_data}
        else:
            return self.current_data

    @property
    def data(self):
        if self.single_value:
            return self.current_data
        else:
            return super().data

    def poll(self) -> P:
        if self.poller:
            return self.poller()
        else:
            raise NotImplementedError
