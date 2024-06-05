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
    ArgumentsException,
    PersonInProtectedAccounts,
)

from zou.app import config


class PersonsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Person)

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

    def check_read_permissions(self):
        return True

    def check_create_permissions(self, data):
        if (
            not data.get("is_bot", False)
            and data.get("active", True)
            and persons_service.is_user_limit_reached()
        ):
            raise ArgumentsException(
                "User limit reached.",
                {
                    "error": True,
                    "message": "User limit reached.",
                    "limit": config.USER_LIMIT,
                },
            )
        return permissions.check_admin_permissions()

    def check_creation_integrity(self, data):
        if "role" in data and data["role"] not in [
            role for role, _ in ROLE_TYPES
        ]:
            raise ArgumentsException("Invalid role")
        if "contract_type" in data and data["contract_type"] not in [
            contract_type for contract_type, _ in CONTRACT_TYPES
        ]:
            raise ArgumentsException("Invalid contract_type")
        if "two_factor_authentication" in data and data[
            "two_factor_authentication"
        ] not in [
            two_factor_authentication
            for two_factor_authentication, _ in TWO_FACTOR_AUTHENTICATION_TYPES
        ]:
            raise ArgumentsException("Invalid two_factor_authentication")

        if "expiration_date" in data and data["expiration_date"] is not None:
            try:
                if (
                    date_helpers.get_date_from_string(
                        data["expiration_date"]
                    ).date()
                    < datetime.date.today()
                ):
                    raise ArgumentsException(
                        "Expiration date can't be in the past."
                    )
            except:
                raise ArgumentsException("Expiration date is not valid.")
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
            raise ArgumentsException("Invalid role")
        if "contract_type" in data and data["contract_type"] not in [
            contract_type for contract_type, _ in CONTRACT_TYPES
        ]:
            raise ArgumentsException("Invalid contract_type")
        if "two_factor_authentication" in data and data[
            "two_factor_authentication"
        ] not in [
            two_factor_authentication
            for two_factor_authentication, _ in TWO_FACTOR_AUTHENTICATION_TYPES
        ]:
            raise ArgumentsException("Invalid two_factor_authentication")

        if "expiration_date" in data and data["expiration_date"] is not None:
            try:
                if (
                    datetime.datetime.strptime(
                        data["expiration_date"], "%Y-%m-%d"
                    ).date()
                    < datetime.date.today()
                ):
                    raise ArgumentsException(
                        "Expiration date can't be in the past."
                    )
            except:
                raise ArgumentsException("Expiration date is not valid.")
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
            raise ArgumentsException("User limit reached.")
        if instance_dict["email"] in config.PROTECTED_ACCOUNTS:
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
        Delete a person corresponding at given ID and return it as a JSON
        object.
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
