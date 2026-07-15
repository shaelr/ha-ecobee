# ha-ecobee

A HACS-installable fork of Home Assistant core's `ecobee` integration. Since
the domain stays `ecobee`, installing this via HACS makes Home Assistant
load it in place of the core integration automatically — no need to
disable/remove core first.

## Repo layout

```
custom_components/ecobee/   # the integration itself
hacs.json                   # HACS metadata (repo root, required)
```

Everything HA-facing lives under `custom_components/ecobee/`. `manifest.json`
there is the source of truth for the installed version.

## Sibling repo: python-ecobee-api

This integration depends on **[shaelr/python-ecobee-api](https://github.com/shaelr/python-ecobee-api)**,
a separate fork of `nkgilley/python-ecobee-api`, referenced in
`manifest.json`'s `requirements` via a pinned git URL:

```
"python-ecobee-api @ git+https://github.com/shaelr/python-ecobee-api.git@vX.Y.Z"
```

**It's deliberately not vendored into this repo.** It's kept as its own
package specifically so it can be PR'd upstream independently of this HA
component. If you add a `pyecobee` method this integration needs, it goes in
that repo, gets its own version bump/tag/release there, and this repo's
`manifest.json` requirement gets bumped to point at the new tag.

A local checkout of it lives at `python-ecobee-api-master/` next to this
repo (gitignored here — it's its own git repo, never nested into this one's
history).

## Release process (HACS requires this exact sequence)

HACS requires `manifest.json`'s `"version"` to match the release tag
**exactly**, or it flags the repo as invalid. For every release:

1. Bump `"version"` in `custom_components/ecobee/manifest.json`.
2. Commit, push to `main`.
3. `git tag -a vX.Y.Z -m "..."` , push the tag.
4. `gh release create vX.Y.Z --repo shaelr/ha-ecobee --title "vX.Y.Z" --notes "..."`.

Roughly semver: patch for bugfixes, minor for new entities/features.

**Only push/tag/release when the user explicitly asks.** Implement and
commit locally by default; wait for an explicit "push and release it"
before touching the remote. Same rule applies to the `python-ecobee-api`
sibling repo.

## No live test environment

There is no running Home Assistant instance or real ecobee thermostat
available while developing this. Verification is limited to:

- `python3 -m py_compile` on changed files
- Standalone Python scripts that exercise the pure logic (slot math, F/C
  conversion, rounding, etc.) with mocked data, since `homeassistant` isn't
  installed locally either — pull it into a throwaway venv
  (`python3 -m pip download homeassistant --no-deps`) to check specific
  HA core API behavior when needed (this has been necessary more than once —
  see the entity-update-timing history below).

Real-device testing happens only after the user installs a release via
HACS and reports back. Several past "fixes" needed a second pass once
tested live — see git log for that history before assuming a fix is
correct on the first attempt.

## Key architectural decisions

### Comfort-setting entities are on the main thermostat device, not their own

Home/Away/Sleep (and any custom comfort settings) each have a Heat Temp /
Cool Temp (`number`), Fan mode (`select`), and — Home/Sleep only — Start
Time (`time`) entity. These were briefly split into their own
`via_device`-linked sub-devices (v0.3.0) to visually separate them, but that
was **reverted** (v0.3.1): it cluttered Settings → Devices & Services with
one extra device per comfort setting, and didn't get the "tap for a rich
popup" UX that was actually wanted — that's a frontend feature hardcoded to
the `climate` domain, not something achievable via device grouping without
shipping a custom Lovelace card (a separate, much bigger project).

Current approach: all comfort-setting entities stay on the main thermostat
device, marked `entity_category: EntityCategory.CONFIG` so HA collapses them
into their own expandable "Configuration" section. Grouping by comfort
setting is otherwise just the entity name prefix (`"Home Heat Temp"`, etc.)
sorting together alphabetically — `entity_category` only has two non-default
values (`config`/`diagnostic`), it can't express "which of N comfort
settings this belongs to."

### Start Time entities are scoped to Home/Sleep only

`time.py`'s `EcobeeComfortStartTime` only exists for comfort settings named
exactly `"Home"` or `"Sleep"` (`DAILY_START_TIME_CLIMATES` in that file). A
single "start time" only cleanly represents a comfort setting that occupies
one contiguous block per day — true for a simple Home/Sleep daily cycle, not
guaranteed for Away or custom settings. Setting it moves that comfort
setting's first daily transition on **all 7 schedule days at once**, reusing
`set_schedule_slots`. For anything more complex than a two-state day, that's
what the Schedule calendar is for.

### Schedule calendar: paint semantics, no delete

`calendar.py`'s `EcobeeScheduleCalendar` represents `program.schedule` (7
days × 48 half-hour slots) as calendar events. Creating/moving/resizing an
event **repaints** whichever slots the new event footprint covers — no
special "clear the old range" step is needed, because the schedule is a raw
grid; whatever's left over from the previous footprint is just whatever was
already there. `DELETE_EVENT` is intentionally **not** supported: every slot
always belongs to *some* comfort setting, so there's no valid "empty" state
to delete into — this was an explicit product decision, not an oversight.

