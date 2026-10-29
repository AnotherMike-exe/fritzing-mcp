# fritzing-mcp

MCP stdio server for building and editing Fritzing circuit designs (`.fzz`
sketches) and custom parts (`.fzp`/SVGs), wrapping the [`fz`
CLI](https://github.com/fedoragobrowse-design/fritzing-ai) — a
stdlib-only Fritzing design toolkit for AI agents.

## Tools

**Parts**

| tool | purpose |
|---|---|
| `fritzing_search_parts` | search the 2663-part library + local custom parts |
| `fritzing_part_connectors` | list a part's connector ids/names/types (needed before wiring) |

**Sketch build**

| tool | purpose |
|---|---|
| `fritzing_new_sketch` | create an empty `.fzz` bundle |
| `fritzing_place_part` | place a part (coordinates in px at 90 DPI) |
| `fritzing_wire` | wire two connectors (`r1.connector1` → `led1.connector1`) |
| `fritzing_move_part` / `fritzing_set_properties` / `fritzing_remove_part` | adjust instances |
| `fritzing_show_sketch` | dump instances/wires as JSON |

**Validation**

| tool | purpose |
|---|---|
| `fritzing_check` | validate sketch (must pass before hand-off) |
| `fritzing_render` | headless-render SVG/PNG for visual inspection |

**Custom parts**

| tool | purpose |
|---|---|
| `fritzing_create_part` | generate fzp + 4 view SVGs from a JSON spec, optionally install |
| `fritzing_validate_part` | validate a `.fzp` file |

**Hand-off**

| tool | purpose |
|---|---|
| `fritzing_open_gui` | open sketches in the Fritzing GUI for human review |

## Requirements

- Python ≥ 3.10, [uv](https://docs.astral.sh/uv/)
- The `fz` toolkit is bundled (`fzkit/` + `bin/fz` + `templates/`) — no
  second repo needed. `FZ_BIN` optionally points at a different launcher.
- Runtime data from a local Fritzing app. `fzkit/paths.py` finds it:
  - **macOS:** `/Applications/Fritzing.app` by default. Parts come from
    `Contents/Resources/fritzing-parts`, custom parts go to
    `~/Library/Application Support/Fritzing/Fritzing/local_parts`, and Qt uses `cocoa`.
  - **Linux:** a source checkout at `~/code/fritzing/fritzing` by default, with
    `~/.local/share/Fritzing/Fritzing/local_parts` and Qt `wayland`.
  - `FRITZING_APP_ROOT` selects another checkout, or another bundle if it ends in
    `.app`. `FRITZING_APP`, `FRITZING_LOCAL_PARTS`, `FRITZING_LIBS`,
    `FRITZING_PLUGINS` and `QT_QPA_PLATFORM` override single values.

  Part search needs `parts.db`, custom-part checks need `fzp_checker.py`, and
  headless rendering needs the Fritzing binary plus ImageMagick with the librsvg
  delegate for PNG (on Homebrew: `imagemagick-full`). Sketch create/show/check
  work without any of it.

## Install

```sh
uv sync   # or: uv venv && uv pip install -e .
```

## Run

Add to your MCP client config:

```json
{
  "mcpServers": {
    "fritzing": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/fritzing-mcp", "fritzing-mcp"]
    }
  }
}
```

## Smoke test

```sh
bun smoke.mjs    # or: node smoke.mjs
```

Drives the server over raw stdio MCP: searches parts, reads connectors,
builds a LED+resistor sketch (place/wire/move/props), validates it, and
renders the breadboard view. Prints `SMOKE: N/N passed`.

## License

MIT
