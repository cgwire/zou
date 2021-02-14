from flask import abort
from flask_jwt_extended import jwt_required

from flask_restful import Resource
from zou.app.utils import csv_utils, permissions


class BaseCsvExport(Resource):
    def __init__(self):
        Resource.__init__(self)
        self.file_name = "export"

    def check_permissions(self):
        permissions.check_manager_permissions()
        return True

    def prepare_import(self):
        pass

    @jwt_required
    def get(self):
        self.prepare_import()
        try:
            self.check_permissions()
            csv_content = []
            csv_content.append(self.build_headers())
            results = self.build_query().all()
            for result in results:
                csv_content.append(self.build_row(result))
        except permissions.PermissionDenied:
            abort(403)

        return csv_utils.build_csv_response(
            csv_content, file_name=self.file_name
        )
