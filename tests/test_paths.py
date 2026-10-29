import unittest

from fzkit import paths


class ResolveTest(unittest.TestCase):
    def test_linux_checkout_default(self):
        r = paths.resolve({}, "linux", home="/home/u")
        self.assertEqual(r.parts_root, "/home/u/code/fritzing/fritzing/parts")
        self.assertEqual(r.fritzing_bin, "/home/u/code/fritzing/fritzing/Fritzing")
        self.assertEqual(r.local_parts, "/home/u/.local/share/Fritzing/Fritzing/local_parts")
        self.assertEqual(r.qt_platform, "wayland")

    def test_macos_bundle_default(self):
        r = paths.resolve({}, "darwin", home="/Users/u")
        self.assertEqual(r.parts_root,
                         "/Applications/Fritzing.app/Contents/Resources/fritzing-parts")
        self.assertEqual(r.fritzing_bin,
                         "/Applications/Fritzing.app/Contents/MacOS/Fritzing")
        self.assertEqual(r.local_parts,
                         "/Users/u/Library/Application Support/Fritzing/Fritzing/local_parts")
        self.assertEqual(r.qt_platform, "cocoa")
        self.assertEqual(r.launcher, ["open", "-a", "/Applications/Fritzing.app"])

    def test_app_root_pointing_at_a_bundle(self):
        r = paths.resolve({"FRITZING_APP_ROOT": "/opt/Fritzing.app"}, "darwin", home="/Users/u")
        self.assertEqual(r.parts_root, "/opt/Fritzing.app/Contents/Resources/fritzing-parts")
        self.assertEqual(r.fritzing_bin, "/opt/Fritzing.app/Contents/MacOS/Fritzing")

    def test_app_root_checkout_keeps_linux_layout_on_macos(self):
        r = paths.resolve({"FRITZING_APP_ROOT": "/src/fritzing"}, "darwin", home="/Users/u")
        self.assertEqual(r.parts_root, "/src/fritzing/parts")
        self.assertEqual(r.fritzing_bin, "/src/fritzing/Fritzing")

    def test_explicit_overrides_win(self):
        env = {"FRITZING_APP": "/x/Fritzing", "FRITZING_LOCAL_PARTS": "/x/lp",
               "QT_QPA_PLATFORM": "offscreen"}
        r = paths.resolve(env, "linux", home="/home/u")
        self.assertEqual(r.fritzing_bin, "/x/Fritzing")
        self.assertEqual(r.local_parts, "/x/lp")
        self.assertEqual(r.qt_platform, "offscreen")


if __name__ == "__main__":
    unittest.main()
