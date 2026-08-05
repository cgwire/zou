import orjson as json

from tests.base import ApiDBTestCase


class ShotgunTestCase(ApiDBTestCase):
    def setUp(self):
        super(ShotgunTestCase, self).setUp()

    def load_fixture(self, data_type):
        file_path = f"./tests/fixtures/shotgun/{data_type}.json"
        api_path = f"/import/shotgun/{data_type}"
        data = json.loads(open(file_path).read())
        return self.post(api_path, data, 200)
