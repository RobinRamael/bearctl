from dasbus.error import DBusError, ErrorMapper, get_error_decorator


class DoubleBearException(Exception):
    pass


error_mapper = ErrorMapper()
dbus_error = get_error_decorator(error_mapper=error_mapper)


@dbus_error("org.freedesktop.DBus.Error.InProgress")
class InProgress(DBusError):
    pass


@dbus_error("org.freedesktop.DBus.Error.UnknownObject")
class UnknownObject(DBusError):
    pass
