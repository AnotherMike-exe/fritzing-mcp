"""Fritzing sketch (.fz) and bundle (.fzz) I/O.

Grounded on the verified Blink.fz reference (Fritzing develop branch):
- .fzz = ZIP with a single top-level <Name>.fz entry (+ code files, part bundles)
- geometry is in pixels at 90 DPI (Fritzing SVGDPI)
- instances are resolved by moduleIdRef via the parts database
"""

from __future__ import annotations

import os
import re
import copy
import xml.etree.ElementTree as ET
import zipfile

FZ_EXT = ".fz"
FZZ_EXT = ".fzz"
WIRE_MODULE_ID = "WireModuleID"

# Layer tokens verified from Blink.fz (Fritzing develop branch):
#   wire_view = layer attr on the wire instance's <xxxView> element
#   wire_conn = layer attr on the wire instance's own <connector> elements
#   part_conn = layer attr on <connect> pointing at a part's connector
#   part_layer = layer attr on a part instance's <xxxView> element
VIEW_TOKENS = {
    "bb": {
        "view": "breadboardView",
        "wire_view": "breadboardWire",
        "wire_conn": "breadboardWire",
        "part_conn": "breadboardbreadboard",
        "part_layer": "breadboard",
        "wire_flags": "64",
        "extras": {"mils": "22.2222", "color": "#418dd9", "opacity": "1", "banded": "0"},
    },
    "sc": {
        "view": "schematicView",
        "wire_view": "schematicTrace",
        "wire_conn": "schematicTrace",
        "part_conn": "schematic",
        "part_layer": "schematic",
        "wire_flags": "128",
        "extras": {"mils": "20", "color": "#000000", "opacity": "1", "banded": "0"},
    },
    "pcb": {
        "view": "pcbView",
        "wire_view": "copper0",
        "wire_conn": "copper0",
        "part_conn": "copper0",
        "part_layer": "board",
        "wire_flags": "4",
        "extras": {"mils": "11.1111", "color": "#f28a00", "opacity": "1", "banded": "0"},
    },
}

VIEW_ORDER = ["bb", "sc", "pcb"]
VIEW_ALIASES = {"bb": "bb", "breadboard": "bb", "sc": "sc", "schematic": "sc",
                "pcb": "pcb", "all": "all"}


def resolve_view_token(name: str) -> list[str]:
    name = VIEW_ALIASES.get(name.strip().lower(), name.strip().lower())
    if name == "all":
        return list(VIEW_ORDER)
    if name not in VIEW_ORDER:
        raise ValueError(f"unknown view '{name}' (expected bb|sc|pcb|all)")
    return [name]


