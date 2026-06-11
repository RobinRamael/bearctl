# CLAUDE.md

Guidance for working in this repository.

## What this is

`bearctl` is the backend daemon for a hand-rolled desktop environment. It watches
system state (battery, network, bluetooth, volume, systemd services, CPU/mem, …)
and pushes it into [eww](https://github.com/elkowar/eww) widgets, while exposing
DBus methods so the widgets (and the CLI) can act back on the system (toggle
bluetooth, pause a service, etc.).

The whole thing is a session DBus service named `org.robinramael.bear.BearCtl`
(`HomtiBearCtl` when `DEBUG` is set — see `in_debug_mode()`), built around three
collaborating abstractions: **Bears**, **Pokes**, and **Views**.

## Core concepts

A **Bear** (`bear/bear.py`) is one unit of functionality (one widget's worth of
state). It owns some pokes and some views. Subclass `Bear`, give it a `name`, and
decorate with `@bears.recruit` to register it. `build_context()` merges every
poke's data plus `get_extra_context()` into one dict; that dict is handed to each
view's `render()`. Override `get_extra_context()` to derive display values
(status strings, icon names) from raw poke data.

A **Poke** (`bear/poke.py`) is a source of state that "pokes" its bears when the
state changes, triggering a re-render. The important subclasses:

- `ProxyPoke` — tracks DBus object properties, re-pokes on `PropertiesChanged`.
- `PollingPoke(interval, poller=...)` — calls `poller()` every `interval` seconds
  and pokes only when the value changed. Use for things without a DBus signal
  (shelling out to a CLI, reading psutil). `single_value=True` (default) exposes
  the polled value under the poke's attribute name; `single_value=False` merges
  the returned dict's keys straight into the bear context.
- `MultiProxyPoke` + a `Provider` (`DBusObjectsProvider` / `DBUSServiceProvider`)
  — tracks a dynamic set of DBus objects (e.g. every bluetooth device).
- Plain `Poke` subclass with a background thread for bespoke event sources
  (see `VolumePoke`).

A **View** (`BearView`) renders context. The common ones:

- `EwwPrefixView(var_names=[...], prefix=...)` — for each name in `var_names`
  present in the context, sets eww variable `{prefix}_{name}` (prefix defaults to
  the bear name). This is the usual choice.
- `EwwJSONView(var_name=...)` — dumps the context (or one key) as JSON into one
  eww variable. Use for lists/structured data.
- `DebugView(keys=...)` — logs context at DEBUG level; attach one while developing.

`icon_name` values emitted into the context are *semantic names* (e.g.
`WIFI_OFF_ICON`), not glyphs — the eww config (a separate repo) maps them to icons.

## DBus methods & actions

Decorate a bear method with `@dbus_method(*arg_transformers)` to expose it on the
bus. The transformers are callables applied to each (string) argument from the CLI
client and also drive the generated DBus XML. Method names are CamelCased on the
wire (`toggle_connect` → `ToggleConnect`); `snake2camel` handles the conversion and
the client converts back.

`ActionableBear` adds a generic `action(name)` dbus method that dispatches
`"left_click"`, `"right_click"`, `"double_left"` to `on_left_click()` etc., so eww
buttons can bind to one method.

Long-running work (connecting, scanning) should run in a `threading.Thread` so it
doesn't block the GLib main loop — see `BluetoothBear._toggle_connect`.

## Registering a new bear

1. Create `bear/<thing>.py` with a `@bears.recruit`-decorated `Bear` subclass.
2. **Add `from . import <thing>` to `bear/__init__.py`** — recruitment only happens
   when the module is imported, and this is the only place that imports them.

## Running & developing

This is a Nix flake project; `direnv`/`nix develop` provides the dev shell.

- Run the daemon: `bearctl service` (all bears) or `bearctl service <name> ...`
  (specific bears; `control` is always included). Useful flags: `--no-eww`
  (don't touch eww), `--reload` (hupper auto-reload), `--verbosity debug`,
  `--debug <module>` (DEBUG for `bear.<module>`), `--color`.
- Call a method: `bearctl client <bear-name> <command> [args...]`
  e.g. `bearctl client bluetooth toggle_connect AA:BB:CC:DD:EE:FF`.
- `control` bear: `bearctl client control refresh_all`,
  `bearctl client control set_log_level <module> <level>`.
- Tests: `pytest`. Lint/format: `ruff`. Build: `nix build`.

Bears that fail to initialize are logged and skipped, so the daemon keeps running.
DEBUG mode (`DEBUG=1`) registers under separate DBus names so a debug instance can
run alongside the real one.
