"""Headless Fritzing rendering: .fzz -> SVG (via app CLI) -> PNG (via ImageMagick).

Verified loop (Fritzing develop build at ~/code/fritzing):
  QT_QPA_PLATFORM=wayland \
  LD_LIBRARY_PATH=~/code/fritzing/qt6-libs \
  QT_PLUGIN_PATH=~/code/fritzing/qt6-plugins \
  Fritzing -svg <dir>
renders <name>_breadboard.svg / _schematic.svg / _pcb.svg for every *.fzz in <dir>.
"""

from __future__ import annotations

import os
import subprocess
import sys

_APP_ROOT = os.environ.get("FRITZING_APP_ROOT") or os.path.expanduser(
    "~/code/fritzing/fritzing")
FRITZING_BIN = os.environ.get("FRITZING_APP", os.path.join(_APP_ROOT, "Fritzing"))
QT6_LIBS = os.environ.get("FRITZING_LIBS",
                          os.path.join(os.path.dirname(_APP_ROOT), "qt6-libs"))
QT6_PLUGINS = os.environ.get("FRITZING_PLUGINS",
                             os.path.join(os.path.dirname(_APP_ROOT), "qt6-plugins"))

VIEW_SUFFIX = {"bb": "breadboard", "sc": "schematic", "pcb": "pcb"}


def _app_env() -> dict[str, str]:
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = QT6_LIBS + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    env["QT_PLUGIN_PATH"] = QT6_PLUGINS + (":" + env["QT_PLUGIN_PATH"] if env.get("QT_PLUGIN_PATH") else "")
    env.setdefault("QT_QPA_PLATFORM", "wayland")
    return env


def render(target: str, png: bool = False, density: int = 150,
           view: str = "all") -> int:
    target = os.path.abspath(target)
    if os.path.isfile(target):
        workdir = os.path.dirname(target)
        if os.path.basename(target) not in os.listdir(workdir):
            raise FileNotFoundError(target)
    elif os.path.isdir(target):
        workdir = target
        if not any(f.lower().endswith((".fzz", ".fz")) for f in os.listdir(workdir)):
            print(f"error: no .fzz/.fz sketches in {target}", file=sys.stderr)
            return 1
    else:
        raise FileNotFoundError(target)

    # The app CLI scans `dir` for sketches and writes outputs next to them.
    proc = subprocess.run(
        [FRITZING_BIN, "-svg", workdir],
        env=_app_env(), capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        print(f"error: Fritzing -svg failed (exit {proc.returncode})\n"
              f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}", file=sys.stderr)
        return 1

    from .model import resolve_view_token
    wanted = [VIEW_SUFFIX[v] for v in resolve_view_token(view)]

    produced = []
    for f in sorted(os.listdir(workdir)):
        base, ext = os.path.splitext(f)
        if ext.lower() not in (".fzz", ".fz"):
            continue
        for suffix in wanted:
            svg = os.path.join(workdir, f"{base}_{suffix}.svg")
            if os.path.exists(svg) and os.path.getsize(svg) > 0:
                produced.append(svg)
    if not produced:
        print("error: render produced no SVGs (app ran but wrote nothing) — "
              "check that the sketch is in the scan dir", file=sys.stderr)
        return 1
    for svg in produced:
        print(f"svg  {svg}")

    if png:
        import shutil
        if shutil.which("magick") is None and shutil.which("convert") is None:
            print("warning: ImageMagick not found; skipping PNG", file=sys.stderr)
            return 0
        binary = "magick" if shutil.which("magick") else "convert"
        for svg in produced:
            png_path = svg[:-4] + ".png"
            proc = subprocess.run(
                [binary, "-density", str(density), svg, png_path],
                capture_output=True, text=True, timeout=60)
            if proc.returncode == 0 and os.path.exists(png_path):
                print(f"png  {png_path}")
            else:
                print(f"warning: rasterize failed for {svg}: {proc.stderr.strip()}",
                      file=sys.stderr)
    return 0
