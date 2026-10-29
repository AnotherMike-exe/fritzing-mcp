"""Locate the Fritzing app, its parts library, and the user's local_parts folder.

Two layouts are supported:
- a source checkout (Linux default, ~/code/fritzing/fritzing): <root>/parts, <root>/Fritzing
- a macOS app bundle (default on darwin, /Applications/Fritzing.app):
  Contents/Resources/fritzing-parts, Contents/MacOS/Fritzing

FRITZING_APP_ROOT selects the root; a path ending in ".app" uses the bundle layout.
FRITZING_APP, FRITZING_LOCAL_PARTS and QT_QPA_PLATFORM override single values.
"""

from __future__ import annotations

import os
import sys
from typing import NamedTuple

MAC_BUNDLE = "/Applications/Fritzing.app"


class Paths(NamedTuple):
    parts_root: str
    fritzing_bin: str
    local_parts: str
    qt_platform: str
    launcher: list[str]
    qt_libs: str
    qt_plugins: str


def resolve(env: dict[str, str], platform: str, home: str) -> Paths:
    root = env.get("FRITZING_APP_ROOT") or (
        MAC_BUNDLE if platform == "darwin" else os.path.join(home, "code/fritzing/fritzing"))
    root = root.rstrip("/")
    if root.endswith(".app"):
        parts_root = os.path.join(root, "Contents/Resources/fritzing-parts")
        binary = os.path.join(root, "Contents/MacOS/Fritzing")
        launcher = ["open", "-a", root]
    else:
        parts_root = os.path.join(root, "parts")
        binary = os.path.join(root, "Fritzing")
        launcher = [os.path.join(os.path.dirname(root), "run-fritzing.sh")]
    if platform == "darwin":
        local = os.path.join(home, "Library/Application Support/Fritzing/Fritzing/local_parts")
        qt = "cocoa"
    else:
        local = os.path.join(home, ".local/share/Fritzing/Fritzing/local_parts")
        qt = "wayland"
    base = os.path.dirname(root)
    return Paths(
        parts_root=parts_root,
        fritzing_bin=env.get("FRITZING_APP") or binary,
        local_parts=env.get("FRITZING_LOCAL_PARTS") or local,
        qt_platform=env.get("QT_QPA_PLATFORM") or qt,
        launcher=launcher,
        qt_libs=env.get("FRITZING_LIBS") or os.path.join(base, "qt6-libs"),
        qt_plugins=env.get("FRITZING_PLUGINS") or os.path.join(base, "qt6-plugins"),
    )


PATHS = resolve(dict(os.environ), sys.platform, os.path.expanduser("~"))
