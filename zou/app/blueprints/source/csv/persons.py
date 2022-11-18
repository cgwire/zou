from zou.app.blueprints.source.csv.base import BaseCsvImportResource

from zou.app.models.person import Person
from zou.app.services import index_service, persons_service
from zou.app.utils import permissions


class PersonsCsvImportResource(BaseCsvImportResource):
    def post(self, **kwargs):
        """
        Import persons via a .csv file.
        ---
        tags:
            - Import
        consumes:
          - multipart/form-data
        parameters:
          - in: formData
            name: file
            type: file
            required: true
        responses:
            201:
                description: The lists of imported persons.
            400:
                description: The .csv file is not properly formatted.
        """
        return super().post(**kwargs)

    def check_permissions(self):
        return permissions.check_admin_permissions()

    def import_row(self, row):
        first_name = row["First Name"]
        last_name = row["Last Name"]
        email = row["Email"]
        phone = row.get("Phone", None)
        role = row.get("Role", None)

        role_map = {
            "Studio Manager": "admin",
            "Production Manager": "manager",
            "Supervisor": "supervisor",
            "Artist": "user",
            "Client": "client",
            "Vendor": "vendor",
        }

        data = {"first_name": first_name, "last_name": last_name}
        if role is not None and role != "":
            if role in role_map.keys():
                role = role_map[role]
            data["role"] = role
        if phone is not None and phone != "":
            data["phone"] = phone

        person = Person.get_by(email=email)
        if person is None:
            data["email"] = email
            data["password"] = None
            person = Person.create(**data)
        elif self.is_update:
            person.update(data)
        index_service.index_person(person)
        return person.serialize_safe()
