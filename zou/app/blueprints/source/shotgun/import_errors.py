from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import StatementError
from werkzeug.exceptions import NotFound

from zou.app.models.data_import_error import DataImportError
from zou.app.utils import permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class ShotgunImportErrorsResource(MethodView):

    def __init__(self):
        MethodView.__init__(self)

    @jwt_required()
    @swag_from(SPECS["ShotgunImportErrorsResource_get"])
    def get(self):
        """
        Get shotgun import errors
        """
        permissions.check_admin_permissions()
        criterions = {"source": "shotgun"}
        import_errors = DataImportError.query.filter_by(**criterions).all()
        return DataImportError.serialize_list(import_errors)

    @jwt_required()
    @swag_from(SPECS["ShotgunImportErrorsResource_post"])
    def post(self):
        """
        Create shotgun import error
        """
        permissions.check_admin_permissions()
        error = DataImportError(event_data=request.json, source="shotgun")
        error.save()
        return error.serialize(), 201


class ShotgunImportErrorResource(MethodView):
    def __init__(self):
        MethodView.__init__(self)

    @jwt_required()
    @swag_from(SPECS["ShotgunImportErrorResource_delete"])
    def delete(self, error_id):
        """
        Delete shotgun import error
        """
        permissions.check_admin_permissions()
        try:
            error = DataImportError.get(error_id)
        except StatementError:
            raise NotFound

        if error is None:
            raise NotFound
        error.delete()

        return "", 204
