"""Sketch validation: unique indexes, known parts, views, wire endpoints."""

from __future__ import annotations

import os

from . import model, partsdb


def check(path: str) -> int:
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

    if problems:
        print(f"check FAILED: {len(problems)} problem(s) in {sketch.path}")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"check OK: {sketch.path} ({len(instances)} instances)")
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
