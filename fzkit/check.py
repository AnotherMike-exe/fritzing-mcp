"""Sketch validation: unique indexes, known parts, views, wire endpoints.

It also warns about breadboard wires that cross a part. A wire may enter a
part only to reach its own pin, on the shortest way in from the part edge.
"""

from __future__ import annotations

import os

from . import model, partsdb


def check(path: str, strict: bool = False) -> int:
    sketch = model.FzSketch(path)
    problems: list[str] = []
    known_modules: dict[str, dict[str, list[str]]] = {}
    instances = sketch.instances()

    if not instances:
        problems.append("sketch has no instances")

    seen_idx: dict[str, str] = {}
    titles: list[str] = []
    for inst in instances:
        ref = inst.findtext("title") or "(untitled)"
        idx = inst.get("modelIndex")
        titles.append(ref)
        if not idx:
            problems.append(f"{ref}: missing modelIndex")
        elif idx in seen_idx:
            problems.append(f"{ref}: duplicate modelIndex {idx} (also on {seen_idx[idx]})")
        else:
            seen_idx[idx] = ref

        views_el = inst.find("views")
        if views_el is None or len(list(views_el)) == 0:
            problems.append(f"{ref}: instance has no views (app will skip it)")

        module_id = inst.get("moduleIdRef")
        if module_id == model.WIRE_MODULE_ID:
            endpoints = _wire_endpoints(inst)
            for other_idx, other_conn in endpoints:
                target = instances_by_idx(instances).get(other_idx)
                if target is None:
                    problems.append(f"{ref}: wire connects to missing modelIndex {other_idx}")
                    continue
                tref = target.findtext("title") or target.get("modelIndex")
                target_module = target.get("moduleIdRef")
                if target_module == model.WIRE_MODULE_ID:
                    continue  # wire-to-wire: connector ids not pre-checkable here
                conns = _connectors_of(known_modules, target_module)
                if conns is not None and other_conn not in conns:
                    problems.append(
                        f"{ref}: wire endpoint {tref}.{other_conn} does not exist "
                        f"(valid: {', '.join(sorted(conns))})")
            continue

        if partsdb.find_part_path(module_id) is None:
            problems.append(f"{ref}: module '{module_id}' not found in parts.db or local_parts")

    for ref, n in ((t, titles.count(t)) for t in set(titles)):
        if ref not in ("(untitled)",) and n > 1:
            problems.append(f"duplicate instance title '{ref}' x{n} (refs must be unique)")

    warnings = route_warnings(sketch)
    if strict:
        problems += warnings
        warnings = []

    if problems:
        print(f"check FAILED: {len(problems)} problem(s) in {sketch.path}")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"check OK: {sketch.path} ({len(instances)} instances)")
    for w in warnings:
        print(f"  warning: {w}")
    return 0


def instances_by_idx(instances):
    return {i.get("modelIndex"): i for i in instances}


def _connectors_of(cache: dict, module_id: str):
    if module_id not in cache:
        try:
            rows = partsdb.connectors(module_id)
            cache[module_id] = {r[0]: r for r in rows} if rows else None
        except Exception:
            cache[module_id] = None
    data = cache[module_id]
    return set(data.keys()) if isinstance(data, dict) else None


def _wire_endpoints(wire_inst):
    """All (other_modelIndex, other_connectorId) targets in every view."""
    out = []
    views_el = wire_inst.find("views")
    if views_el is None:
        return out
    for view_el in views_el:
        conns = view_el.find("connectors")
        if conns is None:
            continue
        for c in conns.findall("connector"):
            for connect in c.findall("connects/connect"):
                out.append((connect.get("modelIndex"), connect.get("connectorId")))
    return out


ROUTE_TOLERANCE = 4.0   # px a wire may run inside a part beyond its pin approach
APPROACH_FACTOR = 1.5   # a pin approach may bend: allow 1.5 x the pin-to-edge distance
PIN_CLEARANCE = 3.0     # px a wire must keep from the centre of a pin it does not use


