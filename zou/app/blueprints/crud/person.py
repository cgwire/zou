import datetime

from flask_jwt_extended import jwt_required

from zou.app.models.person import (
    Person,
    ROLE_TYPES,
    CONTRACT_TYPES,
    TWO_FACTOR_AUTHENTICATION_TYPES,
)
from zou.app.services import (
    deletion_service,
    index_service,
    persons_service,
)
from zou.app.utils import permissions, auth, date_helpers

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.mixin import ArgsMixin

from zou.app.services.exception import (
    WrongParameterException,
    PersonInProtectedAccounts,
)

from zou.app import config


class PersonsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Person)

    @jwt_required()
    def get(self):
        """
        Get persons
        ---
        tags:
          - Crud
        description: Retrieve all persons. Supports filtering via query
          parameters and pagination. Admin users can include password
          hashes. Non-admin users only see minimal information.
        parameters:
          - in: query
            name: page
            required: false
            schema:
              type: integer
            example: 1
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            schema:
              type: integer
            example: 50
            description: Number of results per page
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Whether to include relations
          - in: query
            name: with_pass_hash
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Include password hash (admin only)
        responses:
            200:
              description: Persons retrieved successfully
              content:
                application/json:
                  schema:
                    oneOf:
                      - type: array
                        items:
                          type: object
                      - type: object
                        properties:
                          data:
                            type: array
                            items:
                              type: object
                            example: []
                          total:
                            type: integer
                            example: 100
                          nb_pages:
                            type: integer
                            example: 2
                          limit:
                            type: integer
                            example: 50
                          offset:
                            type: integer
                            example: 0
                          page:
                            type: integer
                            example: 1
            400:
              description: Invalid filter format or query error
        """
        return super().get()

    @jwt_required()
    def post(self):
        """
        Create person
        ---
        tags:
          - Crud
        description: Create a new person with data provided in the
          request body. JSON format is expected. Requires admin
          permissions. Validates role, contract_type, two_factor_authentication,
          email, and expiration_date. Checks user limit for active non-bot users.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - first_name
                  - last_name
                  - email
                properties:
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
                  password:
                    type: string
                    example: securepassword123
                  role:
                    type: string
                    example: user
                  active:
                    type: boolean
                    default: true
                    example: true
                  contract_type:
                    type: string
                    example: permanent
                  two_factor_authentication:
                    type: string
                    example: none
                  expiration_date:
                    type: string
                    format: date
                    example: "2025-12-31"
                  is_bot:
                    type: boolean
                    default: false
                    example: false
        responses:
            201:
              description: Person created successfully
              content:
                application/json:
                  schema:
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
                      role:
                        type: string
                        example: user
                      active:
                        type: boolean
                        example: true
                      contract_type:
                        type: string
                        example: permanent
                      two_factor_authentication:
                        type: string
                        example: none
                      access_token:
                        type: string
                        example: eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or validation error or user limit reached
        """
        return super().post()

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        if permissions.has_admin_permissions():
            if self.get_bool_parameter("with_pass_hash"):
                return [
                    person.serialize(relations=relations)
                    for person in query.all()
                ]
            else:
                return [
                    person.serialize_safe(relations=relations)
                    for person in query.all()
                ]
        else:
            return [
                person.present_minimal(relations=relations)
                for person in query.all()
            ]

    def check_read_permissions(self, options=None):
        return True

    def check_create_permissions(self, data):
        if (
            not data.get("is_bot", False)
            and data.get("active", True)
            and persons_service.is_user_limit_reached()
        ):
            raise WrongParameterException(
                "User limit reached.",
                {
                    "limit": config.USER_LIMIT,
                },
            )
        return permissions.check_admin_permissions()

    def check_creation_integrity(self, data):
        if "role" in data and data["role"] not in [
            role for role, _ in ROLE_TYPES
        ]:
            raise WrongParameterException("Invalid role")
        if "contract_type" in data and data["contract_type"] not in [
            contract_type for contract_type, _ in CONTRACT_TYPES
        ]:
            raise WrongParameterException("Invalid contract_type")
        if "two_factor_authentication" in data and data[
            "two_factor_authentication"
        ] not in [
            two_factor_authentication
            for two_factor_authentication, _ in TWO_FACTOR_AUTHENTICATION_TYPES
        ]:
            raise WrongParameterException("Invalid two_factor_authentication")

        if "expiration_date" in data and data["expiration_date"] is not None:
            try:
                if (
                    date_helpers.get_date_from_string(
                        data["expiration_date"]
                    ).date()
                    < datetime.date.today()
                ):
                    raise WrongParameterException(
                        "Expiration date can't be in the past."
                    )
            except WrongParameterException:
                raise
            except:
                raise WrongParameterException("Expiration date is not valid.")

        if "email" in data:
            try:
                data["email"] = auth.validate_email(data["email"])
            except auth.EmailNotValidException as e:
                raise WrongParameterException(str(e))

        return data

    def update_data(self, data):
        data = super().update_data(data)
        if "password" in data and data["password"] is not None:
            data["password"] = auth.encrypt_password(data["password"])
        if "email" in data:
            data["email"] = data["email"].strip()
        return data

    def post_creation(self, instance):
        instance_dict = instance.serialize(relations=True)
        if instance.is_bot:
            instance_dict["access_token"] = (
                persons_service.create_access_token_for_raw_person(instance)
            )
        if instance.active:
            index_service.index_person(instance)
        persons_service.clear_person_cache()
        return instance_dict


