"""Part discovery: query the Fritzing parts database and the local_parts folder.

- parts.db (SQLite) holds the 2663-part core/contrib library.
- Custom parts installed under ~/.local/share/Fritzing/Fritzing/local_parts/
  are scanned from .fzp files by the app at startup (they are NOT in the db),
  so both sources are merged here.
"""

from __future__ import annotations

import glob
import os
import sqlite3
import xml.etree.ElementTree as ET

APP_ROOT = os.path.expanduser("~/code/fritzing/fritzing")
PARTS_DB = os.path.join(APP_ROOT, "parts", "parts.db")
LOCAL_PARTS_DIR = os.path.expanduser(
    "~/.local/share/Fritzing/Fritzing/local_parts")


class Part:
    __slots__ = ("module_id", "title", "label", "family", "path", "source")

    def __init__(self, module_id, title, label, family, path, source):
        self.module_id = module_id
        self.title = title
        self.label = label
        self.family = family
        self.path = path
        self.source = source

    def as_row(self) -> str:
        return f"{self.module_id}\t{self.title}\t[{self.family}]\t({self.source})"


def _connect() -> sqlite3.Connection:
    if not os.path.exists(PARTS_DB):
        raise FileNotFoundError(f"parts.db not found at {PARTS_DB} — is ~/code/fritzing intact?")
    return sqlite3.connect(f"file:{PARTS_DB}?mode=ro", uri=True)


def query(text: str | None = None, limit: int = 40) -> list[Part]:
    """Search parts by substring over moduleID/title/label/family/path, plus tags."""
    out: dict[str, Part] = {}
    con = _connect()
    try:
        sql = """SELECT moduleID, title, label, family, path FROM parts"""
        args: list = []
        if text:
            t = f"%{text.lower()}%"
            sql += """ WHERE lower(moduleID) LIKE ? OR lower(title) LIKE ?
                       OR lower(label) LIKE ? OR lower(family) LIKE ?
                       OR lower(path) LIKE ?
                       OR id IN (SELECT part_id FROM tags WHERE lower(tag) LIKE ?)"""
            args = [t] * 6
        sql += " ORDER BY title LIMIT ?"
        args.append(limit)
        for row in con.execute(sql, args):
            p = Part(row[0], row[1], row[2], row[3], row[4], "db")
            out[p.module_id] = p
    finally:
        con.close()
    for part in local_parts(text):
        out.setdefault(part.module_id, part)
    return list(out.values())[:limit]


def local_parts(text: str | None = None) -> list[Part]:
    """Scan local_parts/**/*.fzp for AI-installed custom parts."""
    results: list[Part] = []
    for fzp in glob.glob(os.path.join(LOCAL_PARTS_DIR, "**", "*.fzp"), recursive=True):
        try:
            root = ET.parse(fzp).getroot()
        except ET.ParseError:
            continue
        module_id = root.get("moduleId", "")
        title = root.findtext("title", "")
        label = root.findtext("label", "")
        family = ""
        props = root.find("properties")
        if props is not None:
            for p in props.findall("property"):
                if p.get("name") == "family":
                    family = p.get("value", "")
        if text and text.lower() not in (module_id + title + label + family).lower():
            continue
        results.append(Part(module_id, title, label, family, fzp, "local"))
    return results


def connectors(module_id: str) -> list[tuple[str, str, str]]:
    """(connectorId, name, type) for a part; db parts and local parts."""
    con = _connect()
    try:
        rows = con.execute(
            """SELECT c.connectorid, c.name, c.type FROM connectors c
               JOIN parts p ON c.part_id = p.id
               WHERE p.moduleID = ? ORDER BY c.connectorid""",
            (module_id,)).fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        con.close()
    if rows:
        types = {0: "male", 1: "female", 2: "pad"}
        return [(r[0], r[1], types.get(r[2], str(r[2]))) for r in rows]
    # fall back to parsing local fzp files
    for part in local_parts():
        if part.module_id == module_id and os.path.exists(part.path):
            root = ET.parse(part.path).getroot()
            out = []
            for c in root.find("connectors").findall("connector"):
                out.append((c.get("id"), c.get("name", ""), c.get("type", "male")))
            return out
    return []


def find_part_path(module_id: str) -> str | None:
    """parts.db path (relative to parts root) or absolute local path."""
    con = _connect()
    try:
        row = con.execute("SELECT path FROM parts WHERE moduleID = ?",
                          (module_id,)).fetchone()
    finally:
        con.close()
    if row and row[0]:
        return row[0]
    for part in local_parts():
        if part.module_id == module_id:
            return part.path
    return None
