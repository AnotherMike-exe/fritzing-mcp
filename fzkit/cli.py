"""fz — CLI for reading, editing, creating Fritzing designs and parts.

All commands operate on .fzz bundles or plain .fz files.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

from . import model, partsdb

from .paths import PATHS

LAUNCHER = PATHS.launcher

PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(PKG_DIR, "templates", "sketch.fz")


# ---------------------------------------------------------------- parts


def cmd_parts(args) -> int:
    rows = partsdb.query(args.query, limit=args.limit)
    for p in rows:
        if args.verbose:
            print(f"{p.module_id}\n  title: {p.title}\n  family: {p.family}\n  source: {p.source}")
        else:
            print(p.as_row())
    print(f"-- {len(rows)} part(s)" + (f" matching {args.query!r}" if args.query else ""))
    return 0

def cmd_connectors(args) -> int:
    rows = partsdb.connectors(args.module_id)
    if not rows:
        print(f"error: module '{args.module_id}' not found or has no connectors "
              f"(run `fz parts --query ...` for ids)", file=sys.stderr)
        return 1
    print(json.dumps([
        {"id": cid, "name": name, "type": ctype} for cid, name, ctype in rows
    ], indent=2))
    return 0


# ---------------------------------------------------------------- sketch build


def cmd_new(args) -> int:
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if not out.lower().endswith((model.FZZ_EXT, model.FZ_EXT)):
        out += model.FZZ_EXT
    if os.path.exists(out) and not args.force:
        print(f"error: {out} exists (use --force)", file=sys.stderr)
        return 1
    sketch = model.FzSketch.from_template(out, TEMPLATE)
    sketch.save()
    print(f"created {out}")
    return 0


def _require_instance(sketch: model.FzSketch, ref: str) -> ET.Element:
    inst = sketch.find_instance(ref)
    if inst is None:
        raise SystemExit(f"error: no instance titled '{ref}' in {sketch.path} "
                         f"(use `fz show` to list refs)")
    return inst


def _lookup_part(module_id: str):
    for p in partsdb.query(module_id, limit=200):
        if p.module_id == module_id:
            return p
    print(f"error: module '{module_id}' not found (run `fz parts --query ...`)",
          file=sys.stderr)
    raise SystemExit(1)


def cmd_place(args) -> int:
    sketch = model.FzSketch(args.file)
    part = _lookup_part(args.module_id)
    views = model.resolve_view_token(args.view or "all")
    title = args.ref or sketch.unique_title(part.label or part.title)
    if sketch.find_instance(title) is not None:
        print(f"error: ref '{title}' already used", file=sys.stderr)
        return 1
    props = {}
    for kv in args.prop or []:
        k, v = kv.split("=", 1)
        props[k] = v
    inst = sketch.add_part_instance(part.module_id, title, views,
                                    args.x, args.y, part_path=part.path,
                                    props=props)
    sketch.save()
    print(f"placed {title} ({part.module_id}) modelIndex={inst.get('modelIndex')} at ({args.x:g},{args.y:g})")
    return 0


VIEW_NAMES = {"bb": "breadboard", "sc": "schematic", "pcb": "pcb"}


def _part_xml(sketch: model.FzSketch, module_id: str, view: str):
    """(fzp root, view SVG root) from local_parts, the library, or the bundle."""
    from . import geometry
    from .paths import PATHS
    path = partsdb.find_part_path(module_id)
    if path:
        full = path if os.path.isabs(path) else os.path.join(PATHS.parts_root, path)
        image = geometry.view_image(full, view)
        svg = geometry.svg_path(PATHS.parts_root, path, image) if image else None
        if svg and os.path.exists(svg):
            return ET.parse(full).getroot(), ET.parse(svg).getroot()
    blob = sketch.other_entries.get(f"part.{module_id}.fzp")
    if blob:
        fzp = ET.fromstring(blob)
        image = geometry.view_image(fzp, view)
        svg = sketch.other_entries.get("svg." + image.replace("/", ".", 1)) if image else None
        if svg:
            return fzp, ET.fromstring(svg)
    return None


def _pin_xy(sketch, cache, inst, conn_id, view):
    """Absolute px of a connector, or the part origin if the SVG has no such pin."""
    from . import geometry
    view_el = inst.find(f"views/{model.VIEW_TOKENS[view]['view']}")
    geo = view_el.find("geometry") if view_el is not None else None
    if geo is None or geo.get("x") is None:
        ox, oy = model.FzSketch.instance_pos(inst)
    else:
        ox, oy = float(geo.get("x")), float(geo.get("y"))
    module_id = inst.get("moduleIdRef")
    key = (module_id, view)
    if key not in cache:
        xml = _part_xml(sketch, module_id, VIEW_NAMES[view])
        cache[key] = geometry.pin_positions_xml(*xml, VIEW_NAMES[view]) if xml else {}
    if geo is not None and geo.find("transform") is not None:
        print(f"warning: {inst.findtext('title')} is rotated; wire ends use the unrotated pin",
              file=sys.stderr)
    pin = cache[key].get(conn_id)
    if pin is None:
        print(f"warning: no {VIEW_NAMES[view]} position for {inst.findtext('title')}.{conn_id}; "
              f"the wire ends at the part origin", file=sys.stderr)
        return ox, oy
    return ox + pin[0], oy + pin[1]


def cmd_wire(args) -> int:
    sketch = model.FzSketch(args.file)
    ref_a, conn_a = args.ref_a.split(".", 1)
    ref_b, conn_b = args.ref_b.split(".", 1)
    inst_a = _require_instance(sketch, ref_a)
    inst_b = _require_instance(sketch, ref_b)
    views = model.resolve_view_token(args.view or "bb")
    via = [tuple(float(n) for n in v.split(",")) for v in args.via or []]
    cache: dict = {}
    made = []
    for view in views:
        pts = [_pin_xy(sketch, cache, inst_a, conn_a, view),
               *(via if view == "bb" else []),
               _pin_xy(sketch, cache, inst_b, conn_b, view)]
        made += sketch.add_wire((inst_a.get("modelIndex"), conn_a),
                                (inst_b.get("modelIndex"), conn_b),
                                view, pts, color=args.color)
    sketch.save()
    print(f"wired {args.ref_a} <-> {args.ref_b} "
          f"({len(made)} segment(s): {', '.join(w.findtext('title') for w in made)}; "
          f"views {','.join(views)})")
    return 0


def cmd_move(args) -> int:
    sketch = model.FzSketch(args.file)
    inst = _require_instance(sketch, args.ref)
    views_el = inst.find("views")
    changed = 0
    if views_el is not None:
        for view_el in views_el:
            geo = view_el.find("geometry")
            if geo is None:
                continue
            if args.x is not None:
                geo.set("x", f"{args.x:g}")
            if args.y is not None:
                geo.set("y", f"{args.y:g}")
            changed += 1
    sketch.save()
    print(f"moved {args.ref} ({changed} view(s))")
    return 0


def cmd_prop(args) -> int:
    sketch = model.FzSketch(args.file)
    inst = _require_instance(sketch, args.ref)
    for kv in args.props:
        k, v = kv.split("=", 1)
        for el in inst.findall("property"):
            if el.get("name") == k:
                el.set("value", v)
                break
        else:
            p = ET.SubElement(inst, "property")
            p.set("name", k)
            p.set("value", v)
    _reorder_instance_children(inst)
    sketch.save()
    print(f"set {args.props} on {args.ref}")
    return 0


def _reorder_instance_children(inst: ET.Element) -> None:
    order = {"property": 0, "title": 1, "views": 2}
    children = sorted(list(inst), key=lambda e: order.get(e.tag, 3))
    for child in children:
        inst.remove(child)
    for child in children:
        inst.append(child)


def cmd_remove(args) -> int:
    sketch = model.FzSketch(args.file)
    if not sketch.remove_instance(args.ref):
        print(f"error: no instance '{args.ref}'", file=sys.stderr)
        return 1
    sketch.save()
    print(f"removed {args.ref}")
    return 0


# ---------------------------------------------------------------- inspect


def cmd_show(args) -> int:
    sketch = model.FzSketch(args.file)
    insts = sketch.instances()
    if args.json:
        out = {"file": sketch.path, "instances": []}
        for inst in insts:
            views = {}
            views_el = inst.find("views")
            if views_el is not None:
                for view_el in views_el:
                    geo = view_el.find("geometry")
                    views[view_el.tag] = dict(geo.attrib) if geo is not None else {}
            props = {p.get("name"): p.get("value") for p in inst.findall("property")}
            out["instances"].append({
                "ref": inst.findtext("title"),
                "moduleId": inst.get("moduleIdRef"),
                "modelIndex": inst.get("modelIndex"),
                "properties": props,
                "views": views,
            })
        print(json.dumps(out, indent=2))
        return 0
    print(f"file: {sketch.path}  ({len(insts)} instance(s))")
    for inst in insts:
        title = inst.findtext("title")
        pos = model.FzSketch.instance_pos(inst)
        print(f"  {title:<12} {inst.get('moduleIdRef'):<40} idx={inst.get('modelIndex'):<8} @({pos[0]:.0f},{pos[1]:.0f})")
        for p in inst.findall("property"):
            print(f"      {p.get('name')} = {p.get('value')}")
    return 0


# ---------------------------------------------------------------- check / render


def cmd_check(args) -> int:
    from . import check
    return check.check(args.file, strict=args.strict)


def cmd_render(args) -> int:
    from . import render
    return render.render(args.target, png=args.png, density=args.density,
                         view=args.view)


# ---------------------------------------------------------------- custom parts


def cmd_part(args) -> int:
    from . import partgen
    if args.part_cmd == "new":
        return partgen.part_new(args.spec, out=args.out, install=args.install, flat=args.flat)
    return partgen.validate(args.fzp)


# ---------------------------------------------------------------- open in app


def cmd_open(args) -> int:
    if not os.path.exists(LAUNCHER[-1]):
        print(f"error: launcher missing at {LAUNCHER[-1]}", file=sys.stderr)
        return 1
    subprocess.Popen(LAUNCHER + [os.path.abspath(f) for f in args.files])
    print(f"launching {' '.join(LAUNCHER)} {args.files}")
    return 0


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fz", description="Fritzing design toolkit for AI agents")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("parts", help="search the parts library")
    p.add_argument("--query", "-q", help="substring over id/title/label/family/tag")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--verbose", "-v", action="store_true")
    p.set_defaults(fn=cmd_parts)
    p = sub.add_parser("connectors", help="list connector ids/names/types for a part")
    p.add_argument("module_id")
    p.set_defaults(fn=cmd_connectors)

    p = sub.add_parser("new", help="create an empty sketch bundle")
    p.add_argument("out")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("place", help="add a part instance to a sketch")
    p.add_argument("file")
    p.add_argument("module_id")
    p.add_argument("--x", type=float, default=300.0)
    p.add_argument("--y", type=float, default=300.0)
    p.add_argument("--ref", help="instance title (default: label+counter)")
    p.add_argument("--view", help="bb|sc|pcb|all (default all)")
    p.add_argument("--prop", action="append", help="name=value, repeatable")
    p.set_defaults(fn=cmd_place)

    p = sub.add_parser("wire", help="wire two connectors: refA.connectorId refB.connectorId")
    p.add_argument("file")
    p.add_argument("ref_a")
    p.add_argument("ref_b")
    p.add_argument("--view", default="bb", help="bb|sc|pcb|all (default bb)")
    p.add_argument("--color")
    p.add_argument("--via", action="append", metavar="X,Y",
                   help="breadboard bend point in absolute px; repeat in path order")
    p.set_defaults(fn=cmd_wire)

    p = sub.add_parser("move", help="move an instance")
    p.add_argument("file")
    p.add_argument("ref")
    p.add_argument("--x", type=float)
    p.add_argument("--y", type=float)
    p.set_defaults(fn=cmd_move)

    p = sub.add_parser("prop", help="set instance properties name=value ...")
    p.add_argument("file")
    p.add_argument("ref")
    p.add_argument("props", nargs="+")
    p.set_defaults(fn=cmd_prop)

    p = sub.add_parser("remove", help="remove an instance")
    p.add_argument("file")
    p.add_argument("ref")
    p.set_defaults(fn=cmd_remove)

    p = sub.add_parser("show", help="list sketch instances")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("check", help="validate a sketch")
    p.add_argument("file")
    p.add_argument("--strict", action="store_true",
                   help="fail on route warnings (a wire that crosses a part)")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("render", help="headless-render sketch(es) to SVG (+PNG)")
    p.add_argument("target")
    p.add_argument("--png", action="store_true")
    p.add_argument("--density", type=int, default=150)
    p.add_argument("--view", default="all", help="bb|sc|pcb|all")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("part", help="custom part tools")
    ppart = p.add_subparsers(dest="part_cmd", required=True)
    pp = ppart.add_parser("new", help="generate a custom part from a JSON spec")
    pp.add_argument("spec")
    pp.add_argument("--out", default=os.path.join(PKG_DIR, "parts-out"))
    pp.add_argument("--install", action="store_true",
                    help="copy into local_parts so the app finds it")
    pp.add_argument("--flat", action="store_true",
                    help="write into --out itself, not --out/<moduleId>/")
    pp.set_defaults(fn=cmd_part)
    pv = ppart.add_parser("validate", help="validate a .fzp file")
    pv.add_argument("fzp")
    pv.set_defaults(fn=cmd_part)

    p = sub.add_parser("open", help="open sketch(es) in the Fritzing GUI")
    p.add_argument("files", nargs="+")
    p.set_defaults(fn=cmd_open)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 1
        return e.code if isinstance(e.code, int) else 0
    except ET.ParseError as e:
        print(f"error: invalid Fritzing XML: {e}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
