from abc import ABC, abstractmethod
from functools import partial
import logging
import re
import threading
import time
from typing import Any, Callable, Dict, Generic, Hashable, List, Optional, Type, TypeVar

from dasbus.client.proxy import get_object_handler, get_object_path
from dasbus.connection import MessageBus, SessionMessageBus, SystemMessageBus
from dasbus.constants import DBUS_FLAG_NONE
from gi.repository import GLib

from bear.eww import EwwLogsListener
from bear.utils import error_mapper, snake2camel

T = TypeVar("T", bound=Type)

logger = logging.getLogger(__name__)


class UnregisteredException(Exception):
    pass


class PokeMeta(type):
    def __new__(cls, cls_name, bases, attrs):
        attrs["_class_pokes"] = []
        attrs["_class_providers"] = []
        return super().__new__(cls, cls_name, bases, attrs)


class Poke(metaclass=PokeMeta):
    data_class: Callable = dict
    name: str
    current_data: Dict[Any, Any]
    last_change: float
    initial: Dict = {}
    providers: List["Provider"]

    _class_pokes = {}  # overwritten in meta
    _class_providers = {}  # overwritten in meta

    def __init__(self, data_class: Optional[Callable] = None, initial=None):
        self.handlers = []
        self.current_data = {}

        if data_class:
            self.data_class = data_class
        elif not hasattr(self, "data_class"):
            self.data_class = dict

        self.sub_pokes = self._class_pokes[:]
        self.providers = self._class_providers[:]

        self.last_change = 0
        if initial:
            self.initial = initial

        self.registered = False

    def poke(self):
        self.last_change = time.time()
        logger.debug(f"{self} was poked, calling handlers {self.handlers}")
        for handler in self.handlers:
            GLib.idle_add(handler, priority=GLib.PRIORITY_DEFAULT)

    def add_handler(self, h):
        def wrapped():
            if not self.registered:
                logger.warning("Trying to do an unregistered poke. Ignoring")
                return
            h()

        self.handlers.append(wrapped)

    def __set_name__(self, owner, name):
        owner._class_pokes.append(self)
        self.name = name

    @property
    def data(self):
        return self.data_class(**self.current_data)

    def get_data_dict(self) -> dict:
        return self.current_data

    def get_initial_data(self):
        return dict(self.initial)

    def set_data(self, new_data):
        self.current_data.update(new_data)
        self.poke()

    def register(self):
        for sub_poke in self.sub_pokes:
            sub_poke.add_handler(self.update)
            sub_poke.register(self)

        for provider in self.providers:
            provider.poke = self
            provider.register(self)

        self.current_data = self.get_initial_data()
        logger.debug(f"Initial data for {self} set to {self.current_data}")
        self.last_change = time.time()

        self.registered = True

    def add_subpoke(self, key, *args):
        raise NotImplementedError

    def remove_subpoke(self, key):
        raise NotImplementedError

    def unregister(self):
        self.registered = False

    def update(self):
        raise NotImplementedError

    def post_init(self):
        for poke in self.sub_pokes:
            poke.post_init()


OBJ_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"


class ObjectManager:
    def __init__(self, bus: MessageBus, service_name: str, obj_path: str):
        self.bus = bus
        self.service_name = service_name
        self.proxy: Any = self.bus.get_proxy(
            service_name,
            obj_path,
            interface_name=OBJ_MANAGER_INTERFACE,
        )

    def get_objects_of_interface(self, interface_name: str):
        for obj_path, interfaces in self.proxy.GetManagedObjects().items():
            if interface_name in interfaces:
                yield obj_path, self.bus.get_proxy(self.service_name, obj_path)


class DBusMixin:
    use_session_bus: bool
    _system_bus: Optional[SystemMessageBus] = None
    _session_bus: Optional[SessionMessageBus] = None

    @property
    def system_bus(self):
        if not self._system_bus:
            self._system_bus = SystemMessageBus(error_mapper=error_mapper)

        return self._system_bus

    @property
    def session_bus(self):
        if not self._session_bus:
            self._session_bus = SessionMessageBus(error_mapper=error_mapper)

        return self._session_bus

    @property
    def bus(self):
        if self.use_session_bus:
            return self.session_bus
        else:
            return self.system_bus

    def objectmanager_for(self, name, path):
        return ObjectManager(
            self.bus,
            name,
            path,
        )


