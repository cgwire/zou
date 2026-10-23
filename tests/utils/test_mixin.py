import unittest

from zou.app import app
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