def _wire_runs(instances, by_idx):
    """Breadboard wires grouped into runs: one run = the segments from pin to pin."""
    segs = {}
    for wire in instances:
        if wire.get("moduleIdRef") != model.WIRE_MODULE_ID:
            continue
        view = wire.find("views/breadboardView")
        geo = view.find("geometry") if view is not None else None
        if geo is None or geo.get("wireFlags") != model.VIEW_TOKENS["bb"]["wire_flags"]:
            continue
        x, y = float(geo.get("x", 0)), float(geo.get("y", 0))
        p = (x + float(geo.get("x1", 0)), y + float(geo.get("y1", 0)))
        q = (x + float(geo.get("x2", 0)), y + float(geo.get("y2", 0)))
        links, ends = [], []
        for connect in view.iter("connect"):
            target = by_idx.get(connect.get("modelIndex"))
            if target is None:
                continue
            if target.get("moduleIdRef") == model.WIRE_MODULE_ID:
                links.append(connect.get("modelIndex"))
            else:
                ends.append((target, connect.get("connectorId")))
        segs[wire.get("modelIndex")] = (wire, (p, q), links, ends)
    runs, seen = [], set()
    for idx in segs:
        if idx in seen:
            continue
        stack, run = [idx], []
        while stack:
            cur = stack.pop()
            if cur in seen or cur not in segs:
                continue
            seen.add(cur)
            run.append(segs[cur])
            stack.extend(segs[cur][2])
        runs.append(run)
    return runs


def route_warnings(sketch: model.FzSketch) -> list[str]:
    """Breadboard wires that cross the body of a part, or pass over a pin."""
    from . import geometry
    from .cli import _part_xml, _pin_xy
    instances = sketch.instances()
    by_idx = instances_by_idx(instances)
    parts = []  # (modelIndex, ref, box, {connectorId: absolute px})
    for inst in instances:
        module_id = inst.get("moduleIdRef") or ""
        if module_id in (model.WIRE_MODULE_ID, "NoteModuleID") or "breadboard" in module_id.lower():
            continue  # a wire on a breadboard is meant to sit on it
        geo = inst.find("views/breadboardView/geometry")
        xml = _part_xml(sketch, module_id, "breadboard")
        size = geometry.svg_size(xml[1]) if xml else None
        if geo is None or geo.get("x") is None or size is None:
            continue
        x, y = float(geo.get("x")), float(geo.get("y"))
        pins = {c: (x + px, y + py) for c, (px, py)
                in geometry.pin_positions_xml(*xml, "breadboard").items()}
        parts.append((inst.get("modelIndex"), inst.findtext("title") or module_id,
                      (x, y, x + size[0], y + size[1]), pins))

    out: list[str] = []
    cache: dict = {}
    for run in _wire_runs(instances, by_idx):
        name = f"{run[0][0].findtext('title')} ({run[0][0].find('views/breadboardView/wireExtras').get('color')})"
        ends = [(t.get("modelIndex"), c, _pin_xy(sketch, cache, t, c, "bb"))
                for _, _, _, e in run for t, c in e]
        used = {(i, c) for i, c, _ in ends}
        for idx, ref, box, pins in parts:
            inside = sum(geometry.length_inside(p, q, box) for _, (p, q), _, _ in run)
            mine = [xy for i, _, xy in ends if i == idx]
            allowed = sum(max(0.0, geometry.edge_distance(xy, box)) for xy in mine)
            leaves = any(geometry.edge_distance(pt, box) <= 0
                         for _, seg, _, _ in run for pt in seg)
            if inside > allowed * APPROACH_FACTOR + ROUTE_TOLERANCE or (inside and not leaves):
                out.append(f"{name} crosses {ref} for {inside:.0f} px: "
                           f"route it around the part, through clear space")
            for conn, xy in pins.items():
                if (idx, conn) in used:
                    continue
                if any(geometry.length_inside(p, q, (xy[0] - PIN_CLEARANCE, xy[1] - PIN_CLEARANCE,
                                                     xy[0] + PIN_CLEARANCE, xy[1] + PIN_CLEARANCE),
                                              inset=0) for _, (p, q), _, _ in run):
                    out.append(f"{name} passes over {ref}.{conn}, a pin it does not connect to")
    return out
