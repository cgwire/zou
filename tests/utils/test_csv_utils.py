import unittest

from zou.app.utils.csv_utils import build_csv_file_name, build_csv_string


class CsvUtilsTestCase(unittest.TestCase):
    def test_build_csv_file_name(self):
        self.assertEqual(build_csv_file_name("My Export"), "kitsu_my_export")
        self.assertEqual(
            build_csv_file_name("Shot List 2024"), "kitsu_shot_list_2024"
        )

    def test_build_csv_file_name_special_chars(self):
        self.assertEqual(
            build_csv_file_name("é à ü"), "kitsu_e_a_u"
        )

    def test_build_csv_string_simple(self):
        content = [["Name", "Status"], ["SH01", "Done"], ["SH02", "WIP"]]
        result = build_csv_string(content)
        self.assertIn("Name;Status", result)
        self.assertIn("SH01;Done", result)
        self.assertIn("SH02;WIP", result)

    def test_build_csv_string_empty(self):
        self.assertEqual(build_csv_string([]), "")

    def test_build_csv_string_with_delimiter_in_value(self):
        content = [["Name", "Description"], ["SH01", "a;b"]]
        result = build_csv_string(content)
        self.assertIn('"a;b"', result)
