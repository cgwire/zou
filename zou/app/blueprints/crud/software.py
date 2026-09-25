from flasgger import swag_from
from flask import current_app

from sqlalchemy.exc import StatementError

from zou.app.exceptions import WrongParameterException
from flask_jwt_extended import jwt_required

from zou.app.models.software import Software
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.services import files_service


class SoftwaresResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Software)

    def check_read_permissions(self, options=None):
        return True


class SoftwareResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Software)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from("openapi/SoftwareResource_get.yml")
    def get(self, instance_id):
        """
        Get software
        """
        try:
            software = files_service.get_software(instance_id)
            self.check_read_permissions(software)
            return self.clean_get_result(software)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            raise WrongParameterException("Invalid value.")

    def post_update(self, instance_dict, data):
        files_service.clear_software_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        files_service.clear_software_cache(instance_dict["id"])
        return instance_dict