**Unverified assumption, flagged in `const.py`**:
`SCHEDULE_WEEKDAY_TO_ECOBEE_DAY_INDEX_OFFSET` assumes `program.schedule[0]`
is Sunday (per ecobee's API docs), converting Python's `date.weekday()`
(Monday=0) accordingly. This has not been confirmed against a live account.
If a user reports the calendar showing the wrong weekday for a schedule
block, this offset is the first thing to check — it's a one-line fix.

### Two different fixes for "the UI shows stale data after editing"

This came up repeatedly (v0.3.2–v0.3.4) and has two genuinely different root
causes depending on which pyecobee method is involved:

- **Methods that mutate the local cache before POSTing**
  (`set_climate_temperatures`, `set_climate_fan_mode`, `set_schedule_slots`,
  `update_climate_sensors` — the "read program, patch climates/schedule,
  re-POST the whole program" family in `pyecobee/__init__.py`): the new
  value is available locally immediately, no network round trip needed. The
  entity should push it via `schedule_update_ha_state()` /
  `async_write_ha_state()` directly. **Do not** follow up with an extra
  `await self.data.update(no_throttle=True)` — that was an actual bug
  (calendar.py, fixed in v0.3.4): it races ecobee's own eventual
  consistency and can momentarily re-display the stale pre-edit value.
- **Methods that only POST, no local mutation** (`set_hold_temp`,
  `set_hvac_mode`, `set_fan_mode`, etc. — most of `climate.py`'s `Thermostat`
  setters): there's no local value to reflect optimistically. Use
  `self.schedule_update_ha_state(force_refresh=True)` (verified against HA
  core source: thread-safe, and forces an immediate `async_update()` rather
  than waiting for the next scheduled poll) — see `Thermostat._refresh_after_write()`.

### Temperature number entities do their own F↔C conversion

`EcobeeComfortTemp` (number.py) does **not** declare `FAHRENHEIT` as its
native unit and let HA's automatic unit conversion handle display. HA
converts a declared `native_step` by the raw F/C ratio, which turns a clean
0.5 into a non-round value (0.5F × 5/9 ≈ 0.28C) — the entity would silently
stop stepping in real half-degrees once the user's HA is Celsius-configured.
Instead, `native_unit_of_measurement` is a property that always reports
whatever `hass.config.units.temperature_unit` currently is, and the entity
converts F↔C itself, so `native_step = 0.5` is always exactly 0.5 in
whichever unit is shown, matching how ecobee's own app/thermostat step.

Two related landmines already hit and fixed here, worth knowing before
touching this code again:
- `native_min_value`/`native_max_value` must also be aligned to the step
  grid (floor the min, ceil the max) — a raw conversion of round Fahrenheit
  bounds (7°F, 95°F) lands on non-round Celsius values, and stepper widgets
  anchor their increments to that baseline, producing off-grid decimals.
- ecobee stores values in Fahrenheit tenths, so even a value that started
  as a clean half-degree in some other unit doesn't necessarily convert
  back to a clean multiple of `native_step` — round after converting, both
  on read and on write.

### heatCoolMinDelta enforcement

`util.py`'s `enforce_heat_cool_min_delta()` is the shared helper: if a
requested heat/cool pair is closer together than
`settings.heatCoolMinDelta` allows, it spreads both values apart
symmetrically around their midpoint (not favoring whichever value was
passed first). Used in two places that need it independently:
- `climate.py`'s `set_auto_temp_hold` (the two-handle dial drag in Heat/Cool
  mode — previously sent whatever was requested with zero validation).
- `number.py`'s `EcobeeComfortTemp.set_native_value` — Heat Temp and Cool
  Temp are separate entities/API calls per comfort setting, so setting one
  looks up the sibling field's current value and sends both together in one
  `set_climate_temperatures` call.

The raw value is also exposed read-only as `sensor.EcobeeHeatCoolMinDelta`
(`sensor.py`, one per thermostat, `entity_category: DIAGNOSTIC`).

**A third F/C conversion landmine, distinct from the two in the section
above**: this sensor's value is a temperature *delta* (an interval), not an
absolute reading. It originally declared `FAHRENHEIT` as native and let
HA's automatic `device_class=TEMPERATURE` conversion handle display — which
is wrong for a delta, because that conversion applies the full absolute-
value formula `(F-32)*5/9`. A 2°F gap rendered as **-16.7°C** instead of the
correct ~1.1°C gap (confirmed against a live account). Fixed the same way
as `EcobeeComfortTemp`: `native_unit_of_measurement` is a property
reporting whatever HA is configured for, and the conversion is done
manually with a pure ratio (`* 5/9`, no offset). **Any future entity that
represents a temperature difference/interval rather than a point-in-time
reading needs this same treatment** — don't reach for
`device_class=TEMPERATURE` + a fixed native unit + HA's automatic
conversion by default; check whether the value is a delta first.

## Open thread: a custom dashboard card

The user has a separate custom Lovelace card for this integration (built in
a different conversation/session, not part of this repo) and was mid-way
through deciding whether the current entity shape (10+ flat entities in the
thermostat's Configuration section: Heat Temp/Cool Temp/Fan per comfort
setting, Start Time for Home/Sleep) is easy to build that card against, or
whether the entities themselves should be restructured first. Nothing's
been decided yet — this needs the card's actual YAML/code (ask the user for
it; it isn't saved anywhere in this repo or elsewhere on the local
filesystem as of this writing) before making a call either way.
