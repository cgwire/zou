from flasgger import swag_from
from flask import abort
from flask_jwt_extended import jwt_required

from flask.views import MethodView
from zou.app.utils import csv_utils, permissions


class BaseCsvExport(MethodView):
    def __init__(self):
        MethodView.__init__(self)
        self.file_name = "export"

    def check_permissions(self):
        permissions.check_manager_permissions()
        return True

    def prepare_import(self):
        pass

    @jwt_required()
    @swag_from("openapi/BaseCsvExport_get.yml")
    def get(self):
        """
        Export csv
        """
        self.prepare_import()
        try:
            self.check_permissions()
        except permissions.PermissionDenied:
            raise

        def row_generator():
            yield self.build_headers()
            for result in self.build_query().yield_per(500):
                yield self.build_row(result)

        return csv_utils.build_csv_stream_response(
            row_generator(), file_name=self.file_name
        )
