from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app import db
from zou.app.models.department import Department
from zou.app.models.person import Person, DepartmentLink
from zou.app.blueprints.source.shotgun.exception import (
    ShotgunEntryImportFailed,
)
from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)
from zou.app.services import tasks_service


class ImportShotgunPersonsResource(BaseImportShotgunResource):
    def __init__(self):
        BaseImportShotgunResource.__init__(self)

    @jwt_required()
    def post(self):
        """
        Import shotgun persons
        ---
        description: Import Shotgun persons (users). Send a list of Shotgun
          person entries in the JSON body. Returns created or updated persons
          with department associations.
        tags:
          - Import
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                      description: Shotgun ID of the person
                      example: 12345
                    firstname:
                      type: string
                      description: First name
                      example: "John"
                    lastname:
                      type: string
                      description: Last name
                      example: "Doe"
                    email:
                      type: string
                      format: email
                      description: Email address
                      example: "john.doe@example.com"
                    login:
                      type: string
                      description: Desktop login
                      example: "jdoe"
                    sg_status_list:
                      type: string
                      description: Status list
                      example: "act"
                    permission_rule_set:
                      type: object
                      description: Permission rule set
                      properties:
                        name:
                          type: string
                          example: "Manager"
                    department:
                      type: object
                      description: Department information
                      properties:
                        name:
                          type: string
                          example: "Animation"
              example:
                - id: 12345
                  firstname: "John"
                  lastname: "Doe"
                  email: "john.doe@example.com"
                  login: "jdoe"
                  sg_status_list: "act"
                  permission_rule_set:
                    name: "Manager"
                  department:
                    name: "Animation"
        responses:
          200:
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
                        description: Person unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      first_name:
                        type: string
                        description: First name
                        example: "John"
                      last_name:
                        type: string
                        description: Last name
                        example: "Doe"
                      email:
                        type: string
                        format: email
                        description: Email address
                        example: "john.doe@example.com"
                      role:
                        type: string
                        description: User role
                        example: "manager"
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Update timestamp
                        example: "2024-01-15T11:00:00Z"
          400:
            description: Invalid request body or data format error
        """
        return super().post()

    def extract_data(self, sg_person):
        is_active = sg_person.get("sg_status_list", "act") == "act"
        role = "user"

        rule_set = sg_person.get("permission_rule_set", {})
        permission_group = rule_set.get("name", "")
        if permission_group == "Manager":
            role = "manager"
        elif permission_group == "Admin":
            role = "admin"

        if sg_person.get("department", None) is not None:
            department = tasks_service.get_or_create_department(
                sg_person["department"]["name"]
            )
        else:
            department = None

        return {
            "first_name": sg_person["firstname"],
            "last_name": sg_person["lastname"],
            "email": sg_person["email"],
            "shotgun_id": sg_person["id"],
            "desktop_login": sg_person["login"],
            "active": is_active,
            "role": role,
            "department": department,
        }

    def import_entry(self, data):
        # remove departments. It needs to be created using the DepartmentLink
        # table.
        imported_department = data.pop("department")

        if data["email"] != "changeme@email.com":
            person = Person.get_by(shotgun_id=data["shotgun_id"])
            if person is None:
                person = Person.get_by(email=data["email"], is_bot=False)

            if person is None:
                data["password"] = None
                person = Person.create(**data)
                current_app.logger.info("Person created: %s" % person)
            # create or update a department/person link if needed
            if imported_department:
                department_person_link = (
                    db.session.query(DepartmentLink)
                    .filter_by(person_id=person.id)
                    .first()
                )
                department = Department.get_by(id=imported_department["id"])

                if department_person_link is None:
                    person.departments.append(department)
                    current_app.logger.info(
                        "Department Person Link created: %s-%s"
                        % (department.name, person.full_name)
                    )
                elif person.departments != [
                    department,
                ]:
                    person.departments = [
                        department,
                    ]
                    current_app.logger.info(
                        "Department Person Link updated: %s-%s"
                        % (department.name, person.full_name)
                    )

                person.save()

            return person

        else:
            raise ShotgunEntryImportFailed("This entry is not a real person.")


class ImportRemoveShotgunPersonResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, Person)

    @jwt_required()
    def post(self):
        """
        Remove shotgun person
        ---
        description: Remove a Shotgun person (user) from the database. Provide
          the Shotgun entry ID in the JSON body.
        tags:
          - Import
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - id
                properties:
                  id:
                    type: integer
                    description: Shotgun ID of the person to remove
                    example: 12345
              example:
                id: 12345
        responses:
          200:
            description: Removal result returned
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    success:
                      type: boolean
                      description: Whether the removal was successful
                      example: true
                    removed_instance_id:
                      type: string
                      format: uuid
                      description: ID of the removed person, if found
                      example: a24a6ea4-ce75-4665-a070-57453082c25
          400:
            description: Invalid request body or instance not found
        """
        return super().post()
