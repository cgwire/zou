import unittest

from zou.app.utils import colors


class ColorsTestCase(unittest.TestCase):
    def test_rgb_to_hex(self):
        self.assertEqual(colors.rgb_to_hex("0,0,0"), "#000000")
        self.assertEqual(colors.rgb_to_hex("255,255,255"), "#ffffff")
