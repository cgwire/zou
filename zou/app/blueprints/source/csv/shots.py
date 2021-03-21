from zou.app.blueprints.source.csv.base import BaseCsvProjectImportResource

from zou.app.models.entity import Entity
from zou.app.services import shots_service, projects_service
from zou.app.utils import events


class ShotsCsvImportResource(BaseCsvProjectImportResource):
    def prepare_import(self, project_id):
        self.episodes = {}
        self.sequences = {}
        self.descriptor_fields = self.get_descriptor_field_map(
            project_id, "Shot"
        )
        project = projects_service.get_project(project_id)
        self.is_tv_show = projects_service.is_tv_show(project)

    def import_row(self, row, project_id):
        if self.is_tv_show:
            episode_name = row["Episode"]
        sequence_name = row["Sequence"]
        shot_name = row["Name"]
        description = row.get("Description", "")
        nb_frames = row.get("Nb Frames", None) or row.get("Frames", None)
        data = {
            "frame_in": row.get("Frame In", None) or row.get("In", None),
            "frame_out": row.get("Frame Out", None) or row.get("Out", None),
            "fps": row.get("FPS", None),
        }

        if self.is_tv_show:
            episode_key = "%s-%s" % (project_id, episode_name)
            if episode_key not in self.episodes:
                self.episodes[
                    episode_key
                ] = shots_service.get_or_create_episode(
                    project_id, episode_name
                )

            sequence_key = "%s-%s-%s" % (
                project_id,
                episode_name,
                sequence_name,
            )
        else:
            sequence_key = "%s-%s" % (project_id, sequence_name)

        if sequence_key not in self.sequences:
            if self.is_tv_show:
                episode = self.episodes[episode_key]
                self.sequences[
                    sequence_key
                ] = shots_service.get_or_create_sequence(
                    project_id, episode["id"], sequence_name
                )
            else:
                self.sequences[
                    sequence_key
                ] = shots_service.get_or_create_sequence(
                    project_id, None, sequence_name
                )
        sequence_id = self.get_id_from_cache(self.sequences, sequence_key)

        shot_type = shots_service.get_shot_type()
        entity = Entity.get_by(
            name=shot_name,
            project_id=project_id,
            parent_id=sequence_id,
            entity_type_id=shot_type["id"],
        )

        for name, field_name in self.descriptor_fields.items():
            if name in row:
                data[field_name] = row[name]
            elif (
                entity is not None
                and entity.data is not None
                and field_name in entity.data
            ):
                data[field_name] = entity.data[field_name]

        if entity is None:
            if nb_frames is None or len(nb_frames) == 0:
                entity = Entity.create(
                    name=shot_name,
                    description=description,
                    project_id=project_id,
                    parent_id=sequence_id,
                    entity_type_id=shot_type["id"],
                    data=data,
                )
            else:
                entity = Entity.create(
                    name=shot_name,
                    description=description,
                    project_id=project_id,
                    parent_id=sequence_id,
                    entity_type_id=shot_type["id"],
                    nb_frames=nb_frames,
                    data=data,
                )
            events.emit(
                "shot:new", {"shot_id": str(entity.id)}, project_id=project_id
            )

        elif self.is_update:
            entity.update(
                {
                    "description": description,
                    "nb_frames": nb_frames,
                    "data": data,
                }
            )
            events.emit(
                "shot:update",
                {"shot_id": str(entity.id)},
                project_id=project_id,
            )

        return entity.serialize()
