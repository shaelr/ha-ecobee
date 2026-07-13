# ecobee (custom)

A HACS-installable fork of Home Assistant's core `ecobee` integration, kept
as a `custom_components/ecobee` override so it can be modified independently
of Home Assistant core releases.

## Install via HACS

1. HACS → Integrations → ⋮ → Custom repositories.
2. Add this repo's URL, category **Integration**.
3. Install "ecobee", then restart Home Assistant.

Because the domain (`ecobee`) matches the core integration, Home Assistant
loads this custom version instead of the core one — no need to remove
anything first, just restart after installing.

## Notes

- Existing `ecobee` config entries carry over unchanged; the domain and
  config flow are untouched from core.
- Version is tracked manually in `custom_components/ecobee/manifest.json`.
