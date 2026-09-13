"""Custom part generator: JSON spec -> .fzp + 4 view SVGs, installable to local_parts.

Layout follows the highest-priority SVG search path verified in
src/items/partfactory.cpp getSvgFilename():
  <local_parts>/{moduleID}/part.fzp
  <local_parts>/{moduleID}/{breadboard,schematic,pcb,icon}/<name>.svg

Pin SVG ids: breadboard/schematic use id="connector{N}pin" (schematic adds
terminalId circles id="connector{N}terminal"); pcb pads use id="connector{N}pad".
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

LOCAL_PARTS_DIR = os.path.expanduser(
    "~/.local/share/Fritzing/Fritzing/local_parts")
FZP_CHECKER = os.path.expanduser("~/code/fritzing/fritzing/parts/fzp_checker.py")

VIEWS = ["breadboard", "schematic", "pcb", "icon"]
REQUIRED_SPEC_KEYS = ("title", "pins", "geometry")


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:32] or "part"


def _module_id(title: str, pins: list) -> str:
    digest = hashlib.sha1(
        json.dumps({"t": title, "p": [p.get("name") for p in pins]},
                   sort_keys=True).encode()).hexdigest()[:8]
    return f"ai-{_slug(title)}-{digest}ModuleID"


def _svg(w: float, h: float, body: str) -> str:
    """Fritzing SVGs: viewBox in px at 90 DPI, width/height in physical units."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w / 90:g}in" '
            f'height="{h / 90:g}in" viewBox="0 0 {w:g} {h:g}">\n{body}\n</svg>\n')


def _breadboard_svg(geo: dict, pins: list, group_id: str = "breadboard") -> str:
    w, h, color = geo.get("w", 180), geo.get("h", 100), geo.get("color", "#1a6fc4")
    body = [f'  <g id="{group_id}">',
            f'   <rect x="0" y="0" width="{w:g}" height="{h:g}" rx="8" fill="{color}" stroke="#0d3c66" stroke-width="2"/>']
    for i, (px, py) in enumerate(geo.get("pins", [])):
        body.append(f'   <line x1="{px:g}" y1="{py:g}" x2="{px:g}" y2="{h:g}" stroke="#c9a227" stroke-width="2.5"/>')
        body.append(f'   <circle id="connector{i}pin" cx="{px:g}" cy="{py:g}" r="5" fill="#c9a227"/>')
    body.append('  </g>')
    return _svg(w, h, "\n".join(body))


def _schematic_svg(geo: dict, pins: list) -> str:
    w, h = geo.get("w", 120), geo.get("h", 80)
    body = ['  <g id="schematic">',
            f'   <rect x="0" y="0" width="{w:g}" height="{h:g}" fill="none" stroke="#000000" stroke-width="2"/>']
    for i, (px, py) in enumerate(geo.get("pins", [])):
        attach_y = 0 if py <= h / 2 else h
        body.append(f'   <line x1="{px:g}" y1="{attach_y:g}" x2="{px:g}" y2="{py:g}" stroke="#000000" stroke-width="2"/>')
        body.append(f'   <circle id="connector{i}pin" cx="{px:g}" cy="{py:g}" r="3" fill="none" stroke="#000000" stroke-width="1.5"/>')
        body.append(f'   <circle id="connector{i}terminal" cx="{px:g}" cy="{py:g}" r="1.2" fill="#000000"/>')
        label = pins[i].get("name", f"pin{i}") if i < len(pins) else f"pin{i}"
        ty = py + 12 if py <= h / 2 else py - 6
        body.append(f'   <text x="{px + 6:g}" y="{ty:g}" font-family="Noto Sans" font-size="10">{label}</text>')
    body.append('  </g>')
    return _svg(w, h, "\n".join(body))


