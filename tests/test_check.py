import os
import tempfile
import unittest

from fzkit import check, model, partsdb

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "sketch.fz")
FZP = """<?xml version="1.0" encoding="UTF-8"?>
<module moduleId="ai-route-1ModuleID"><title>Route</title>
 <views><breadboardView><layers image="breadboard/route.svg"/></breadboardView></views>
 <connectors>
  <connector id="connector0" name="A"><views><breadboardView><p layer="breadboard" svgId="connector0pin"/></breadboardView></views></connector>
  <connector id="connector1" name="B"><views><breadboardView><p layer="breadboard" svgId="connector1pin"/></breadboardView></views></connector>
 </connectors>
</module>
"""
# 100 x 50 px board, pin A near the left edge, pin B near the right edge
SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="100px" height="50px" viewBox="0 0 100 50">
 <rect width="100" height="50"/>
 <circle id="connector0pin" cx="5" cy="25" r="2"/>
 <circle id="connector1pin" cx="95" cy="25" r="2"/>
</svg>
"""


class RouteWarningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        part = os.path.join(self.tmp.name, "local_parts", "ai-route-1ModuleID")
        os.makedirs(os.path.join(part, "breadboard"))
        with open(os.path.join(part, "part.fzp"), "w") as f:
            f.write(FZP)
        with open(os.path.join(part, "breadboard", "route.svg"), "w") as f:
            f.write(SVG)
        self.saved = partsdb.LOCAL_PARTS_DIR
        partsdb.LOCAL_PARTS_DIR = os.path.join(self.tmp.name, "local_parts")
        self.sketch = model.FzSketch.from_template(os.path.join(self.tmp.name, "T.fzz"), TEMPLATE)
        self.u1 = self.sketch.add_part_instance("ai-route-1ModuleID", "U1", ["bb"], 0, 0)
        self.u2 = self.sketch.add_part_instance("ai-route-1ModuleID", "U2", ["bb"], 200, 0)

    def tearDown(self):
        partsdb.LOCAL_PARTS_DIR = self.saved
        self.tmp.cleanup()

    def wire(self, a, b, points):
        self.sketch.add_wire((a[0].get("modelIndex"), a[1]), (b[0].get("modelIndex"), b[1]),
                             "bb", points)

    def test_wire_across_a_part_warns(self):
        self.wire((self.u1, "connector0"), (self.u2, "connector0"), [(5, 25), (205, 25)])
        warnings = check.route_warnings(self.sketch)
        self.assertTrue(any("crosses U1" in w for w in warnings), warnings)
        self.assertTrue(any("passes over U1.connector1" in w for w in warnings), warnings)

    def test_wire_around_a_part_is_clean(self):
        self.wire((self.u1, "connector0"), (self.u2, "connector0"),
                  [(5, 25), (-10, 25), (-10, 70), (150, 70), (150, 25), (205, 25)])
        self.assertEqual(check.route_warnings(self.sketch), [])

    def test_jumper_inside_one_part_warns(self):
        self.wire((self.u1, "connector0"), (self.u1, "connector1"), [(5, 25), (5, 30), (95, 30), (95, 25)])
        self.assertTrue(any("crosses U1" in w for w in check.route_warnings(self.sketch)))


if __name__ == "__main__":
    unittest.main()
