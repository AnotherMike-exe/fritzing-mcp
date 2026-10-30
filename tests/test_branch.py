import os
import tempfile
import unittest

from fzkit import model

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "sketch.fz")


def connects(inst, conn):
    view = inst.find("views/breadboardView")
    for c in view.findall("connectors/connector"):
        if c.get("connectorId") == conn:
            return {(x.get("modelIndex"), x.get("connectorId"), x.get("layer"))
                    for x in c.findall("connects/connect")}
    return set()


class BranchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = model.FzSketch.from_template(os.path.join(self.tmp.name, "T.fzz"), TEMPLATE)
        self.r1 = self.s.add_part_instance("ResistorModuleID", "R1", ["bb"], 0, 0)
        self.r2 = self.s.add_part_instance("ResistorModuleID", "R2", ["bb"], 100, 0)
        self.r3 = self.s.add_part_instance("ResistorModuleID", "R3", ["bb"], 100, 100)

    def tearDown(self):
        self.tmp.cleanup()

    def test_wire_end_position(self):
        first, second = self.s.add_wire((self.r1.get("modelIndex"), "connector0"),
                                        (self.r2.get("modelIndex"), "connector0"),
                                        "bb", [(10, 10), (50, 10), (50, 40)])
        self.assertEqual(self.s.wire_end(first, "connector1"), (50, 10))
        self.assertEqual(self.s.wire_end(second, "connector1"), (50, 40))

    def test_branch_joins_every_wire_end_at_the_bend(self):
        first, second = self.s.add_wire((self.r1.get("modelIndex"), "connector0"),
                                        (self.r2.get("modelIndex"), "connector0"),
                                        "bb", [(10, 10), (50, 10), (50, 40)])
        (branch,) = self.s.add_wire((self.r3.get("modelIndex"), "connector0"),
                                    (first.get("modelIndex"), "connector1"),
                                    "bb", [(110, 110), (50, 10)])
        b = branch.get("modelIndex")
        layer = "breadboardWire"
        self.assertEqual(connects(branch, "connector1"),
                         {(first.get("modelIndex"), "connector1", layer),
                          (second.get("modelIndex"), "connector0", layer)})
        self.assertIn((b, "connector1", layer), connects(first, "connector1"))
        self.assertIn((b, "connector1", layer), connects(second, "connector0"))


if __name__ == "__main__":
    unittest.main()
