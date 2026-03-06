from tests.base import ApiDBTestCase
from zou.app.models.studio import Studio
from zou.app.utils import fields


class StudioTestCase(ApiDBTestCase):
    def setUp(self):
        super(StudioTestCase, self).setUp()
        self.generate_data(Studio, 3)

    def test_get_studios(self):
        studios = self.get("data/studios")
        self.assertEqual(len(studios), 3)

    def test_get_studio(self):
        studio = self.get_first("data/studios")
        studio_again = self.get("data/studios/%s" % studio["id"])
        self.assertEqual(studio, studio_again)
        self.get_404("data/studios/%s" % fields.gen_uuid())

    def test_create_studio(self):
        data = {"name": "Test Studio", "color": "#FF0000"}
        self.studio = self.post("data/studios", data)
        self.assertIsNotNone(self.studio["id"])
        studios = self.get("data/studios")
        self.assertEqual(len(studios), 4)

    def test_update_studio(self):
        studio = self.get_first("data/studios")
        data = {"color": "#00FF00"}
        self.put("data/studios/%s" % studio["id"], data)
        studio_again = self.get("data/studios/%s" % studio["id"])
        self.assertEqual(data["color"], studio_again["color"])
        self.put_404("data/studios/%s" % fields.gen_uuid(), data)

    def test_delete_studio(self):
        studios = self.get("data/studios")
        self.assertEqual(len(studios), 3)
        studio = studios[0]
        self.delete("data/studios/%s" % studio["id"])
        studios = self.get("data/studios")
        self.assertEqual(len(studios), 2)
        self.delete_404("data/studios/%s" % fields.gen_uuid())
