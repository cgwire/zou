from zou.app.blueprints.export.csv.base import BaseCsvExport
from flask_jwt_extended import jwt_required
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from zou.app.models.person import Person
from zou.app.models.studio import Studio


class PersonsCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)
        self.file_name = "people_export"
        self.studio_cache = {}

    @jwt_required()
    def get(self):
        """
        Export persons csv
        ---
        tags:
          - Export
        description: Export persons as CSV file. Includes first name, last
          name, email, phone, role, departments, studio, country, contract
          type, position, seniority, daily salary and active status.
          Excludes bot accounts.
        produces:
          - text/csv
        responses:
            200:
              description: Persons exported as CSV successfully
              content:
                text/csv:
                  schema:
                    type: string
                  example: "First Name;Last Name;Email;Phone;Role;Departments;Studio;Country;Contract Type;Position;Seniority;Daily Salary;Active\nJohn;Doe;john.doe@example.com;+1234567890;user;Animation;Paris;FR;freelance;artist;mid;320;yes"
        """
        return super().get()

    def build_headers(self):
        return [
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

    def build_query(self):
        return (
            Person.query.options(selectinload(Person.departments))
            .filter(Person.is_bot.isnot(True), Person.is_guest.isnot(True))
            .order_by(
                func.lower(Person.first_name),
                func.lower(Person.last_name),
            )
        )

    def get_studio_name(self, studio_id):
        if studio_id is None:
            return ""
        if studio_id not in self.studio_cache:
            self.studio_cache[studio_id] = Studio.get(studio_id)
        studio = self.studio_cache[studio_id]
        return studio.name if studio is not None else ""

    def build_row(self, person):
        return [
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
