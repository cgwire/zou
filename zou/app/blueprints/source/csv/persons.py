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
        phone = row["Phone"]
        role = row.get("Role", None)

        if role == "Studio Manager":
            role = "admin"
        elif role == "Supervisor":
            role = "manager"
        elif role == "Client":
            role = "client"

        if (
            role is not None
            and len(role) > 0
            and role not in ["admin", "manager"]
        ):
            role = "user"

        try:
            person = Person.get_by(email=email)

            if person is None:
                if role is None:
                    role = "user"
                password = auth.encrypt_password("default")
                person = Person.create(
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    role=role,
                )
            elif self.is_update:
                data = {
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": phone,
                }
                if role is not None and len(role) > 0:
                    data["role"] = role
                person.update(data)
        except IntegrityError:
            person = Person.get_by(email=email)

        return person.serialize_safe()
