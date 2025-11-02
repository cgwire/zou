from zou.app.blueprints.export.csv.base import BaseCsvExport
from flask_jwt_extended import jwt_required

from zou.app.models.person import Person


class PersonsCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)
        self.file_name = "people_export"

    @jwt_required()
    def get(self):
        """
        Export persons csv
        ---
        tags:
          - Export
        description: Export persons as CSV file. Includes person information
          with last name, first name, email, phone, role, contract type,
          and active status. Excludes bot accounts.
        produces:
          - text/csv
        responses:
            200:
              description: Persons exported as CSV successfully
              content:
                text/csv:
                  schema:
                    type: string
                  example: "Last Name,First Name,Email,Phone,Role,Contract Type,Active\nDoe,John,john.doe@example.com,+1234567890,user,freelance,yes"
        """
        return super().get()

    def build_headers(self):
        return [
            "Last Name",
            "First Name",
            "Email",
            "Phone",
            "Role",
            "Contract Type",
            "Active",
        ]

    def build_query(self):
        return Person.query.filter(Person.is_bot == False).order_by(
            Person.last_name, Person.first_name
        )

    def build_row(self, person):
        active = "yes"
        if not person.active:
            active = "no"
        return [
            person.last_name,
            person.first_name,
            person.email,
            person.phone,
            person.role.code,
            person.contract_type.code,
            active,
        ]
