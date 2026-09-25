from flasgger import swag_from
from flask import current_app

from sqlalchemy.exc import StatementError

from zou.app.exceptions import WrongParameterException
from flask_jwt_extended import jwt_required

from zou.app.models.output_type import OutputType
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.services import files_service


class OutputTypesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, OutputType)

    def check_read_permissions(self, options=None):
        return True


class OutputTypeResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, OutputType)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from("openapi/OutputTypeResource_get.yml")
    def get(self, instance_id):
        """
        Get output type
        """
        try:
            output_type = files_service.get_output_type(instance_id)
            self.check_read_permissions(output_type)
            return self.clean_get_result(output_type)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            raise WrongParameterException("Invalid value.")

    def post_update(self, instance_dict, data):
        files_service.clear_output_type_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        files_service.clear_output_type_cache(instance_dict["id"])
        return instance_dict
