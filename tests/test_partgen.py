import os
import sys
import tempfile
import unittest
from unittest import mock

from fzkit import partgen


class ValidateTest(unittest.TestCase):
    def test_checker_runs_in_this_python(self):
        calls = []

        def fake_run(argv, **kw):
            calls.append(argv)
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            checker = os.path.join(tmp, "fzp_checker.py")
            open(checker, "w").close()
            fzp = os.path.join(tmp, "part.fzp")
            with open(fzp, "w") as f:
                f.write("<module><views/></module>")
            with mock.patch.object(partgen, "FZP_CHECKER", checker), \
                    mock.patch.object(partgen.subprocess, "run", fake_run):
                partgen.validate(fzp)
        self.assertEqual(calls[0][0], sys.executable)


if __name__ == "__main__":
    unittest.main()


SPEC = {
    "title": "Demo Module", "author": "Plum Solutions",
    "pins": [{"name": "VCC"}, {"name": "OUT"}],
    "geometry": {
        "breadboard": {"w": 40, "h": 30, "color": "#123456", "pins": [[9, 9], [9, 18]],
                       "pin_r": 3, "legs": False, "stroke": "#000000",
                       "labels": [{"side": "right"}, {"text": "SIG", "side": "up"}],
                       "extra": ['<rect id="mark" x="1" y="1" width="2" height="2"/>']},
        "schematic": {"pins": [[0, 10], [0, 20]]},
        "pcb": {"pins": [[5, 5], [5, 14]]},
    },
}


class StyleTest(unittest.TestCase):
    def build(self, spec, flat=True):
        import json
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "spec.json")
        with open(path, "w") as f:
            json.dump(spec, f)
        with mock.patch.object(partgen, "validate", lambda p: 0):
            partgen.part_new(path, out=os.path.join(tmp.name, "Out"), flat=flat)
        return os.path.join(tmp.name, "Out")

    def read(self, d, name):
        with open(os.path.join(d, name)) as f:
            return f.read()

    def test_flat_out_writes_into_the_folder(self):
        d = self.build(SPEC)
        self.assertTrue(os.path.exists(os.path.join(d, "part.fzp")))
        self.assertTrue(os.path.exists(os.path.join(d, "breadboard", "demo-module.svg")))

    def test_breadboard_style_keys(self):
        svg = self.read(self.build(SPEC), "breadboard/demo-module.svg")
        self.assertIn('r="3"', svg)
        self.assertNotIn("<line", svg)
        self.assertIn('stroke="#000000"', svg)
        self.assertIn('fill="#123456"', svg)
        self.assertIn(">VCC</text>", svg)
        self.assertIn(">SIG</text>", svg)
        self.assertIn('font-family="Noto Sans"', svg)
        self.assertIn('id="mark"', svg)
        self.assertLess(svg.index('id="mark"'), svg.index('id="connector0pin"'))

    def test_defaults_unchanged(self):
        spec = {**SPEC, "geometry": {**SPEC["geometry"],
                                     "breadboard": {"w": 40, "h": 30, "pins": [[9, 9], [9, 18]]}}}
        svg = self.read(self.build(spec), "breadboard/demo-module.svg")
        self.assertIn('r="5"', svg)
        self.assertIn("<line", svg)
        self.assertNotIn("<text", svg)

    def test_author_and_single_date(self):
        fzp = self.read(self.build(SPEC), "part.fzp")
        self.assertIn("<author>Plum Solutions</author>", fzp)
        self.assertEqual(fzp.count("<date>"), 1)
