"""fritzing-mcp: MCP stdio server for building and editing Fritzing designs.

Wraps the `fz` CLI (the Fritzing design toolkit for AI agents). All tools
drive `fz`, which edits .fzz/.fz sketch bundles, queries the parts database,
and renders headless SVG/PNG previews via the local Fritzing app.

The design loop the tools support:
  new -> search_parts -> place_part -> wire -> render -> check -> open (GUI)

Configuration:
  FZ_BIN  absolute path to a `fz` launcher (optional override; the bundled
          toolkit's bin/fz next to this file is used by default)

Run:  uv run --project . fritzing-mcp   (stdio)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP

mcp = FastMCP("fritzing")

_TIMEOUT_S = 300


def _fz() -> str:
    path = (os.environ.get("FZ_BIN")
            or str(Path(__file__).resolve().parent / "bin" / "fz"))
    if not os.path.isfile(path):
        raise RuntimeError(
            f"fz launcher not found at {path!r} — set FZ_BIN to the `fz` CLI")
    return path


def _run(*argv: str, timeout: int = _TIMEOUT_S) -> str:
    # Run fz in this interpreter, so fz and fzp_checker see the server's venv (lxml).
    r = subprocess.run([sys.executable, _fz(), *argv], capture_output=True, text=True,
                       timeout=timeout)
    out = "\n".join(s.strip() for s in (r.stdout, r.stderr) if s and s.strip())
    if r.returncode != 0:
        raise RuntimeError(f"fz {' '.join(argv[:2])} failed (exit {r.returncode}):\n"
                           f"{out or '(no output)'}")
    return out


def _props(props: dict[str, str]) -> list[str]:
    out = []
    for k, v in (props or {}).items():
        out += ["--prop", f"{k}={v}"]
    return out


# ---------------------------------------------------------------------- parts

@mcp.tool
def fritzing_search_parts(
    query: Annotated[str, "substring over module id, title, label, family, tags"],
    limit: int = 40,
    verbose: bool = False,
) -> str:
    """Search the Fritzing parts library (2663 core parts + local custom parts).

    Returns rows of `moduleId  title  [family]  (source)`. Call
    fritzing_part_connectors with a result's moduleId before wiring it.
    """
    argv = ["parts", "--query", query, "--limit", str(limit)]
    if verbose:
        argv.append("--verbose")
    return _run(*argv)


@mcp.tool
def fritzing_part_connectors(
    module_id: Annotated[str, "moduleId from fritzing_search_parts, e.g. 'ResistorModuleID'"],
) -> str:
    """List a part's connector ids, names, and types (male/female/pad) as JSON.

    Connector ids are what wire endpoints reference
    (e.g. "r1.connector1" -> "led1.connector1").
    """
    return _run("connectors", module_id)


# --------------------------------------------------------------- sketch build

@mcp.tool
def fritzing_new_sketch(
    path: Annotated[str, "output path, .fzz or .fz"],
    force: bool = False,
) -> str:
    """Create an empty Fritzing sketch bundle."""
    argv = ["new", path]
    if force:
        argv.append("--force")
    return _run(*argv)


@mcp.tool
def fritzing_place_part(
    file: Annotated[str, "sketch .fzz/.fz path"],
    module_id: str,
    x: float = 300.0,
    y: float = 300.0,
    ref: Annotated[str, "instance reference; default label+counter (e.g. R1)"] = "",
    view: Annotated[str, "bb | sc | pcb | all"] = "all",
    props: Annotated[dict[str, str], "part properties, e.g. {'resistance': '220'}"] | None = None,
) -> str:
    """Add a part instance to a sketch.

    Coordinates are sketch pixels at 90 DPI (1 inch = 90 px; mm -> px = 90*mm/25.4).
    The placed instance's assigned ref is in the output — use it for wire/move/props.
    """
    argv = ["place", file, module_id, "--x", str(x), "--y", str(y)]
    if ref:
        argv += ["--ref", ref]
    if view != "all":
        argv += ["--view", view]
    argv += _props(props)
    return _run(*argv)


@mcp.tool
def fritzing_wire(
    file: str,
    ref_a: Annotated[str, "'ref.connectorId', e.g. 'r1.connector1'"],
    ref_b: Annotated[str, "'ref.connectorId'"],
    view: Annotated[str, "bb | sc | pcb | all"] = "bb",
    color: Annotated[str, "hex color, e.g. '#ff0000'"] = "",
    via: Annotated[list[list[float]], "breadboard bend points [[x, y], ...] in absolute px, in path order"] | None = None,
) -> str:
    """Wire two part connectors together (creates the electrical <connect>).

    An end can also be a wire end, 'Wire7.connector1': the new wire branches
    from that end or bend point. Use a branch for one signal that goes to
    several pins, for example GND. Wire titles are in fritzing_show_sketch.

    The wire ends on the real pin positions from each part's SVG. Bend points
    become a chain of wire segments, as the Fritzing app stores them. Each
    view gets its own wire; `via` applies to the breadboard view only.
    """
    argv = ["wire", file, ref_a, ref_b, "--view", view]
    if color:
        argv += ["--color", color]
    for x, y in via or []:
        argv += ["--via", f"{x:g},{y:g}"]
    return _run(*argv)


@mcp.tool
def fritzing_move_part(file: str, ref: str, x: float | None = None, y: float | None = None) -> str:
    """Move a placed instance (omit x/y to read its current position)."""
    argv = ["move", file, ref]
    if x is not None:
        argv += ["--x", str(x)]
    if y is not None:
        argv += ["--y", str(y)]
    return _run(*argv)


@mcp.tool
def fritzing_set_properties(
    file: str,
    ref: str,
    props: Annotated[dict[str, str], "properties to set, e.g. {'resistance': '10k'}"],
) -> str:
    """Set instance properties (name=value pairs)."""
    if not props:
        raise RuntimeError("props must not be empty")
    return _run("prop", file, ref, *[f"{k}={v}" for k, v in props.items()])


@mcp.tool
def fritzing_remove_part(file: str, ref: str) -> str:
    """Remove an instance from the sketch."""
    return _run("remove", file, ref)


@mcp.tool
def fritzing_show_sketch(file: str) -> str:
    """Dump the sketch's instances (refs, moduleIds, positions, wires) as JSON."""
    return _run("show", file, "--json")


