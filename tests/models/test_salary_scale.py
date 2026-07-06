from tests.base import ApiDBTestCase

from zou.app.models.department import Department
from zou.app.models.person import POSITION_TYPES, SENIORITY_TYPES
from zou.app.models.salary_scale import SalaryScale

from zou.app.utils import fields


class SalaryScaleTestCase(ApiDBTestCase):

    def test_get_salary_scales(self):
        """
        The list route auto-creates the missing (department, position,
        seniority) entries before returning them.
        """
        self.generate_fixture_department()
        departments = Department.query.all()
        salary_scales = self.get("data/salary-scales")
        expected = (
            len(departments) * len(POSITION_TYPES) * len(SENIORITY_TYPES)
        )
        self.assertEqual(len(salary_scales), expected)
        self.assertEqual(
            {scale["department_id"] for scale in salary_scales},
            {str(department.id) for department in departments},
        )

    def test_get_salary_scale(self):
        self.generate_fixture_department()
        salary_scale = self.get_first("data/salary-scales")
        salary_scale_again = self.get(
            f"data/salary-scales/{salary_scale['id']}"
        )
        self.assertEqual(salary_scale, salary_scale_again)
        self.get_404(f"data/salary-scales/{fields.gen_uuid()}")

    def test_update_salary_scale(self):
        self.generate_fixture_department()
        salary_scale = self.get_first("data/salary-scales")
        self.put(f"data/salary-scales/{salary_scale['id']}", {"salary": 640})
        salary_scale_again = self.get(
            f"data/salary-scales/{salary_scale['id']}"
        )
        self.assertEqual(salary_scale_again["salary"], 640)
        self.put_404(f"data/salary-scales/{fields.gen_uuid()}", {"salary": 1})

    def test_delete_salary_scale(self):
        self.generate_fixture_department()
        salary_scale = self.get_first("data/salary-scales")
        self.delete(f"data/salary-scales/{salary_scale['id']}")
        self.get_404(f"data/salary-scales/{salary_scale['id']}")
        self.delete_404(f"data/salary-scales/{fields.gen_uuid()}")

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
