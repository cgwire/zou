from zou.app.blueprints.source.csv.base import (
    BaseCsvImportResource,
    RowException,
)

from zou.app.models.person import (
    Person,
    ROLE_TYPES,
    CONTRACT_TYPES,
    POSITION_TYPES,
    SENIORITY_TYPES,
    normalize_country,
)
from zou.app.models.department import Department
from zou.app.models.studio import Studio
from zou.app.services import index_service
from zou.app.utils import permissions

from zou.app.utils.string import strtobool


class PersonsCsvImportResource(BaseCsvImportResource):
    def post(self):
        """
        Import persons csv
        ---
        tags:
          - Import
        description: Import persons from a CSV file. Creates or updates
          persons based on CSV rows. Supports first/last name, email, phone,
          role, departments, studio, country, contract type, position,
          seniority, daily salary and active status.
        consumes:
          - multipart/form-data
        parameters:
          - in: query
            name: update
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Whether to update existing persons
          - in: formData
            name: file
            type: file
            required: true
            description: CSV file with person data
        responses:
            201:
              description: Persons imported successfully
              content:
                application/json:
                  schema:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        first_name:
                          type: string
                          example: John
                        last_name:
                          type: string
                          example: Doe
                        email:
                          type: string
                          format: email
                          example: john.doe@example.com
                        phone:
                          type: string
                          example: +1234567890
                        role:
                          type: string
                          example: user
                        departments:
                          type: array
                          items:
                            type: string
                            format: uuid
                          example: []
                        studio_id:
                          type: string
                          format: uuid
                          example: null
                        country:
                          type: string
                          description: ISO 3166-1 alpha-2 country code (nullable)
                          example: FR
                        contract_type:
                          type: string
                          example: open-ended
                        position:
                          type: string
                          example: lead
                        seniority:
                          type: string
                          example: senior
                        daily_salary:
                          type: integer
                          example: 320
                        active:
                          type: boolean
                          example: true
            400:
              description: Invalid CSV format or missing required columns
        """
        return super().post()

    def check_permissions(self):
        return permissions.check_admin_permissions()

    def prepare_import(self):
        self.role_types_map = {role[1]: role[0] for role in ROLE_TYPES}
        self.contract_types_map = {
            contract[1]: contract[0] for contract in CONTRACT_TYPES
        }
        self.position_types_map = {
            position[1]: position[0] for position in POSITION_TYPES
        }
        self.seniority_types_map = {
            seniority[1]: seniority[0] for seniority in SENIORITY_TYPES
        }
        self.studio_cache = {}
        self.department_cache = {}

    def import_row(self, row):
        first_name = row["First Name"]
        last_name = row["Last Name"]
        email = row["Email"]
        phone = row.get("Phone", None)
        role = row.get("Role", None)
        contract_type = row.get("Contract Type", None)
        position = row.get("Position", None)
        seniority = row.get("Seniority", None)
        country = row.get("Country", None)
        daily_salary = row.get("Daily Salary", None)
        studio_name = row.get("Studio", None)
        departments_value = row.get("Departments", None)
        active = row.get("Active", None)

        data = {"first_name": first_name, "last_name": last_name}
        if role:
            data["role"] = self.map_choice("Role", role, self.role_types_map)
        if contract_type:
            data["contract_type"] = self.map_choice(
                "Contract Type", contract_type, self.contract_types_map
            )
        if position:
            data["position"] = self.map_choice(
                "Position", position, self.position_types_map
            )
        if seniority:
            data["seniority"] = self.map_choice(
                "Seniority", seniority, self.seniority_types_map
            )
        # Share the Person model rule (ISO 3166-1 alpha-2) but fail the row
        # instead of silently storing None like the model validator.
        is_valid_country, normalized_country = normalize_country(country)
        if not is_valid_country:
            raise ValueError(f"Country: {country}")
        if normalized_country:
            data["country"] = normalized_country
        if daily_salary:
            try:
                data["daily_salary"] = int(daily_salary)
            except ValueError:
                raise ValueError(f"Daily Salary: {daily_salary}")
        if studio_name:
            studio = self.add_to_cache_if_absent(
                self.studio_cache,
                lambda name: Studio.get_by(name=name),
                studio_name,
            )
            if studio is None:
                raise RowException(f"Studio not found: {studio_name}")
            data["studio_id"] = studio.id
        if phone:
            data["phone"] = phone
        if active:
            data["active"] = strtobool(active)

        # Resolve departments before any write so an unknown name fails the
        # row without leaving an orphan person behind.
        department_ids = None
        if departments_value:
            department_ids = self.resolve_departments(departments_value)

        person = Person.get_by(email=email, is_bot=False)
        created = person is None
        if created:
            data["email"] = email
            data["password"] = None
            person = Person.create(**data)
        elif self.is_update:
            person.update(data)

        if (created or self.is_update) and department_ids is not None:
            person.set_departments(department_ids)

        index_service.index_person(person)
        return person.serialize_safe()

    def map_choice(self, label, value, choice_map):
        """
        Accept either a human label ("Lead") or a stored code ("lead") for a
        ChoiceType column and return the code. Raise ValueError (400) on an
        unknown value, like the other typed columns.
        """
        if value in choice_map:
            return choice_map[value]
        if value not in choice_map.values():
            raise ValueError(f"{label}: {value}")
        return value

    def resolve_departments(self, departments_value):
        """
        Turn a comma-separated list of department names into a list of UUIDs,
        raising RowException (400) on any unknown name. Names are matched
        exactly (case-sensitive), like the other typed columns.
        """
        department_ids = []
        for name in [
            name.strip()
            for name in departments_value.split(",")
            if name.strip()
        ]:
            department = self.add_to_cache_if_absent(
                self.department_cache,
                lambda name: Department.get_by(name=name),
                name,
            )
            if department is None:
                raise RowException(f"Department not found: {name}")
            department_ids.append(department.id)
        return department_ids