class FzSketch:
    """Parses and rewrites a Fritzing sketch (.fz or .fzz)."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.other_entries: dict[str, bytes] = {}
        self.fz_name: str | None = None
        self.root: ET.Element | None = None
        self._load()

    # ---------- construction ----------

    @classmethod
    def from_template(cls, path: str, template_path: str) -> "FzSketch":
        sketch = cls.__new__(cls)
        sketch.path = os.path.abspath(path)
        sketch.other_entries = {}
        sketch.fz_name = os.path.basename(sketch.path)
        sketch.root = ET.parse(template_path).getroot()
        return sketch

    # ---------- loading ----------

    def _load(self) -> None:
        if self.path.lower().endswith(FZZ_EXT):
            with zipfile.ZipFile(self.path) as z:
                for name in z.namelist():
                    if name.lower().endswith(FZ_EXT):
                        self.fz_name = name
                        data = z.read(name)
                    else:
                        self.other_entries[name] = z.read(name)
            if self.fz_name is None:
                raise ValueError(f"{self.path}: no .fz entry inside bundle")
        else:
            with open(self.path, "rb") as f:
                data = f.read()
            self.fz_name = os.path.basename(self.path)
        self.root = ET.fromstring(data)

    # ---------- instances ----------

    def instances(self) -> list[ET.Element]:
        el = self.root.find("instances")
        return list(el.findall("instance")) if el is not None else []

    def find_instance(self, ref: str) -> ET.Element | None:
        """ref = instance title (e.g. 'R1') or modelIndex string."""
        for inst in self.instances():
            title = inst.findtext("title")
            if title == ref or inst.get("modelIndex") == ref:
                return inst
        return None

    @staticmethod
    def instance_pos(inst: ET.Element) -> tuple[float, float]:
        views_el = inst.find("views")
        if views_el is not None:
            for view_el in views_el:
                geo = view_el.find("geometry")
                if geo is not None and geo.get("x") is not None:
                    return float(geo.get("x")), float(geo.get("y"))
        return 300.0, 300.0

    def next_model_index(self) -> str:
        vals = [int(i.get("modelIndex", "0")) for i in self.instances()]
        return str(max(vals + [1000]) + 1)

    def unique_title(self, label: str) -> str:
        base = re.sub(r"[^A-Za-z0-9]", "", label)[:12] or "Part"
        used = {i.findtext("title") or "" for i in self.instances()}
        n = 1
        while f"{base}{n}" in used:
            n += 1
        return f"{base}{n}"

    # ---------- mutation ----------

    def add_part_instance(self, module_id: str, title: str, views: list[str],
                          x: float, y: float, part_path: str = "",
                          props: dict[str, str] | None = None) -> ET.Element:
        inst = ET.SubElement(self._instances_el(), "instance")
        inst.set("moduleIdRef", module_id)
        inst.set("modelIndex", self.next_model_index())
        if part_path:
            inst.set("path", part_path)
        # schema order: property(s), title, views (as in Blink.fz)
        for k, v in (props or {}).items():
            p = ET.SubElement(inst, "property")
            p.set("name", k)
            p.set("value", v)
        ET.SubElement(inst, "title").text = title
        views_el = ET.SubElement(inst, "views")
        z = 1.5 + len(self.instances()) * 0.0001
        for v in views:
            tok = VIEW_TOKENS[v]
            view_el = ET.SubElement(views_el, tok["view"])
            view_el.set("layer", tok["part_layer"])
            geo = ET.SubElement(view_el, "geometry")
            geo.set("z", f"{z:.5f}")
            geo.set("x", f"{x:g}")
            geo.set("y", f"{y:g}")
        return inst

    def add_wire(self, a: tuple[str, str], b: tuple[str, str], view: str,
                 points: list[tuple[float, float]],
                 color: str | None = None) -> list[ET.Element]:
        """Wire part connector a = (modelIndex, connectorId) to b in one view.

        points are absolute sketch px: the start pin, any bend points, the end
        pin. Fritzing stores a bend point as a chain of wire instances joined
        end to end, so this returns one instance per segment. Each instance
        carries the view's wireFlags (64 breadboard, 128 schematic, 4 pcb):
        Fritzing uses the flag to decide which view a wire belongs to.
        """
        if len(points) < 2:
            raise ValueError("a wire needs at least two points")
        tok = VIEW_TOKENS[view]
        chain = []
        for _ in range(len(points) - 1):
            inst = ET.SubElement(self._instances_el(), "instance")
            inst.set("moduleIdRef", WIRE_MODULE_ID)
            inst.set("modelIndex", self.next_model_index())
            inst.set("path", "wire.fzp")
            ET.SubElement(inst, "title").text = self.unique_title("Wire")
            chain.append(inst)
        for k, inst in enumerate(chain):
            (x0, y0), (x1, y1) = points[k], points[k + 1]
            view_el = ET.SubElement(ET.SubElement(inst, "views"), tok["view"])
            view_el.set("layer", tok["wire_view"])
            geo = ET.SubElement(view_el, "geometry")
            for key, val in (("z", "3.50003"), ("x", f"{x0:g}"), ("y", f"{y0:g}"),
                             ("x1", "0"), ("y1", "0"), ("x2", f"{x1 - x0:g}"),
                             ("y2", f"{y1 - y0:g}"), ("wireFlags", tok["wire_flags"])):
                geo.set(key, val)
            extras = ET.SubElement(view_el, "wireExtras")
            for key, dv in tok["extras"].items():
                extras.set(key, color if (key == "color" and color) else dv)
            first = (a[0], a[1], tok["part_conn"]) if k == 0 else \
                (chain[k - 1].get("modelIndex"), "connector1", tok["wire_conn"])
            last = (b[0], b[1], tok["part_conn"]) if k == len(chain) - 1 else \
                (chain[k + 1].get("modelIndex"), "connector0", tok["wire_conn"])
            conns = ET.SubElement(view_el, "connectors")
            for my_conn, (other_idx, other_conn, layer) in (("connector0", first),
                                                            ("connector1", last)):
                c = ET.SubElement(conns, "connector")
                c.set("connectorId", my_conn)
                c.set("layer", tok["wire_conn"])
                cgeo = ET.SubElement(c, "geometry")
                cgeo.set("x", "0")
                cgeo.set("y", "0")
                connect = ET.SubElement(ET.SubElement(c, "connects"), "connect")
                connect.set("connectorId", other_conn)
                connect.set("modelIndex", other_idx)
                connect.set("layer", layer)
        return chain

    def remove_instance(self, ref: str) -> bool:
        inst = self.find_instance(ref)
        if inst is None:
            return False
        self._instances_el().remove(inst)
        return True

    def _instances_el(self) -> ET.Element:
        el = self.root.find("instances")
        if el is None:
            el = ET.SubElement(self.root, "instances")
        return el

    # ---------- saving ----------

    def fz_bytes(self) -> bytes:
        root = copy.deepcopy(self.root)
        ET.indent(root, space="    ")
        body = ET.tostring(root, encoding="unicode")
        if not body.lstrip().startswith("<?xml"):
            return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body).encode()
        return body.encode()

    def save(self, path: str | None = None) -> str:
        path = os.path.abspath(path or self.path)
        data = self.fz_bytes()
        if path.lower().endswith(FZZ_EXT):
            name = os.path.basename(path)
            fz = name[:-1]  # Demo.fzz -> Demo.fz (strip final "z")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(fz, data)
                for entry, blob in self.other_entries.items():
                    if entry.lower().endswith(FZ_EXT):
                        continue
                    z.writestr(entry, blob)
        else:
            with open(path, "wb") as f:
                f.write(data)
        self.path = path
        return path

