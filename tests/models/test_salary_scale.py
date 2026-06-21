from tests.base import ApiDBTestCase

from zou.app.models.department import Department
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

    def test_delete_department_cascades_salary_scales(self):
        """
        A department must stay deletable even though salary scale entries
        reference it: the entries are auto-generated and meaningless without
        the department, so they are removed by the ON DELETE CASCADE foreign
        key instead of blocking the deletion.
        """
        department = Department.create(name="Modeling", color="#FFFFFF")
        SalaryScale.create(
            department_id=department.id,
            position="artist",
            seniority="junior",
            salary=500,
        )
        SalaryScale.create(
            department_id=department.id,
            position="lead",
            seniority="senior",
            salary=900,
        )
        self.assertEqual(
            SalaryScale.query.filter_by(department_id=department.id).count(), 2
        )

        department.delete()

        self.assertIsNone(Department.get(department.id))
        self.assertEqual(
            SalaryScale.query.filter_by(department_id=department.id).count(), 0
        )

    """
    def test_get_salary_scale(self):
        salary_scale = self.get_first("data/salary-scales")
        salary_scale_again = self.get(
            f"data/salary-scales/{salary_scale['id']}"
        )
        self.assertEqual(salary_scale, salary_scale_again)
        self.get_404(f"data/salary-scales/{fields.gen_uuid()}")

    def test_create_salary_scale(self):
        data = {"position": "artist", "seniority": "junior", "daily_salary": 500}
        self.salary_scale = self.post("data/salary-scales", data)
        self.assertIsNotNone(self.salary_scale["id"])

        salary_scales = self.get("data/salary-scales")
        self.assertEqual(len(salary_scales), 4)

    def test_update_salary_scale(self):
        salary_scale = self.get_first("data/salary-scales")
        data = {"position": "lead", "seniority": "senior", "daily_salary": 600}
        self.put(f"data/salary-scales/{salary_scale['id']}", data)
        salary_scale_again = self.get(
            f"data/salary-scales/{salary_scale['id']}"
        )
        self.assertEqual(data["position"], salary_scale_again["position"])
        self.put_404(f"data/salary-scales/{fields.gen_uuid()}", data)

    def test_delete_salary_scale(self):
        salary_scales = self.get("data/salary-scales")
        self.assertEqual(len(salary_scales), 3)
        salary_scale = salary_scales[0]
        self.delete(f"data/salary-scales/{salary_scale['id']}")
        salary_scales = self.get("data/salary-scales")
        self.assertEqual(len(salary_scales), 2)
        self.delete_404(f"data/salary-scales/{fields.gen_uuid()}")
    """
