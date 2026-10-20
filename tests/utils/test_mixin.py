import unittest

from zou.app import app
from zou.app.exceptions import WrongParameterException
from zou.app.mixin import ArgsMixin


class ArgsMixinTestCase(unittest.TestCase):
    """
    get_args reads query parameters from descriptors of one to five
    elements. The one element form is a list holding the name only.
    """

    def test_every_descriptor_shape_reads_the_parameter(self):
        with app.test_request_context("/?name=Tree&limit=3&flag=true"):
            args = ArgsMixin().get_args(
                [
                    ["name"],
                    ("limit", 0),
                    ("flag", False, False, bool),
                    "missing",
                ]
            )
        self.assertEqual(args["name"], "Tree")
        self.assertEqual(args["limit"], "3")
        self.assertTrue(args["flag"])
        self.assertIsNone(args["missing"])

    def test_get_pagination_without_page_nor_limit(self):
        with app.test_request_context("/?name=Tree"):
            self.assertEqual(ArgsMixin().get_pagination(), (None, None))
        with app.test_request_context("/?page=0"):
            self.assertEqual(ArgsMixin().get_pagination(), (None, None))

    def test_get_pagination_with_page(self):
        with app.test_request_context("/?page=3"):
            self.assertEqual(
                ArgsMixin().get_pagination(),
                (3, app.config["NB_RECORDS_PER_PAGE"]),
            )
        with app.test_request_context("/?page=2&limit=20"):
            self.assertEqual(ArgsMixin().get_pagination(), (2, 20))

    def test_get_pagination_with_limit_only(self):
        with app.test_request_context("/?limit=20"):
            self.assertEqual(ArgsMixin().get_pagination(), (1, 20))
        with app.test_request_context("/?page=0&limit=20"):
            self.assertEqual(ArgsMixin().get_pagination(), (1, 20))

    def test_get_pagination_caps_limit(self):
        max_limit = app.config["MAX_RECORDS_PER_PAGE"]
        with app.test_request_context(f"/?limit={max_limit + 1}"):
            self.assertEqual(ArgsMixin().get_pagination(), (1, max_limit))

    def test_get_pagination_rejects_negative_limit(self):
        with app.test_request_context("/?limit=-1"):
            self.assertRaises(
                WrongParameterException, ArgsMixin().get_pagination
            )
