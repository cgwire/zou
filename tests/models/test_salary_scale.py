from tests.base import ApiDBTestCase

from zou.app.models.salary_scale import SalaryScale

from zou.app.utils import fields


class SalaryScaleTestCase(ApiDBTestCase):
    def setUp(self):
        super(SalaryScaleTestCase, self).setUp()
        # self.generate_data(SalaryScale, 3)

    def test_get_salary_scales(self):
        pass
        # salary_scales = self.get("data/salary-scales")
        # self.assertEqual(len(salary_scales), 3)

    """
    def test_get_salary_scale(self):
        salary_scale = self.get_first("data/salary-scales")
        salary_scale_again = self.get(
            "data/salary-scales/%s" % salary_scale["id"]
        )
        self.assertEqual(salary_scale, salary_scale_again)
        self.get_404("data/salary-scales/%s" % fields.gen_uuid())

    def test_create_salary_scale(self):
        data = {"position": "artist", "seniority": "junior", "daily_salary": 500}
        self.salary_scale = self.post("data/salary-scales", data)
        self.assertIsNotNone(self.salary_scale["id"])

        salary_scales = self.get("data/salary-scales")
        self.assertEqual(len(salary_scales), 4)

    def test_update_salary_scale(self):
        salary_scale = self.get_first("data/salary-scales")
        data = {"position": "lead", "seniority": "senior", "daily_salary": 600}
        self.put("data/salary-scales/%s" % salary_scale["id"], data)
        salary_scale_again = self.get(
            "data/salary-scales/%s" % salary_scale["id"]
        )
        self.assertEqual(data["position"], salary_scale_again["position"])
        self.put_404("data/salary-scales/%s" % fields.gen_uuid(), data)

    def test_delete_salary_scale(self):
        salary_scales = self.get("data/salary-scales")
        self.assertEqual(len(salary_scales), 3)
        salary_scale = salary_scales[0]
        self.delete("data/salary-scales/%s" % salary_scale["id"])
        salary_scales = self.get("data/salary-scales")
        self.assertEqual(len(salary_scales), 2)
        self.delete_404("data/salary-scales/%s" % fields.gen_uuid())
    """
