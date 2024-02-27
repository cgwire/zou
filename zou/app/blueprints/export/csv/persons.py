from zou.app.blueprints.export.csv.base import BaseCsvExport

from zou.app.models.person import Person


class PersonsCsvExport(BaseCsvExport):
    def __init__(self):
        BaseCsvExport.__init__(self)
        self.file_name = "people_export"

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