class ProxyPoke(Poke, DBusMixin):
    proxy: Any
    property_names: List[str] = []
    service_name: str = None
    obj_path: str = None
    property_mapping: Dict[str, str] = {}
    interface_name: Optional[str] = None
    interface_names: List[str]

    def __init__(
        self,
        *args,
        service_name=None,
        unique_name=None,
        obj_path=None,
        interface_name=None,
        interface_names=None,
        property_names=None,
        capitalize_first=True,
        property_mapping=None,
        use_session_bus=True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if service_name:
            self.service_name = service_name

        if not self.property_names:
            self.property_names = property_names or []

        assert not (interface_name and interface_names)

        if interface_names:
            self.interface_names = interface_names
        elif interface_name:
            self.interface_names = [interface_name]
        elif self.interface_name:
            self.interface_names = [self.interface_name]

        self.capitalize_first = capitalize_first

        if obj_path:
            self.obj_path = obj_path

        self.unique_name = unique_name

        if property_mapping:
            self.property_mapping = property_mapping

        if not hasattr(self, "use_session_bus"):
            self.use_session_bus = use_session_bus

    def register(self):
        self.proxy = self.get_proxy()

        super().register()

        name = (
            self.unique_name
            or self.service_name
            or get_object_handler(self.proxy)._service_name
        )

        obj_path = self.obj_path or get_object_path(self.proxy)

        self._subscription_id = self.bus.connection.signal_subscribe(
            name,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            obj_path,
            None,
            DBUS_FLAG_NONE,
            callback=self._on_property_change,
            user_data=(),
        )

    def unregister(self):
        if not self._subscription_id:
            raise UnregisteredException

        super().unregister()
        logger.debug(f"Unregistering {self} from PropertiesChanged signal")
        self.bus.connection.signal_unsubscribe(self._subscription_id)

    def get_initial_data(self):
        data = {}

        all_props = {}
        for interface in self.interface_names:
            interface_props = self.proxy.GetAll(interface)
            all_props.update(interface_props)

        for prop in self.property_names:
            data[prop] = all_props[self.transform_variable(prop)].unpack()

        return data

    def on_property_change(self, sender_name, changed):
        if not self.property_names:
            logger.warn(
                f"Change was detected in {self}, but no property names were set."
            )

        change_detected = False
        for prop in self.property_names:
            try:
                changed_value = changed[self.transform_variable(prop)]
                if changed_value != self.current_data[prop]:
                    self.current_data[prop] = changed_value
                    change_detected = True
            except KeyError:
                pass

        if change_detected:
            logger.debug(
                f"Property change in {self}, from {sender_name}, poking bears..."
            )
            logger.debug(f"current data is now {self.current_data}")
            self.poke()

    def transform_variable(self, s: str) -> str:
        try:
            return self.property_mapping[s]
        except KeyError:
            return snake2camel(s, capitalize_first=self.capitalize_first)

    def _on_property_change(
        self,
        connection,
        sender_name,
        object_path,
        interface_name,
        signal_name,
        parameters,
        user_data,
    ):
        _, changed, __ = parameters
        self.on_property_change(sender_name, changed)

    def get_proxy(self):
        if not self.service_name:
            raise TypeError(f"Need service name to build dbus proxy for {self}")

        if not self.obj_path:
            raise TypeError(f"Need obj_path to build dbus proxy for {self}")

        return self.bus.get_proxy(self.service_name, self.obj_path)

    def __str__(self):
        return f"{self.__class__.__name__}({self.service_name, self.unique_name, self.obj_path})"


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
        self.start_polling()

    def start_polling(self):
        GLib.timeout_add_seconds(
            priority=GLib.PRIORITY_DEFAULT,
            function=self.do_poll,
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

    def do_poll(self):
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


class PausablePollingPoke(PollingPoke):

    def __init__(self, *args, start_paused=False, **kwargs):
        super().__init__(*args, **kwargs)

        self.start_event = threading.Event()

        if not start_paused:
            self.start_event.set()

    def unpause(self):
        logger.debug("Unpausing {self}")
        self.start_event.set()
        self.do_poll()
        self.start_polling()

    def pause(self):
        logger.debug("Pausing {self}")
        self.start_event.clear()

    def do_poll(self):
        if self.start_event.is_set():
            logger.info("Start event set, doing poll")
            super().do_poll()
        else:
            logger.info("Start event not set, cancelling next poll")
            return False


class MultiPoke(Poke):
    poke_map: Dict[Hashable, Poke]
    _class_providers: List["Provider"] = []

    def __init__(self):
        super().__init__()
        self.poke_map = {}
        self.last_change_in = None

    @abstractmethod
    def create_subpoke(self, key: Hashable, *args) -> Poke:
        raise NotImplementedError

    def add_subpoke(self, key: Hashable, *args):
        self._add_subpoke(key, self.create_subpoke(key, *args))

    def _add_subpoke(self, key: Hashable, poke: Poke):
        logger.debug(f"Adding subpoke {key}: {poke}")

        poke.add_handler(partial(self.on_proxy_change, key))
        poke.register()
        self.poke_map[key] = poke
        self.last_change_in = key

        if self.registered:
            self.poke()

    def remove_subpoke(self, key) -> Poke:
        proxy_poke = self.poke_map.pop(key)
        proxy_poke.unregister()

        if self.poke_map:
            self.last_change_in, _ = max(
                ((k, poke) for k, poke in self.poke_map.items()),
                key=lambda tup: tup[-1].last_change,
            )
        else:
            self.last_change_in = None

        logger.debug(
            f"Removing subpoke {key}: {proxy_poke}, last change now in {self.last_change_in}"
        )

        self.poke()
        return proxy_poke

    def on_proxy_change(self, key):
        logger.debug(f"{self}: Received change in proxy with key {key}")
        self.last_change_in = key
        self.poke()

    @property
    def data(self):
        if not self.last_change_in:
            assert not self.poke_map
            return None

        try:
            return self.data_class(**self.poke_map[self.last_change_in].current_data)
        except KeyError:
            logger.error(
                f"last changed key {self.last_change_in} was not found in {self.poke_map} of {self}"
            )
            return {}

    @property
    def all_data(self):
        return {
            key: self.data_class(**poke.current_data)
            for key, poke in self.poke_map.items()
        }

    def get_data_dict(self) -> dict:
        return self.all_data


class Provider(ABC):
    poke: Poke

    def __set_name__(self, poke_class: Type[Poke], name):
        poke_class._class_providers.append(self)
        self.name = name

    @abstractmethod
    def register(self, poke: Poke):
        pass


class MultiProxyPoke(MultiPoke, DBusMixin):
    poke_map: Dict[Hashable, ProxyPoke]
    use_session_bus: bool = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.use_session_bus = kwargs.pop("use_session_bus", self.use_session_bus)


class DBUSServiceProvider(Provider, DBusMixin):
    proxy: Any

    def __init__(self, match_on, *args, use_session_bus=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_session_bus = use_session_bus
        self.match_on = match_on

    def register(self, poke):
        logger.debug(f"Registering {self}")
        super().register(poke)

        self.proxy = self.bus.get_proxy("org.freedesktop.DBus", "/org/freedesktop/DBus")

        for service_name in self.proxy.ListNames():
            if self.matches(service_name):
                unique_name = self.proxy.GetNameOwner(service_name)
                self.poke.add_subpoke(unique_name, service_name)

        self.proxy.NameOwnerChanged.connect(self.on_owner_change)

    # completely unintuitively, listening for wether the name owner changed
    # is how we figure out wether new services appear and already existing
    # ones dissappear: new ones have the old empty and dissappearing ones the new
    # empty.
    def on_owner_change(self, bus_name, old, new):
        if old and new:
            logger.warning("Service changed owner. Do we handle this correctly?")

        if self.matches(bus_name):
            if old:
                self.poke.remove_subpoke(old)
            if new:
                self.poke.add_subpoke(new, bus_name)

    def matches(self, service_name):
        return bool(re.search(self.match_on, service_name))


class ProxyProvider(Provider, DBusMixin):
    pass


class DBusObjectsProvider(ProxyProvider):
    obj_manager: Any
    service_name: str
    obj_manager_path: str = "/"
    obj_manager: Any
    interface_name: str

    def __init__(
        self,
        *args,
        service_name=None,
        obj_manager_path=None,
        interface_name=None,
        use_session_bus=True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.use_session_bus = use_session_bus

        if service_name:
            self.service_name = service_name

        if obj_manager_path:
            self.obj_manager_path = obj_manager_path

        if interface_name:
            self.interface_name = interface_name

    def register(self, poke: MultiPoke):
        super().register(poke)

        self.obj_manager = self.objectmanager_for(
            self.service_name, self.obj_manager_path
        )

        for obj_path, _ in self.obj_manager.get_objects_of_interface(
            self.interface_name
        ):
            self.poke.add_subpoke(obj_path)

        self.obj_manager.proxy.InterfacesAdded.connect(self.on_added)
        self.obj_manager.proxy.InterfacesRemoved.connect(self.on_removed)

    def on_added(self, obj_path, interfaces):
        if self.interface_name in interfaces:
            self.poke.add_subpoke(obj_path)

    def on_removed(self, obj_path, interfaces):
        if self.interface_name in interfaces:
            self.poke.remove_subpoke(obj_path)
