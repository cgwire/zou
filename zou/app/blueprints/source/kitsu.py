from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.mixin import ArgsMixin
from zou.app.utils import fields, permissions


class BaseImportKitsuResource(Resource, ArgsMixin):

    def __init__(self, model):
        Resource.__init__(self)
        self.model = model

    @jwt_required
    @permissions.require_admin
    def post(self):
        kitsu_entries = request.json
        instances = []
        for entry in kitsu_entries:
            if self.pre_check_entry():
                instance = self.model.create_from_import(entry)
                instances.append(instance)
        return fields.serialize_models(instances)

    def pre_check_entry(self):
        return True


class ImportKitsuCommentsResource(BaseImportKitsuResource):

    def __init__(self):
        BaseImportKitsuResource.__init__(self, Entity)


class ImportKitsuEntitiesResource(BaseImportKitsuResource):

    def __init__(self):
        BaseImportKitsuResource.__init__(self, Entity)


class ImportKitsuProjectsResource(BaseImportKitsuResource):

    def __init__(self):
        BaseImportKitsuResource.__init__(self, Project)


class ImportKitsuTasksResource(BaseImportKitsuResource):

    def __init__(self):
        BaseImportKitsuResource.__init__(self, Task)
