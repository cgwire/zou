from flask import request, abort
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import StatementError

from zou.app.models.data_import_error import DataImportError


class ShotgunImportErrorsResource(Resource):
    def __init__(self):
        Resource.__init__(self)

    @jwt_required()
    def get(self):
        """
        Import shotgun error resource.
        ---
        tags:
          - Import
        responses:
            200:
                description: Resource imported
        """
        criterions = {"source": "shotgun"}
        import_errors = DataImportError.query.filter_by(**criterions).all()
        return DataImportError.serialize_list(import_errors)

    @jwt_required()
    def post(self):
        """
        Serialize shotgun error resource.
        ---
        tags:
          - Import
        responses:
            200:
                description: Resource serialized
        """
        error = DataImportError(event_data=request.json, source="shotgun")
        error.save()
        return error.serialize(), 201


class ShotgunImportErrorResource(Resource):
    def __init__(self):
        Resource.__init__(self)

    @jwt_required()
    def delete(self, error_id):
        """
        Delete error.
        ---
        tags:
          - Import
        parameters:
          - in: path
            name: error_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Error deleted
            404:
                description: Error non-existant or Statement error
        """
        try:
            error = DataImportError.get(error_id)
        except StatementError:
            abort(404)

        if error is None:
            abort(404)
        error.delete()

        return {"deletion_success": True}, 204
