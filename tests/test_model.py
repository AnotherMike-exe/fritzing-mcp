import os
import tempfile
import unittest

from fzkit import model

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "sketch.fz")


def new_sketch(tmp: str) -> model.FzSketch:
    return model.FzSketch.from_template(os.path.join(tmp, "T.fzz"), TEMPLATE)


def wire(sketch, a, b, views=("bb",)):
    return sketch.add_wire(
        endpoints=[("connector0", b.get("modelIndex"), "connector0"),
                   ("connector1", a.get("modelIndex"), "connector0")],
        views=list(views), origin=(0, 0), end_offsets=((0, 0), (10, 0)))


class WireTitleTest(unittest.TestCase):
    def test_titles_stay_unique_after_a_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = new_sketch(tmp)
            a = s.add_part_instance("A", "A1", ["bb"], 0, 0)
            b = s.add_part_instance("B", "B1", ["bb"], 100, 0)
            w1 = wire(s, a, b)
            wire(s, a, b)
            s.remove_instance(w1.findtext("title"))
            wire(s, a, b)
            titles = [i.findtext("title") for i in s.instances()]
            self.assertEqual(len(titles), len(set(titles)), titles)


if __name__ == "__main__":
    unittest.main()
