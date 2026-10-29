"""Connector positions from a part's view SVG, in sketch px at 90 DPI.

A breadboard wire must end on the pin centre: Fritzing does not snap a
breadboard wire (wireFlags 64) to its connector when it loads a sketch.
Positions are relative to the part's top-left corner, which is the
instance geometry x/y.
"""

from __future__ import annotations

import math
import os
import re
import xml.etree.ElementTree as ET

Matrix = tuple[float, float, float, float, float, float]  # a b c d e f (SVG order)
IDENTITY: Matrix = (1, 0, 0, 1, 0, 0)
UNIT_PX = {"in": 90.0, "mm": 90 / 25.4, "cm": 900 / 25.4, "pt": 90 / 72, "px": 1.0, "": 1.0}
VIEW_TAGS = {"breadboard": "breadboardView", "schematic": "schematicView", "pcb": "pcbView"}


def svg_path(parts_root: str, fzp_path: str, image: str) -> str:
    """Resolve a fzp <layers image="..."> to a file.

    Library parts (path relative to the parts root, e.g. core/x.fzp) keep their
    SVGs in <parts_root>/svg/<folder>/; a local part keeps them next to its fzp.
    """
    if os.path.isabs(fzp_path):
        return os.path.join(os.path.dirname(fzp_path), image)
    folder = fzp_path.split("/", 1)[0]
    return os.path.join(parts_root, "svg", folder, image)


def _mul(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + c * b2, b * a2 + d * b2,
            a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def parse_transform(text: str | None) -> Matrix:
    m = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            r = math.radians(v[0])
            cx, cy = (v[1], v[2]) if len(v) == 3 else (0, 0)
            t = _mul(_mul((1, 0, 0, 1, cx, cy),
                          (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)),
                     (1, 0, 0, 1, -cx, -cy))
        else:
            continue
        m = _mul(m, t)
    return m


def _length_px(text: str | None) -> float | None:
    if not text:
        return None
    mt = re.fullmatch(r"\s*([\d.eE+-]+)\s*([a-z]*)\s*", text)
    if not mt or mt.group(2) not in UNIT_PX:
        return None
    return float(mt.group(1)) * UNIT_PX[mt.group(2)]


def _root_matrix(root: ET.Element) -> Matrix:
    """viewBox user units -> 90 DPI px, from width/height and viewBox."""
    vb = [float(x) for x in re.split(r"[\s,]+", (root.get("viewBox") or "").strip()) if x]
    w, h = _length_px(root.get("width")), _length_px(root.get("height"))
    if len(vb) != 4 or not w or not h:
        return IDENTITY
    sx, sy = w / vb[2], h / vb[3]
    return (sx, 0, 0, sy, -vb[0] * sx, -vb[1] * sy)


def _centre(el: ET.Element) -> tuple[float, float] | None:
    tag = el.tag.rsplit("}", 1)[-1]
    g = lambda k: float(el.get(k, 0))  # noqa: E731
    if tag in ("circle", "ellipse"):
        return g("cx"), g("cy")
    if tag in ("rect", "image", "use"):
        return g("x") + g("width") / 2, g("y") + g("height") / 2
    if tag == "line":
        return (g("x1") + g("x2")) / 2, (g("y1") + g("y2")) / 2
    if tag in ("polygon", "polyline", "path"):
        nums = [float(n) for n in re.findall(r"-?[\d.]+(?:e-?\d+)?",
                                             el.get("points") or el.get("d") or "")]
        if len(nums) < 2:
            return None
        xs, ys = nums[0::2], nums[1::2]  # absolute coords only; good enough for pins
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    if tag == "g":
        pts = [c for c in (_centre(k) for k in el) if c]
        if not pts:
            return None
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    return None


def _find(root: ET.Element, svg_id: str) -> tuple[ET.Element, Matrix] | None:
    stack = [(root, _root_matrix(root))]
    while stack:
        el, m = stack.pop()
        m = _mul(m, parse_transform(el.get("transform"))) if el is not root else m
        if el.get("id") == svg_id:
            return el, m
        stack.extend((child, m) for child in el)
    return None


def pin_positions(fzp_path: str, svg_file: str, view: str = "breadboard") -> dict[str, tuple[float, float]]:
    """connectorId -> (x, y) px from the part's top-left, for one view."""
    return pin_positions_xml(ET.parse(fzp_path).getroot(), ET.parse(svg_file).getroot(), view)


def pin_positions_xml(fzp: ET.Element, svg: ET.Element,
                      view: str = "breadboard") -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for conn in fzp.iter("connector"):
        p = conn.find(f"views/{VIEW_TAGS[view]}/p")
        if p is None or not p.get("svgId"):
            continue
        hit = _find(svg, p.get("svgId"))
        if hit is None:
            continue
        el, m = hit
        c = _centre(el)
        if c is None:
            continue
        a, b, cc, d, e, f = m
        out[conn.get("id")] = (a * c[0] + cc * c[1] + e, b * c[0] + d * c[1] + f)
    return out


def view_image(fzp: str | ET.Element, view: str = "breadboard") -> str | None:
    root = ET.parse(fzp).getroot() if isinstance(fzp, str) else fzp
    layers = root.find(f"views/{VIEW_TAGS[view]}/layers")
    return layers.get("image") if layers is not None else None


def svg_size(svg: ET.Element) -> tuple[float, float] | None:
    """(width, height) of a part's view SVG in 90 DPI px."""
    w, h = _length_px(svg.get("width")), _length_px(svg.get("height"))
    return (w, h) if w and h else None


def length_inside(p: tuple[float, float], q: tuple[float, float],
                  box: tuple[float, float, float, float], inset: float = 0.5) -> float:
    """Length of segment p-q inside box (x0, y0, x1, y1), shrunk by inset.

    The inset keeps a wire that only runs along the edge of a part from
    counting as inside it.
    """
    x0, y0, x1, y1 = box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset
    dx, dy = q[0] - p[0], q[1] - p[1]
    lo, hi = 0.0, 1.0
    for d, start, low, high in ((dx, p[0], x0, x1), (dy, p[1], y0, y1)):
        if d == 0:
            if not low < start < high:
                return 0.0
            continue
        t0, t1 = (low - start) / d, (high - start) / d
        lo, hi = max(lo, min(t0, t1)), min(hi, max(t0, t1))
    return max(0.0, hi - lo) * math.hypot(dx, dy)


def edge_distance(pt: tuple[float, float], box: tuple[float, float, float, float]) -> float:
    """Distance from a point inside box to the nearest edge of the box."""
    return min(pt[0] - box[0], box[2] - pt[0], pt[1] - box[1], box[3] - pt[1])
