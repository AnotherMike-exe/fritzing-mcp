import os
import tempfile
import unittest

from fzkit import partsdb

FZP = """<?xml version="1.0" encoding="UTF-8"?>
<module moduleId="ai-demo-1ModuleID">
 <title>Demo Board</title>
 <label>U</label>
 <tags><tag>plum</tag><tag>level shifter</tag></tags>
 <properties><property name="family">custom</property></properties>
</module>
"""


class LocalPartsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, "ai-demo-1ModuleID"))
        with open(os.path.join(self.tmp.name, "ai-demo-1ModuleID", "part.fzp"), "w") as f:
            f.write(FZP)
        self.saved = partsdb.LOCAL_PARTS_DIR
        partsdb.LOCAL_PARTS_DIR = self.tmp.name

    def tearDown(self):
        partsdb.LOCAL_PARTS_DIR = self.saved
        self.tmp.cleanup()

    def test_matches_a_tag(self):
        self.assertEqual([p.module_id for p in partsdb.local_parts("plum")],
                         ["ai-demo-1ModuleID"])

    def test_matches_title_case_insensitive(self):
        self.assertEqual(len(partsdb.local_parts("demo board")), 1)

    def test_no_match_across_field_boundary(self):
        # title "Demo Board" + label "U" must not join into "boardu"
        self.assertEqual(partsdb.local_parts("boardu"), [])


if __name__ == "__main__":
    unittest.main()
