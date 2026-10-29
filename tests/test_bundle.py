import os
import tempfile
import unittest
import zipfile

from fzkit import model, partsdb

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "sketch.fz")
FZP = """<?xml version="1.0" encoding="UTF-8"?>
<module moduleId="ai-demo-1ModuleID"><title>Demo</title>
 <views>
  <iconView><layers image="icon/demo.svg"/></iconView>
  <breadboardView><layers image="breadboard/demo.svg"/></breadboardView>
  <schematicView><layers image="schematic/demo.svg"/></schematicView>
  <pcbView><layers image="pcb/demo.svg"/></pcbView>
 </views>
</module>
"""


class BundleTest(unittest.TestCase):
    def test_local_parts_are_bundled_on_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            lp = os.path.join(tmp, "local_parts")
            part = os.path.join(lp, "ai-demo-1ModuleID")
            for view in ("icon", "breadboard", "schematic", "pcb"):
                os.makedirs(os.path.join(part, view))
                with open(os.path.join(part, view, "demo.svg"), "w") as f:
                    f.write(f"<svg id='{view}'/>")
            with open(os.path.join(part, "part.fzp"), "w") as f:
                f.write(FZP)
            saved = partsdb.LOCAL_PARTS_DIR
            partsdb.LOCAL_PARTS_DIR = lp
            try:
                s = model.FzSketch.from_template(os.path.join(tmp, "T.fzz"), TEMPLATE)
                s.add_part_instance("ai-demo-1ModuleID", "U1", ["bb"], 0, 0)
                s.add_part_instance("ResistorModuleID", "R1", ["bb"], 0, 0)
                s.save()
            finally:
                partsdb.LOCAL_PARTS_DIR = saved
            names = set(zipfile.ZipFile(os.path.join(tmp, "T.fzz")).namelist())
        self.assertIn("part.ai-demo-1ModuleID.fzp", names)
        for view in ("icon", "breadboard", "schematic", "pcb"):
            self.assertIn(f"svg.{view}.demo.svg", names)
        self.assertFalse(any("Resistor" in n for n in names), names)


if __name__ == "__main__":
    unittest.main()
