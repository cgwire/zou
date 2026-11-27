from flask_jwt_extended import jwt_required

from zou.app.blueprints.export.csv.base import BaseCsvExport
from zou.app.services import persons_service
from zou.app.utils import permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")
SALARY_COLUMN = 11


class PersonsCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)
        self.file_name = "people_export"
        self.studio_cache = {}

    @jwt_required()
    @swag_from(SPECS["PersonsCsvExport_get"])
    def get(self):
        """
        Export persons csv
        """
        return super().get()

    def build_headers(self):
        headers = [
            "First Name",
            "Last Name",
            "Email",
            "Phone",
            "Role",
            "Departments",
            "Studio",
            "Country",
            "Contract Type",
            "Position",
            "Seniority",
            "Daily Salary",
            "Active",
        ]
        return self.keep_salary_for_admins(headers)

    def keep_salary_for_admins(self, row):
        """
        The managers can get the export, but only the admins get the daily
        salary.
        """
        if not permissions.has_admin_permissions():
            del row[SALARY_COLUMN]
        return row

    def build_query(self):
        return persons_service.get_studio_team_persons_query()

    def get_studio_name(self, studio_id):
        if studio_id is None:
            return ""
        if studio_id not in self.studio_cache:
            self.studio_cache[studio_id] = persons_service.get_studio_raw(
                studio_id
            )
        studio = self.studio_cache[studio_id]
        return studio.name if studio is not None else ""

    def build_row(self, person):
        row = [
            person.first_name,
            person.last_name,
            person.email,
            person.phone,
            person.role.code,
            ",".join(sorted(d.name for d in person.departments)),
            self.get_studio_name(person.studio_id),
            person.country or "",
            person.contract_type.code,
            person.position.code if person.position else "",
            person.seniority.code if person.seniority else "",
            person.daily_salary if person.daily_salary is not None else "",
            "yes" if person.active else "no",
        ]
        return self.keep_salary_for_admins(row)
