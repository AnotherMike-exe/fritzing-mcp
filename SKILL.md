---
name: fritzing
description: Read, edit, and create Fritzing circuit designs (.fzz sketches) and custom parts (.fzp/.fzpz). Use when the user asks to build, modify, inspect, or visually check an electronics design with Fritzing, or to author new Fritzing parts.
---

# Fritzing AI design toolkit

Drive the locally-built Fritzing app (develop branch, Qt 6.11.2) through the `fz` CLI. Work on files — the GUI is only for final human review.

## Environment

| thing | value |
|---|---|
| CLI | `~/code/fritzing-ai/bin/fz` (add `alias fz=~/code/fritzing-ai/bin/fz`) |
| App | `~/code/fritzing/fritzing/Fritzing` (launcher `~/code/fritzing/run-fritzing.sh`) |
| Parts DB | `~/code/fritzing/fritzing/parts/parts.db` (2663 parts) |
| Custom parts dir | `~/.local/share/Fritzing/Fritzing/local_parts/<ModuleID>/` |
| Sketch units | pixels at 90 DPI (1 inch = 90 px; mm→px = 90·mm/25.4) |

All Python, no dependencies. ImageMagick (`magick`) is used for PNG rasterizing.

## The design loop

Iterate: **new → parts → place → wire → render → look → adjust**.

```bash
cd ~/code/fritzing-ai
bin/fz new /tmp/design/demo.fzz                    # empty sketch
bin/fz parts --query "resistor" --limit 10         # find parts (also scans local custom parts)
bin/fz place /tmp/design/demo.fzz ResistorModuleID --x 300 --y 250 --ref r1 --prop resistance=220
bin/fz place /tmp/design/demo.fzz 3mmColorLEDModuleID --x 500 --y 250 --ref led1
bin/fz wire /tmp/design/demo.fzz r1.connector1 led1.connector1   # pin1 -> anode
bin/fz render /tmp/design --png                    # writes demo_breadboard.{svg,png} etc.
```

Then **read the rendered PNG with vision** (`read .../demo_breadboard.png`) and adjust positions with `fz move` / wire colors with `fz wire --color #ff0000`. Iterate until the layout looks right.

- `fz place` prints the assigned instance ref (default: label + counter, e.g. `R1`). Use that ref everywhere.
- `fz place --view bb|sc|pcb|all` limits which views the part exists in (default all three).
- `fz wire --view bb|sc|pcb|all` (default bb). Wire visuals run between instance origins.
- `fz show <file> --json` dumps full structure; plain `fz show` is a compact list.
- `fz check <file>` MUST pass before you hand a design off or open it in the GUI.
- `fz open <file>` opens the design in the real GUI app for the user.

## Part discovery

`bin/fz parts --query <text>` searches moduleId/title/label/family/tags and merges custom parts from `local_parts`. `--verbose` shows family/source. Common anchors:

| part | moduleID | connectors |
|---|---|---|
| Generic Breadboard | `BreadboardModuleID` | hole grid |
| Resistor | `ResistorModuleID` | connector0 "Pin 0", connector1 "Pin 1" |
| LED 3mm | `3mmColorLEDModuleID` | connector0 cathode, connector1 anode |
| Wire | `WireModuleID` | built-in, never place manually |

Find a part's connector ids with `fz parts -q <name>` then checking the connector table: connectors are named like `connector0`, `connector1` … and `fz parts` does not print them — use `python3 -c` with `fzkit.partsdb.connectors("ModuleID")` or read the part's `.fzp` (`<connector id=... name=...>`).

## Authoring a custom part

Write a JSON spec (see `examples/simple-sensor.json`), then:

```bash
bin/fz part new mypart.json --install     # generates fzp + 4 SVGs, validates, installs
bin/fz parts --query "mypart"             # confirm it is discoverable
```

Spec schema: `title`, `label`, `family`, `tags[]`, `description`, `properties{}`, `pins[{name,type}]`, and `geometry` with per-view `pins` coordinate arrays **in the same order as `pins`**:

- `breadboard: {w,h,color,pins}` — body rect + gold pin circles
- `schematic: {w,h,pins}` — symbol box + labeled pins
- `pcb: {w,h,padD,holeD,pins}` — copper pads + silkscreen outline

`--install` copies to `local_parts/<ModuleID>/` (the highest-priority SVG search path). **Restart Fritzing** afterwards — parts are scanned at startup. Generated fzp passes are checked by the bundled `fzp_checker.py` plus structural checks.

## Validation

`bin/fz check <file>` verifies: unique modelIndexes, all moduleIds resolvable (db or local_parts), every instance has ≥1 view, every wire endpoint connector exists on its target. Fix every reported problem before finishing.

## Format cheat-sheet (for direct XML work)

- `.fzz` = ZIP containing `<Name>.fz` (+ optional `part.*.fzp` / `svg.*.svg` entries for bundled custom parts, + code files).
- `.fz` = `<module fritzingVersion icon>` → `<project_properties>`, `<views>` (view settings), `<instances>`.
- instance = `<instance moduleIdRef modelIndex path?>` → `<property name value>*`, `<title>`, `<views>` → per-view `<geometry z x y>` (parts) or `+x1 y1 x2 y2 wireFlags` (wires) + `<wireExtras mils color opacity banded>` + `<connectors><connector connectorId layer><geometry x y/><connects><connect connectorId modelIndex layer/></connects>`.
- Wire layer tokens (verified): breadboard wire `breadboardWire` / connect-to-part `breadboardbreadboard`; schematic `schematicTrace` / `schematic`; pcb `copper0` / `copper0`.
- Wires connect electrically via the explicit `<connect>` elements — geometry only affects the drawing.

## Quirks

- The app always reports 2 missing built-in parts (`NotoSchematicLogoTextModuleID`, `v5NetLabelModuleID` — upstream bug, a referenced SVG was never committed). Harmless; ignore.
- First `fz render` per session takes ~10 s (parts DB load); renders of several sketches in one dir batch in the same run.
- Custom parts must have all 4 views (icon may reuse the breadboard image) or the app warns "incomplete".
- If the app reports parts missing at startup (e.g. `NotoSchematicLogoTextModuleID`), the checked-in `parts/parts.db` is stale: with an existing db the app skips compiled-in resource parts. Rebuild it (writes a full db incl. resources + local custom parts) and swap it in:
  ```bash
  cd ~/code/fritzing/fritzing
  LD_LIBRARY_PATH=~/code/fritzing/qt6-libs QT_PLUGIN_PATH=~/code/fritzing/qt6-plugins \
    QT_QPA_PLATFORM=offscreen ./Fritzing -db /tmp/parts_new.db
  cp /tmp/parts_new.db parts/parts.db   # backup first
  ```
  Already applied on this machine (2026-09-06).
