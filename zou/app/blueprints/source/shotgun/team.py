from flasgger import swag_from
from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app import db
from zou.app.models.project import Project
from zou.app.models.project import ProjectPersonLink
from zou.app.models.person import Person

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)


class ImportShotgunProjectConnectionsResource(BaseImportShotgunResource):
    def __init__(self):
        BaseImportShotgunResource.__init__(self)

    @jwt_required()
    @swag_from("openapi/ImportShotgunProjectConnectionsResource_post.yml")
    def post(self):
        """
        Import shotgun project connections
        """
        return super().post()

    def prepare_import(self):
        pass

    def extract_data(self, sg_project_user_connection):
        sg_project = sg_project_user_connection["project"]
        sg_user = sg_project_user_connection["user"]

        data = {
            "shotgun_id": sg_project_user_connection["id"],
            "project_shotgun_id": sg_project["id"],
            "person_shotgun_id": sg_user["id"],
        }
        return data

    def import_entry(self, data):
        project_person_link = ProjectPersonLink.query.filter(
            ProjectPersonLink.shotgun_id == data["shotgun_id"]
        ).first()

        if project_person_link is None:
            project = Project.get_by(shotgun_id=data["project_shotgun_id"])
            person = Person.get_by(shotgun_id=data["person_shotgun_id"])

            if project is not None and person is not None:
                project.team.append(person)
                project.save()
                # Record the Shotgun id on the link so the next import and
                # the removal route find it instead of duplicating it.
                link = ProjectPersonLink.query.filter_by(
                    project_id=project.id, person_id=person.id
                ).first()
                link.shotgun_id = data["shotgun_id"]
                db.session.commit()
                current_app.logger.info(
                    f"Project Person Link created: {project}"
                )
        else:
            project = Project.get(project_person_link.project_id)
            current_app.logger.info(
                f"Project Person Link already there: {project}"
            )

        return project


class ImportRemoveShotgunProjectConnectionResource(
    ImportRemoveShotgunBaseResource
):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(self, ProjectPersonLink)

    def get_instance(self, sg_model):
        # ProjectPersonLink is a bare link table without BaseMixin, so the
        # generic get_by lookup does not exist on it.
        return ProjectPersonLink.query.filter_by(
            shotgun_id=sg_model["id"]
        ).first()

    def delete_instance(self, instance):
        db.session.delete(instance)
        db.session.commit()
        return True

    @jwt_required()
    @swag_from("openapi/ImportRemoveShotgunProjectConnectionResource_post.yml")
    def post(self):
        """
        Remove shotgun project connection
        """
        return super().post()
