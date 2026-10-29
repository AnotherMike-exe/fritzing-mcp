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
