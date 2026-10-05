from flasgger import swag_from
import datetime

import sqlalchemy.orm as orm
from flask_jwt_extended import jwt_required
from sqlalchemy.inspection import inspect

from zou.app.models.person import (
    Person,
    ROLE_TYPES,
    CONTRACT_TYPES,
    DISPLAY_DATE_FORMATS,
    SENSITIVE_FIELDS,
    TWO_FACTOR_AUTHENTICATION_TYPES,
    normalize_country,
    normalize_locale,
)

# Columns behind Person.present_minimal, the payload every non admin gets
# from the list route, plus email. Email is not in that payload but the
# lookup is part of the API every studio pipeline builds on
# (gazu.person.get_person_by_email); matching an address the caller already
# holds is not the sweep the other hidden columns allow, since equality
# answers nothing about a value that has not been guessed first.
MINIMAL_PERSON_FILTER_FIELDS = [
    "id",
    "first_name",
    "last_name",
    "full_name",
    "has_avatar",
    "active",
    "departments",
    "studio_id",
    "role",
    "desktop_login",
    "email",
    "is_bot",
    "is_guest",
]
from zou.app.services import (
    deletion_service,
    index_service,
    persons_service,
)
from zou.app.utils import permissions, auth, date_helpers
from zou.app.utils.fields import serialize_value

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.mixin import ArgsMixin

from zou.app.exceptions import (
    WrongParameterException,
    PersonInProtectedAccounts,
)

from zou.app import config


def check_country(data):
    """
    Reject an invalid country code with a clean 400. Empty or missing values
    are treated as "no country" and accepted. The stored value is normalized
    to uppercase by the Person model.
    """
    is_valid, _ = normalize_country(data.get("country"))
    if not is_valid:
        raise WrongParameterException(
            "Invalid country code, expected an ISO 3166-1 alpha-2 code."
        )


def check_locale(data):
    """
    Reject a locale that Python Babel cannot parse with a clean 400. Empty or
    missing values are treated as "no locale" and accepted. Without this guard
    the raw value would be stored and then break every later read of the
    person, since the model re-parses the locale through Babel on load.
    """
    is_valid, _ = normalize_locale(data.get("locale"))
    if not is_valid:
        raise WrongParameterException(
            "Invalid locale, expected a name available in Python Babel "
            "(e.g. en_US, fr_FR)."
        )


def check_display_date_format(data):
    """
    Reject a display date format outside the supported list with a clean
    400. A missing or null value is treated as "use the default" and
    accepted.
    """
    value = data.get("display_date_format")
    if value is not None and value not in DISPLAY_DATE_FORMATS:
        raise WrongParameterException(
            "Invalid display_date_format, expected one of: "
            f"{', '.join(DISPLAY_DATE_FORMATS)}."
        )


class PersonsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Person)

    def get_relations_eager_load(self):
        return [Person.departments]

    @jwt_required()
    @swag_from("openapi/PersonsResource_get.yml")
    def get(self):
        """
        Get persons
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/PersonsResource_post.yml")
    def post(self):
        """
        Create person
        """
        return super().post()

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        if relations:
            for relationship in self.get_relations_eager_load():
                query = query.options(orm.selectinload(relationship))

        if permissions.has_admin_permissions():
            if self.get_bool_parameter("with_pass_hash"):
                # Only the password hash is re-added (needed for Kitsu ->
                # Kitsu migration). Never expose the 2FA secrets
                # (totp/email OTP/recovery codes/FIDO) that the full
                # serialize() would otherwise leak.
                persons = []
                for person in query.all():
                    person_dict = person.serialize_safe(relations=relations)
                    person_dict["password"] = serialize_value(person.password)
                    persons.append(person_dict)
                return persons
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

    def get_filterable_column_names(self):
        """
        Mirror what all_entries actually returns, plus the email lookup.
        Without this, filtering answers questions the response refuses to:
        ?daily_salary=320 walks the payroll one value at a time, and phone,
        contract_type or seniority go the same way.
        """
        if permissions.has_admin_permissions():
            return [
                name
                for name in inspect(self.model).all_orm_descriptors.keys()
                if name not in SENSITIVE_FIELDS
            ]
        return MINIMAL_PERSON_FILTER_FIELDS

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
                    "limit": persons_service.get_user_limit(),
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
        check_country(data)
        check_locale(data)
        check_display_date_format(data)
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
            except Exception:
                raise WrongParameterException("Expiration date is not valid.")

        if "email" in data:
            try:
                data["email"] = auth.validate_email(data["email"])
            except auth.EmailNotValidException as e:
                raise WrongParameterException(str(e))

            if not data.get("is_bot", False):
                existing = Person.query.filter(
                    Person.email == data["email"],
                    Person.is_bot.isnot(True),
                ).first()
                if existing is not None:
                    raise WrongParameterException("Email already in use.")

        return data

    def update_data(self, data):
        data = super().update_data(data)
        if "password" in data and data["password"] is not None:
            data["password"] = auth.encrypt_password(data["password"])
        if "email" in data:
            data["email"] = data["email"].strip()
        return data

    def post_creation(self, instance):
        instance_dict = instance.serialize_safe(relations=True)
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
    @swag_from("openapi/PersonResource_get.yml")
    def get(self, instance_id):
        """
        Get person
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/PersonResource_put.yml")
    def put(self, instance_id):
        """
        Update person
        """
        return super().put(instance_id)

    def serialize_update_response(self, instance):
        return instance.serialize_safe()

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
            data.pop("oidc_issuer", None)
            data.pop("oidc_subject", None)
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
        check_country(data)
        check_locale(data)
        check_display_date_format(data)
        if "two_factor_authentication" in data and data[
            "two_factor_authentication"
        ] not in [
            two_factor_authentication
            for two_factor_authentication, _ in TWO_FACTOR_AUTHENTICATION_TYPES
        ]:
            raise WrongParameterException("Invalid two_factor_authentication")

        if "expiration_date" in data and data["expiration_date"] is not None:
            try:
                new_expiration_date = datetime.datetime.strptime(
                    data["expiration_date"], "%Y-%m-%d"
                ).date()
            except Exception:
                raise WrongParameterException("Expiration date is not valid.")

            # Reject a past date only when it actually changes. Re-submitting an
            # already-expired person's own date (e.g. to disable a bot) must
            # keep working, otherwise expired accounts can never be edited.
            current_expiration_date = Person.get(instance_id).expiration_date
            if (
                new_expiration_date != current_expiration_date
                and new_expiration_date < datetime.date.today()
            ):
                raise WrongParameterException(
                    "Expiration date can't be in the past."
                )

        if "email" in data:
            try:
                data["email"] = auth.validate_email(data["email"])
            except auth.EmailNotValidException as e:
                raise WrongParameterException(str(e))

            person = Person.get(instance_id)
            is_bot = data.get("is_bot", person.is_bot)
            if not is_bot:
                existing = Person.query.filter(
                    Person.email == data["email"],
                    Person.id != instance_id,
                    Person.is_bot.isnot(True),
                ).first()
                if existing is not None:
                    raise WrongParameterException("Email already in use.")

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
            and instance_dict.get("is_bot", False) == False
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
        regenerate_token = "expiration_date" in data
        if regenerate_token and data["expiration_date"] is not None:
            # A past date only yields an already-expired token that get_jti()
            # then rejects (500/401). Skip regeneration so an expired bot
            # keeps a stable token and stays editable.
            regenerate_token = (
                datetime.datetime.strptime(
                    data["expiration_date"], "%Y-%m-%d"
                ).date()
                >= datetime.date.today()
            )
        if regenerate_token:
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
    @swag_from("openapi/PersonResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete person
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
