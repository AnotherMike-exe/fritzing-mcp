import os
import tempfile
import unittest

from fzkit import geometry

FZP = """<?xml version="1.0" encoding="UTF-8"?>
<module moduleId="DemoModuleID">
 <views><breadboardView><layers image="breadboard/demo.svg"><layer layerId="breadboard"/></layers></breadboardView></views>
 <connectors>
  <connector id="connector0" name="A"><views><breadboardView><p layer="breadboard" svgId="connector0pin"/></breadboardView></views></connector>
  <connector id="connector1" name="B"><views><breadboardView><p layer="breadboard" svgId="connector1pin"/></breadboardView></views></connector>
  <connector id="connector2" name="C"><views><breadboardView><p layer="breadboard" svgId="c2"/></breadboardView></views></connector>
 </connectors>
</module>
"""

# 1 in x 0.5 in drawn in a 1000 x 500 viewBox: 1 user unit = 0.09 px at 90 DPI
SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="1in" height="0.5in" viewBox="0 0 1000 500">
 <g id="breadboard">
  <circle id="connector0pin" cx="100" cy="200" r="20"/>
  <g transform="translate(500,0)">
   <rect id="connector1pin" x="0" y="100" width="100" height="200"/>
  </g>
  <g transform="matrix(1 0 0 1 10 20) scale(2)">
   <circle id="c2" cx="50" cy="50" r="5"/>
  </g>
 </g>
</svg>
"""


class PinPositionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, "breadboard"))
        self.fzp = os.path.join(self.tmp.name, "part.fzp")
        with open(self.fzp, "w") as f:
            f.write(FZP)
        with open(os.path.join(self.tmp.name, "breadboard", "demo.svg"), "w") as f:
            f.write(SVG)

    def tearDown(self):
        self.tmp.cleanup()

    def test_positions_in_90_dpi_px(self):
        pos = geometry.pin_positions(self.fzp, os.path.join(self.tmp.name, "breadboard", "demo.svg"))
        self.assertAlmostEqual(pos["connector0"][0], 9.0)
        self.assertAlmostEqual(pos["connector0"][1], 18.0)
        # rect centre (550, 200) after translate(500, 0)
        self.assertAlmostEqual(pos["connector1"][0], 49.5)
        self.assertAlmostEqual(pos["connector1"][1], 18.0)
        # circle (50, 50) -> scale 2 -> (100, 100) -> translate (110, 120)
        self.assertAlmostEqual(pos["connector2"][0], 9.9)
        self.assertAlmostEqual(pos["connector2"][1], 10.8)

    def test_svg_path_for_core_and_local_parts(self):
        self.assertEqual(
            geometry.svg_path("/parts", "core/x.fzp", "breadboard/x.svg"),
            "/parts/svg/core/breadboard/x.svg")
        self.assertEqual(
            geometry.svg_path("/parts", "/lp/Demo/part.fzp", "breadboard/d.svg"),
            "/lp/Demo/breadboard/d.svg")


if __name__ == "__main__":
    unittest.main()