# ----------------------------------------------------------------- validation

@mcp.tool
def fritzing_check(file: str, strict: bool = False) -> str:
    """Validate a sketch: unique modelIndexes, resolvable moduleIds, every
    instance has >= 1 view, every wire endpoint connector exists on its target.
    Also warns when a breadboard wire crosses a part or passes over a pin it
    does not use. strict=True turns those warnings into failures.
    MUST pass before handing a design off or opening it in the GUI."""
    return _run("check", file, *(["--strict"] if strict else []))


@mcp.tool
def fritzing_render(
    target: Annotated[str, "sketch file or directory of sketches"],
    png: bool = True,
    view: Annotated[str, "bb | sc | pcb | all"] = "all",
    density: int = 150,
) -> str:
    """Headless-render sketch(es) to SVG (and optionally PNG via ImageMagick).

    Writes <name>_<view>.svg/.png next to the target. The first render per
    session takes ~10 s (parts DB load). Read the PNG to visually inspect the
    design, then adjust positions/wires and re-render.
    """
    argv = ["render", target, "--view", view, "--density", str(density)]
    if png:
        argv.append("--png")
    return _run(*argv)


# --------------------------------------------------------------- custom parts

@mcp.tool
def fritzing_create_part(
    spec_path: Annotated[str, "path to a part spec JSON (schema in the fzkit docs)"],
    install: Annotated[bool, "install into local_parts so the app discovers it"] = False,
    out: Annotated[str, "output directory for the generated fzp+SVGs"] = "",
    flat: Annotated[bool, "write into `out` itself, not out/<moduleId>/"] = False,
) -> str:
    """Generate a custom part (fzp + 4 view SVGs) from a JSON spec.

    Custom parts must have all 4 views; restart Fritzing after --install
    (parts are scanned at startup). Optional breadboard style keys in
    geometry.breadboard: pin_r, legs, stroke, body, extra, labels
    ([{text?, side}] per pin), label_size, label_color.
    """
    argv = ["part", "new", spec_path]
    if install:
        argv.append("--install")
    if out:
        argv += ["--out", out]
    if flat:
        argv.append("--flat")
    return _run(*argv)


@mcp.tool
def fritzing_validate_part(fzp_path: str) -> str:
    """Validate a .fzp part definition file."""
    return _run("part", "validate", fzp_path)


# ------------------------------------------------------------------- hand-off

@mcp.tool
def fritzing_open_gui(files: Annotated[list[str], "sketch paths to open"]) -> str:
    """Open sketch(es) in the Fritzing GUI for human review."""
    if not files:
        raise RuntimeError("files must not be empty")
    return _run("open", *files)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
