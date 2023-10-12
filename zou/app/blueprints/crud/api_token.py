import datetime

from flask import abort
from flask_jwt_extended import jwt_required
from flask_restful import current_app
from sqlalchemy.exc import StatementError

from zou.app.models.api_token import ApiToken
from zou.app.services import (
    api_tokens_service,
    deletion_service,
)
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.mixin import ArgsMixin

from zou.app.services.exception import (
    DepartmentNotFoundException,
    ApiTokenInProtectedAccounts,
)
from zou.app.models.department import Department

from zou.app import config


class ApiTokensResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ApiToken)
        self.protected_fields += ["jti"]

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        if permissions.has_admin_permissions():
            return [
                api_token.serialize_safe(relations=relations)
                for api_token in query.all()
            ]
        else:
            return [
                api_token.present_minimal(relations=relations)
                for api_token in query.all()
            ]

    def update_data(self, data):
        data = super().update_data(data)
        if "departments" in data:
            try:
                departments = []
                for department_id in data["departments"]:
                    department = Department.get(department_id)
                    if department is not None:
                        departments.append(department)
            except StatementError:
                raise DepartmentNotFoundException()
            data["departments"] = departments
        return data

    def post_creation(self, instance):
        return api_tokens_service.create_access_token_from_instance(instance)

    def check_read_permissions(self):
        return True

    def check_create_permissions(self, data):
        return (
            permissions.check_admin_permissions()
            and permissions.check_person_permissions()
        )


class ApiTokenResource(BaseModelResource, ArgsMixin):
    def __init__(self):
        BaseModelResource.__init__(self, ApiToken)
        self.protected_fields += ["jti", "days_duration"]

    def check_read_permissions(self, instance):
        return True

    def check_update_permissions(self, instance, data):
        return (
            permissions.check_admin_permissions()
            and permissions.check_person_permissions()
        )

    def check_delete_permissions(self, instance):
        return (
            permissions.check_admin_permissions()
            and permissions.check_person_permissions()
        )

    @jwt_required()
    def get(self, instance_id):
        """
        Retrieves the given API token.
        """
        relations = self.get_bool_parameter("relations")

        try:
            instance = self.get_model_or_404(instance_id)
            result = self.serialize_instance(instance, relations=relations)
            self.check_read_permissions(result)
            result = self.clean_get_result(result)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            abort(404)

        return result, 200

    def serialize_instance(self, instance, relations=False):
        if permissions.has_admin_permissions():
            return instance.serialize_safe(relations=relations)
        else:
            return instance.present_minimal(relations=relations)

    def pre_update(self, instance_dict, data):
        if (
            data.get("active") is False
            and instance_dict["email"] in config.PROTECTED_ACCOUNTS
        ):
            raise ApiTokenInProtectedAccounts(
                "Can't set this API token as inactive it's a protected account."
            )
        return data

    def post_update(self, instance_dict):
        api_tokens_service.clear_api_token_cache()
        instance_dict["departments"] = [
            str(department.id) for department in self.instance.departments
        ]
        return instance_dict

    def post_delete(self, instance_dict):
        api_tokens_service.clear_api_token_cache()
        return instance_dict

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        if "departments" in data:
            try:
                departments = []
                for department_id in data["departments"]:
                    department = Department.get(department_id)
                    if department is not None:
                        departments.append(department)
            except StatementError:
                raise DepartmentNotFoundException()
            data["departments"] = departments
        return data

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete an API token corresponding at given ID and return it as a JSON
        object.
        """
        force = self.get_force()
        api_token = self.get_model_or_404(instance_id)
        api_token_dict = api_token.serialize()
        self.check_delete_permissions(api_token_dict)
        self.pre_delete(api_token_dict)
        deletion_service.remove_api_token(instance_id, force=force)
        self.emit_delete_event(api_token_dict)
        self.post_delete(api_token_dict)
        return "", 204
