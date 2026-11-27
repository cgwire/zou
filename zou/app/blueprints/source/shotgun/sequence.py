from flask import current_app
from flask_jwt_extended import jwt_required

from zou.app.blueprints.source.shotgun.base import (
    BaseImportShotgunResource,
    ImportRemoveShotgunBaseResource,
)
from zou.app.blueprints.source.shotgun.exception import (
    ShotgunEntryImportFailed,
)
from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.services import (
    cascade_deletion_service,
    entity_types_service,
    persons_service,
)
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class ImportShotgunSequencesResource(BaseImportShotgunResource):
    @jwt_required()
    @swag_from(SPECS["ImportShotgunSequencesResource_post"])
    def post(self):
        """
        Import shotgun sequences
        """
        return super().post()

    def prepare_import(self):
        self.sequence_type = entity_types_service.get_sequence_type()
        self.project_map = Project.get_id_map(field="name")
        self.current_user_id = persons_service.get_current_user()["id"]

    def get_episode(self, sg_sequence):
        # A None ID would match the episodes created in Kitsu.
        episode_sg_id = (sg_sequence.get("episode") or {}).get("id")
        if episode_sg_id is None:
            return None
        return self.get_episode_id(episode_sg_id)

    def extract_data(self, sg_sequence):
        project_id = self.get_project(sg_sequence)
        episode_id = self.get_episode(sg_sequence)
        if project_id is None:
            raise ShotgunEntryImportFailed
        return {
            "name": sg_sequence["code"],
            "shotgun_id": sg_sequence["id"],
            "description": sg_sequence["description"],
            "project_id": project_id,
            "parent_id": episode_id,
            "entity_type_id": self.sequence_type["id"],
        }

    def get_project(self, sg_sequence):
        project_id = None
        if sg_sequence["project"] is not None:
            project_name = sg_sequence["project"]["name"]
            project_id = self.project_map.get(project_name, None)
        return project_id

    def import_entry(self, data):
        sequence = Entity.get_by(
            shotgun_id=data["shotgun_id"],
            entity_type_id=self.sequence_type["id"],
        )

        similar_sequence = Entity.get_by(
            name=data["name"],
            parent_id=data["parent_id"],
            project_id=data["project_id"],
            entity_type_id=self.sequence_type["id"],
        )

        if sequence is None and similar_sequence is None:
            sequence = Entity.create(**data, created_by=self.current_user_id)
            current_app.logger.info(f"Sequence created: {sequence}")

        elif sequence is not None:
            if similar_sequence is None:
                sequence.update(data)
                sequence.save()
            else:
                sequence.update(
                    {
                        "description": data["description"],
                        "shotgun_id": data["shotgun_id"],
                    }
                )
                sequence.save()
            current_app.logger.info(f"Sequence updated: {sequence}")

        return sequence


class ImportRemoveShotgunSequenceResource(ImportRemoveShotgunBaseResource):
    def __init__(self):
        ImportRemoveShotgunBaseResource.__init__(
            self,
            Entity,
            lambda sequence: cascade_deletion_service.remove_sequence(
                str(sequence.id)
            ),
            entity_type_id=entity_types_service.get_sequence_type()["id"],
        )

    @jwt_required()
    @swag_from(SPECS["ImportRemoveShotgunSequenceResource_post"])
    def post(self):
        """
        Remove shotgun sequence
        """
        return super().post()
