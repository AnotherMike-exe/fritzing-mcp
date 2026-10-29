import os
import tempfile
import unittest

from fzkit import model

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "sketch.fz")


def new_sketch(tmp: str) -> model.FzSketch:
    return model.FzSketch.from_template(os.path.join(tmp, "T.fzz"), TEMPLATE)


def wire(sketch, a, b, view="bb", points=((0, 0), (10, 0)), color=None):
    return sketch.add_wire((a.get("modelIndex"), "connector0"),
                           (b.get("modelIndex"), "connector1"),
                           view, list(points), color=color)


def flags(inst):
    return inst.find("views/*/geometry").get("wireFlags")


def ends(inst):
    out = {}
    for c in inst.findall("views/*/connectors/connector"):
        t = c.find("connects/connect")
        out[c.get("connectorId")] = (t.get("modelIndex"), t.get("connectorId"), t.get("layer"))
    return out


class WireTitleTest(unittest.TestCase):
    def test_titles_stay_unique_after_a_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = new_sketch(tmp)
            a = s.add_part_instance("A", "A1", ["bb"], 0, 0)
            b = s.add_part_instance("B", "B1", ["bb"], 100, 0)
            w1 = wire(s, a, b)[0]
            wire(s, a, b)
            s.remove_instance(w1.findtext("title"))
            wire(s, a, b)
            titles = [i.findtext("title") for i in s.instances()]
            self.assertEqual(len(titles), len(set(titles)), titles)


class WireViewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = new_sketch(self.tmp.name)
        self.a = self.s.add_part_instance("A", "A1", ["bb", "sc", "pcb"], 0, 0)
        self.b = self.s.add_part_instance("B", "B1", ["bb", "sc", "pcb"], 100, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_flag_per_view(self):
        # Fritzing ties a wire to one view by its flag: 64 breadboard, 128 schematic, 4 pcb
        self.assertEqual(flags(wire(self.s, self.a, self.b, "bb")[0]), "64")
        self.assertEqual(flags(wire(self.s, self.a, self.b, "sc")[0]), "128")
        self.assertEqual(flags(wire(self.s, self.a, self.b, "pcb")[0]), "4")

    def test_straight_wire_geometry_and_ends(self):
        (w,) = wire(self.s, self.a, self.b, points=((5, 7), (45, 7)), color="#ff0000")
        geo = w.find("views/breadboardView/geometry")
        self.assertEqual((geo.get("x"), geo.get("y"), geo.get("x2"), geo.get("y2")),
                         ("5", "7", "40", "0"))
        self.assertEqual(w.find("views/breadboardView/wireExtras").get("color"), "#ff0000")
        e = ends(w)
        self.assertEqual(e["connector0"], (self.a.get("modelIndex"), "connector0", "breadboardbreadboard"))
        self.assertEqual(e["connector1"], (self.b.get("modelIndex"), "connector1", "breadboardbreadboard"))

    def test_bend_points_make_a_chain(self):
        chain = wire(self.s, self.a, self.b, points=((0, 0), (0, 50), (100, 50), (100, 0)))
        self.assertEqual(len(chain), 3)
        mid = chain[1]
        e = ends(mid)
        self.assertEqual(e["connector0"], (chain[0].get("modelIndex"), "connector1", "breadboardWire"))
        self.assertEqual(e["connector1"], (chain[2].get("modelIndex"), "connector0", "breadboardWire"))
        geo = mid.find("views/breadboardView/geometry")
        self.assertEqual((geo.get("x"), geo.get("y"), geo.get("x2"), geo.get("y2")),
                         ("0", "50", "100", "0"))
        self.assertEqual(ends(chain[0])["connector0"][0], self.a.get("modelIndex"))
        self.assertEqual(ends(chain[2])["connector1"][0], self.b.get("modelIndex"))


if __name__ == "__main__":
    unittest.main()