def _pcb_svg(geo: dict, pins: list) -> str:
    w, h = geo.get("w", 100), geo.get("h", 70)
    pad_d, hole_d = geo.get("padD", 12), geo.get("holeD", 4)
    copper, silk, outline = [], [], []
    for i, (px, py) in enumerate(geo.get("pins", [])):
        # copper pads must use the standard copper color #f7bd13
        copper.append(f'   <circle id="connector{i}pad" cx="{px:g}" cy="{py:g}" r="{pad_d / 2:g}" fill="#f7bd13"/>')
        # drill holes: white circles, but keep them out of the copper group
        silk.append(f'   <circle cx="{px:g}" cy="{py:g}" r="{hole_d / 2:g}" fill="#ffffff"/>')
    outline.append(f'   <rect x="1" y="1" width="{w - 2:g}" height="{h - 2:g}" fill="none" stroke="#ffffff" stroke-width="2"/>')
    body = ('  <g id="silkscreen">\n' + "\n".join(silk + outline) + '\n  </g>\n'
            '  <g id="outline">\n' + f'   <rect x="0" y="0" width="{w:g}" height="{h:g}" fill="none" stroke="#000000" stroke-width="1"/>' + '\n  </g>\n'
            '  <g id="copper0">\n' + "\n".join(copper) + '\n  </g>')
    return _svg(w, h, body)


def _fzp(module_id: str, spec: dict, svg_name: str) -> str:
    title = spec["title"]
    label = spec.get("label", title[:8])
    pins = spec["pins"]
    family = spec.get("family", "custom")
    bb_geo = spec["geometry"]["breadboard"]
    sc_geo = spec["geometry"]["schematic"]
    pcb_geo = spec["geometry"]["pcb"]

    conn_xml = []
    for i, pin in enumerate(pins):
        conn_xml.append(f'''  <connector id="connector{i}" name="{pin.get("name", f"pin{i}")}" type="{pin.get("type", "male")}">
   <description>{pin.get("description", pin.get("name", f"pin{i}"))}</description>
   <views>
    <breadboardView>
     <p layer="breadboard" svgId="connector{i}pin"/>
    </breadboardView>
    <schematicView>
     <p layer="schematic" svgId="connector{i}pin" terminalId="connector{i}terminal"/>
    </schematicView>
    <pcbView>
     <p layer="copper0" svgId="connector{i}pad"/>
    </pcbView>
   </views>
  </connector>''')

    props_xml = [f'  <property name="family">{family}</property>']
    for k, v in spec.get("properties", {}).items():
        props_xml.append(f'  <property name="{k}">{v}</property>')

    tags_xml = "\n".join(f'  <tag>{t}</tag>' for t in spec.get("tags", [family]))

    from datetime import date as _date
    svg_name = svg_name  # noqa
    date_str = _date.today().isoformat()
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<module fritzingVersion="1.0.8" moduleId="{module_id}">
 <version>1</version>
 <author>AI (fzkit)</author>
 <date>2026-09-06</date>
 <title>{title}</title>
 <label>{label}</label>
 <date>{date_str}</date>
 <tags>
{tags_xml}
 </tags>
 <properties>
{chr(10).join(props_xml)}
 </properties>
 <description>{spec.get("description", title)}</description>
 <views>
  <iconView>
   <layers image="icon/{svg_name}"/>
  </iconView>
  <breadboardView>
   <layers image="breadboard/{svg_name}">
    <layer layerId="breadboard"/>
   </layers>
  </breadboardView>
  <schematicView>
   <layers image="schematic/{svg_name}">
    <layer layerId="schematic"/>
   </layers>
  </schematicView>
  <pcbView>
   <layers image="pcb/{svg_name}">
    <layer layerId="copper0"/>
    <layer layerId="silkscreen"/>
    <layer layerId="outline"/>
   </layers>
  </pcbView>
 </views>
 <connectors>
{chr(10).join(conn_xml)}
 </connectors>
