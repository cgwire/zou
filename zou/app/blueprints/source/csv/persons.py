from flasgger import swag_from
from zou.app.blueprints.source.csv.base import (
    BaseCsvImportResource,
    RowException,
)

from zou.app.models.person import (
    ROLE_TYPES,
    CONTRACT_TYPES,
    POSITION_TYPES,
    SENIORITY_TYPES,
    normalize_country,
)
from zou.app.services import persons_service
from zou.app.utils import permissions

from zou.app.utils.string import strtobool


class PersonsCsvImportResource(BaseCsvImportResource):
    @swag_from("openapi/PersonsCsvImportResource_post.yml")
    def post(self):
        """
        Import persons csv
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
                persons_service.get_studio_raw_by_name,
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

        return persons_service.import_person(
            email, data, department_ids, update=self.is_update
        )

    def map_choice(self, label, value, choice_map):
        """
        Accept either a human label ("Lead") or a stored code ("lead") for a
        ChoiceType column, case-insensitively, and return the code. Raise
        ValueError (400) naming the accepted values on an unknown one.
        """
        folded = value.casefold()
        for choice_label, code in choice_map.items():
            if folded in (choice_label.casefold(), code.casefold()):
                return code
        raise ValueError(
            f"{label}: {value} (accepted values: {', '.join(choice_map)})"
        )

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
                persons_service.get_department_raw_by_name,
                name,
            )
            if department is None:
                raise RowException(f"Department not found: {name}")
            department_ids.append(department.id)
        return department_ids
