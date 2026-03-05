import unittest

from pydantic import BaseModel

from zou.app.utils.validation import _format_validation_errors, validate_request_body
from zou.app.services.exception import WrongParameterException


class SampleSchema(BaseModel):
    name: str
    count: int


class ValidationTestCase(unittest.TestCase):
    def test_validate_request_body_success(self):
        result = validate_request_body(
            SampleSchema, data={"name": "test", "count": 5}
        )
        self.assertEqual(result.name, "test")
        self.assertEqual(result.count, 5)

    def test_validate_request_body_coercion(self):
        result = validate_request_body(
            SampleSchema, data={"name": "test", "count": "3"}
        )
        self.assertEqual(result.count, 3)

    def test_validate_request_body_missing_field(self):
        with self.assertRaises(WrongParameterException) as ctx:
            validate_request_body(SampleSchema, data={"name": "test"})
        self.assertIn("errors", ctx.exception.dict)
        errors = ctx.exception.dict["errors"]
        self.assertTrue(
            any(e["field"] == "count" for e in errors)
        )

    def test_validate_request_body_wrong_type(self):
        with self.assertRaises(WrongParameterException) as ctx:
            validate_request_body(
                SampleSchema, data={"name": "test", "count": "abc"}
            )
        errors = ctx.exception.dict["errors"]
        self.assertTrue(
            any(e["field"] == "count" for e in errors)
        )

    def test_format_validation_errors(self):
        try:
            SampleSchema.model_validate({"name": "test"})
        except Exception as e:
            errors = _format_validation_errors(e)
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0]["field"], "count")
            self.assertIn("message", errors[0])
