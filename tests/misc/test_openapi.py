from tests.base import ApiTestCase


class OpenApiTestCase(ApiTestCase):
    def test_openapi_route(self):
        # A malformed YAML block in a single route docstring makes Flasgger
        # raise while building the whole spec, so /openapi.json answers a 500
        # and the apidocs deployment ships an error payload to Bump.sh.
        spec = self.get("/openapi.json")
        self.assertEqual(spec["openapi"], "3.0.2")
        self.assertTrue(len(spec["paths"]) > 0)
