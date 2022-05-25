from zou.app.blueprints.source.csv.base import BaseCsvImportResource

from zou.app.models.person import Person
from zou.app.utils import auth, permissions

from sqlalchemy.exc import IntegrityError


class PersonsCsvImportResource(BaseCsvImportResource):
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
            data["password"] = auth.encrypt_password("default")
            person = Person.create(**data)
        elif self.is_update:
            person.update(data)

        return person.serialize_safe()
