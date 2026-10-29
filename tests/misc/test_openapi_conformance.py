import re

from tests.base import ApiDBTestCase

METHODS = ("get", "post", "put", "delete", "patch")
SWAGGER_2_OPERATION_KEYS = ("produces", "consumes")
SWAGGER_2_ROOT_KEYS = ("host", "basePath", "schemes")


class OpenApiConformanceTestCase(ApiDBTestCase):
    """
    The spec declares OpenAPI 3.0.2. Flasgger copies the yml files as they
    are, so Swagger 2 syntax used to reach /openapi.json and break the
    clients generated from it: 598 errors under a 3.0 validator.
    """

    def setUp(self):
        super().setUp()
        self.spec = self.app.get("/openapi.json").json

    def operations(self):
        for path, methods in self.spec["paths"].items():
            for method, operation in methods.items():
                if method in METHODS:
                    yield path, method, operation

    def test_no_swagger_2_root_keys(self):
        self.assertEqual(self.spec["openapi"], "3.0.2")
        for key in SWAGGER_2_ROOT_KEYS:
            self.assertNotIn(key, self.spec)

    def test_operations_are_openapi_3(self):
        bad = []
        for path, method, operation in self.operations():
            if "responses" not in operation:
                bad.append((path, method, "no responses"))
            for key in SWAGGER_2_OPERATION_KEYS:
                if key in operation:
                    bad.append((path, method, key))
            for parameter in operation.get("parameters", []):
                if parameter.get("in") in ("body", "formData"):
                    bad.append((path, method, parameter["name"]))
                elif "schema" not in parameter and "content" not in parameter:
                    bad.append((path, method, parameter["name"]))
        self.assertEqual(bad, [])

    def test_path_parameters_are_declared(self):
        bad = []
        for path, method, operation in self.operations():
            declared = {
                parameter["name"]
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "path"
            }
            for name in re.findall(r"\{([^}]+)\}", path):
                if name not in declared:
                    bad.append((path, method, name))
        self.assertEqual(bad, [])
