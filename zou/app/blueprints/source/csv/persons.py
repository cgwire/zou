from zou.app.blueprints.source.csv.base import BaseCsvImportResource

from zou.app.models.person import Person, ROLE_TYPES, CONTRACT_TYPES
from zou.app.services import index_service
from zou.app.utils import permissions

from zou.app.utils.string import strtobool


class PersonsCsvImportResource(BaseCsvImportResource):
    def post(self):
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
        return super().post()

    def check_permissions(self):
        return permissions.check_admin_permissions()

    def prepare_import(self):
        self.role_types_map = {role[1]: role[0] for role in ROLE_TYPES}
        self.contract_types_map = {
            contract[1]: contract[0] for contract in CONTRACT_TYPES
        }

    def import_row(self, row):
        first_name = row["First Name"]
        last_name = row["Last Name"]
        email = row["Email"]
        phone = row.get("Phone", None)
        role = row.get("Role", None)
        contract_type = row.get("Contract Type", None)
        active = row.get("Active", None)

        data = {"first_name": first_name, "last_name": last_name}
        if role:
            if role in self.role_types_map.keys():
                role = self.role_types_map[role]
            elif role not in self.role_types_map.values():
                raise ValueError(f"Role: {role}")
            data["role"] = role
        if contract_type:
            if contract_type in self.contract_types_map.keys():
                contract_type = self.contract_types_map[contract_type]
            elif contract_type not in self.contract_types_map.values():
                raise ValueError(f"Contract Type: {contract_type}")
            data["contract_type"] = contract_type
        if phone:
            data["phone"] = phone
        if active:
            data["active"] = strtobool(active)

        person = Person.get_by(email=email, is_bot=False)
        if person is None:
            data["email"] = email
            data["password"] = None
            person = Person.create(**data)
        elif self.is_update:
            person.update(data)
        index_service.index_person(person)
        return person.serialize_safe()