class PersonResource(BaseModelResource, ArgsMixin):
    def __init__(self):
        BaseModelResource.__init__(self, Person)
        self.protected_fields += ["password", "jti"]

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Get person
        ---
        tags:
          - Crud
        description: Retrieve a person by their ID and return it as a
          JSON object. Supports including relations. Managers see safe
          serialization, others see minimal information.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to include relations
        responses:
            200:
              description: Person retrieved successfully
              content:
                application/json:
                  schema:
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
                      role:
                        type: string
                        example: user
                      active:
                        type: boolean
                        example: true
                      contract_type:
                        type: string
                        example: permanent
                      two_factor_authentication:
                        type: string
                        example: none
                      departments:
                        type: array
                        items:
                          type: string
                          format: uuid
                        example: []
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid ID format or query error
        """
        return super().get(instance_id)

    @jwt_required()
    def put(self, instance_id):
        """
        Update person
        ---
        tags:
          - Crud
        description: Update a person with data provided in the request
          body. JSON format is expected. Users can only update themselves
          unless they have admin permissions. Non-admins cannot change
          certain protected fields. Validates role, contract_type,
          two_factor_authentication, email, and expiration_date. Checks
          user limit when activating non-bot users. Protected accounts
          have restrictions.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  first_name:
                    type: string
                    example: Jane
                  last_name:
                    type: string
                    example: Smith
                  email:
                    type: string
                    format: email
                    example: jane.smith@example.com
                  password:
                    type: string
                    example: newsecurepassword123
                  role:
                    type: string
                    example: manager
                    description: Admin only
                  active:
                    type: boolean
                    example: true
                    description: Admin only
                  contract_type:
                    type: string
                    example: freelance
                  two_factor_authentication:
                    type: string
                    example: totp
                  expiration_date:
                    type: string
                    format: date
                    example: "2025-12-31"
                    description: Person or admin only
        responses:
            200:
              description: Person updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      first_name:
                        type: string
                        example: Jane
                      last_name:
                        type: string
                        example: Smith
                      email:
                        type: string
                        format: email
                        example: jane.smith@example.com
                      role:
                        type: string
                        example: manager
                      active:
                        type: boolean
                        example: true
                      contract_type:
                        type: string
                        example: freelance
                      two_factor_authentication:
                        type: string
                        example: totp
                      departments:
                        type: array
                        items:
                          type: string
                          format: uuid
                        example: []
                      access_token:
                        type: string
                        example: eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or validation error or user limit reached or protected account restriction
        """
        return super().put(instance_id)

    def check_update_permissions(self, instance_dict, data):
        if instance_dict["id"] != persons_service.get_current_user()["id"]:
            permissions.check_admin_permissions()
        return instance_dict

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        if not permissions.has_admin_permissions():
            if not permissions.has_person_permissions():
                data.pop("expiration_date", None)
            data.pop("role", None)
            data.pop("departments", None)
            data.pop("active", None)
            data.pop("is_bot", None)
            data.pop("archived", None)
            data.pop("login_failed_attemps", None)
            data.pop("last_login_failed", None)
            data.pop("is_generated_from_ldap", None)
            data.pop("ldap_uid", None)
            data.pop("last_presence", None)
            data.pop("studio_id", None)

        if "role" in data and data["role"] not in [
            role for role, _ in ROLE_TYPES
        ]:
            raise WrongParameterException("Invalid role")
        if "contract_type" in data and data["contract_type"] not in [
            contract_type for contract_type, _ in CONTRACT_TYPES
        ]:
            raise WrongParameterException("Invalid contract_type")
        if "two_factor_authentication" in data and data[
            "two_factor_authentication"
        ] not in [
            two_factor_authentication
            for two_factor_authentication, _ in TWO_FACTOR_AUTHENTICATION_TYPES
        ]:
            raise WrongParameterException("Invalid two_factor_authentication")

        if "expiration_date" in data and data["expiration_date"] is not None:
            try:
                if (
                    datetime.datetime.strptime(
                        data["expiration_date"], "%Y-%m-%d"
                    ).date()
                    < datetime.date.today()
                ):
                    raise WrongParameterException(
                        "Expiration date can't be in the past."
                    )
            except WrongParameterException:
                raise
            except:
                raise WrongParameterException("Expiration date is not valid.")

        if "email" in data:
            try:
                data["email"] = auth.validate_email(data["email"])
            except auth.EmailNotValidException as e:
                raise WrongParameterException(str(e))

        return data

    def check_delete_permissions(self, instance_dict):
        if instance_dict["id"] == persons_service.get_current_user()["id"]:
            raise permissions.PermissionDenied
        permissions.check_admin_permissions()
        return instance_dict

    def serialize_instance(self, instance, relations=True):
        if permissions.has_manager_permissions():
            return instance.serialize_safe(relations=relations)
        else:
            return instance.present_minimal(relations=relations)

    def pre_update(self, instance_dict, data):
        if (
            not instance_dict.get("active", False)
            and data.get("active", False)
            and not instance_dict.get("is_bot", False)
            and not data.get("is_bot", False)
            and persons_service.is_user_limit_reached()
        ):
            raise WrongParameterException("User limit reached.")
        if (
            instance_dict["email"] in config.PROTECTED_ACCOUNTS
            and instance_dict["id"] != persons_service.get_current_user()["id"]
        ):
            message = None
            if data.get("active") is False:
                message = "Can't set this person as inactive it's a protected account."
            elif data.get("role") is not None:
                message = "Can't change the role of this person it's a protected account."

            if message is not None:
                raise PersonInProtectedAccounts(message)
        return data

    def post_update(self, instance_dict, data):
        persons_service.clear_person_cache()
        index_service.remove_person_index(instance_dict["id"])
        person = persons_service.get_person_raw(instance_dict["id"])
        if person.active:
            index_service.index_person(person)
        instance_dict["departments"] = [
            str(department.id) for department in self.instance.departments
        ]
        if "expiration_date" in data:
            instance_dict["access_token"] = (
                persons_service.create_access_token_for_raw_person(
                    self.instance
                )
            )
        return instance_dict

    def post_delete(self, instance_dict):
        persons_service.clear_person_cache()
        return instance_dict

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete person
        ---
        tags:
          - Crud
        description: Delete a person by their ID. Returns empty response
          on success. Cannot delete yourself.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: force
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Force deletion even if person has associated data
        responses:
            204:
              description: Person deleted successfully
            400:
              description: Cannot delete person or integrity error
        """
        force = self.get_force()
        person = self.get_model_or_404(instance_id)
        person_dict = person.serialize()
        self.check_delete_permissions(person_dict)
        self.pre_delete(person_dict)
        deletion_service.remove_person(instance_id, force=force)
        index_service.remove_person_index(instance_id)
        self.emit_delete_event(person_dict)
        self.post_delete(person_dict)
        return "", 204