</module>
'''


def part_new(spec_path: str, out: str, install: bool = False) -> int:
    with open(spec_path) as f:
        spec = json.load(f)
    missing = [k for k in REQUIRED_SPEC_KEYS if k not in spec]
    if missing:
        print(f"error: spec missing keys: {missing}", file=sys.stderr)
        return 1
    pins = spec["pins"]
    if not pins:
        print("error: spec needs at least one pin", file=sys.stderr)
        return 1
    geo = spec["geometry"]
    for view in ("breadboard", "schematic", "pcb"):
        if view not in geo or "pins" not in geo[view]:
            print(f"error: geometry.{view}.pins missing", file=sys.stderr)
            return 1
        if len(geo[view]["pins"]) != len(pins):
            print(f"error: geometry.{view}.pins must list {len(pins)} coords "
                  f"(one per pin, same order as 'pins')", file=sys.stderr)
            return 1

    module_id = _module_id(spec["title"], pins)
    svg_name = f"{_slug(spec['title'])}.svg"
    part_dir = os.path.join(os.path.abspath(out), module_id)
    os.makedirs(part_dir, exist_ok=True)
    for view in VIEWS:
        os.makedirs(os.path.join(part_dir, view), exist_ok=True)

    # Generate per-view SVGs; the icon view reuses the breadboard image.
    files = {
        "breadboard": _breadboard_svg(geo["breadboard"], pins),
        "schematic": _schematic_svg(geo["schematic"], pins),
        "pcb": _pcb_svg(geo["pcb"], pins),
    }
    files["icon"] = _breadboard_svg(geo["breadboard"], pins, group_id="icon")
    for view, content in files.items():
        with open(os.path.join(part_dir, view, svg_name), "w") as f:
            f.write(content)
    fzp_path = os.path.join(part_dir, "part.fzp")
    with open(fzp_path, "w") as f:
        f.write(_fzp(module_id, spec, svg_name))
    # dot-style copies next to the fzp (extracted-fzpz convention; used by
    # the parts-repo fzp_checker and as an app fallback search path)
    for view in VIEWS:
        dot_name = "svg." + view + "." + svg_name
        with open(os.path.join(part_dir, dot_name), "w") as f:
            f.write(files[view])

    print(f"part {module_id}")
    print(f"dir  {part_dir}")
    print(f"fzp  {fzp_path}")
    for view in VIEWS:
        print(f"svg  {os.path.join(part_dir, view, svg_name)}")
    print("pins: " + ", ".join(
        f"{p.get('name', f'pin{i}')}=connector{i}" for i, p in enumerate(pins)))

    rc = validate(fzp_path)
    if rc != 0:
        print("warning: validation reported issues (see above)", file=sys.stderr)

    if install:
        dest = os.path.join(LOCAL_PARTS_DIR, module_id)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(part_dir, dest)
        # also mirror SVGs to <local_parts>/svg/core/<view>/ — the parts-root
        # convention used by fzp_checker and the app's fallback SVG search
        svg_root = os.path.join(LOCAL_PARTS_DIR, "svg", "core")
        for view in ("breadboard", "schematic", "pcb", "icon"):
            os.makedirs(os.path.join(svg_root, view), exist_ok=True)
            shutil.copy2(os.path.join(part_dir, view, svg_name),
                         os.path.join(svg_root, view, svg_name))
        print(f"installed {dest}")
        print(f"svg mirror {svg_root}/<view>/{svg_name}")
        print("note: restart Fritzing to pick up the new part")
    return rc


def validate(fzp_path: str) -> int:
    rc = 0
    if os.path.exists(FZP_CHECKER):
        proc = subprocess.run(["python3", FZP_CHECKER, fzp_path],
                              capture_output=True, text=True, timeout=60)
        out = (proc.stdout + proc.stderr).strip()
        if out:
            print(out)
        rc = proc.returncode
    else:
        print(f"note: fzp_checker not found at {FZP_CHECKER}; structural checks only")
    # structural sanity: 4 views present, all referenced SVGs exist
    root = ET.parse(fzp_path).getroot()
    views = {v.tag for v in root.find("views")} if root.find("views") is not None else set()
    expected = {"iconView", "breadboardView", "schematicView", "pcbView"}
    if views != expected:
        print(f"error: views {sorted(expected - views)} missing from {fzp_path}",
              file=sys.stderr)
        rc = 1
    base = os.path.dirname(fzp_path)
    for v in root.find("views"):
        layers = v.find("layers")
        if layers is None:
            continue
        image = layers.get("image", "")
        svg_path = os.path.join(base, image)
        if not os.path.exists(svg_path):
            print(f"error: referenced SVG missing: {svg_path}", file=sys.stderr)
            rc = 1
    print("check " + ("OK" if rc == 0 else "FAILED"))
    return rc
