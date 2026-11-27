from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)
from zou.app.services import (
    entities_service,
    entity_types_service,
    index_service,
    persons_service,
    projects_service,
    shots_service,
)
from zou.app.services.task_types_service import (
    get_task_statuses,
    get_task_type,
)
from zou.app.services.tasks_service import (
    create_task,
    create_tasks,
    get_tasks_for_shot,
)
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class ShotsCsvImportResource(BaseCsvProjectImportResource):
    @swag_from(SPECS["ShotsCsvImportResource_post"])
    def post(self, project_id):
        """
        Import shots csv
        """
        return super().post(project_id)

    def prepare_import(self, project_id):
        self.episodes = {}
        self.sequences = {}
        self.descriptor_fields = self.get_descriptor_field_map(
            project_id, "Shot"
        )
        project = projects_service.get_project(project_id)
        self.is_tv_show = projects_service.is_tv_show(project)
        # Serialized once: a query would run again on every row, and model
        # instances would be expired by every row commit.
        self.task_types_in_project_for_shots = [
            task_type.serialize()
            for task_type in projects_service.get_project_task_types_raw(
                project_id, "Shot"
            )
        ]
        self.task_statuses = {
            status["id"]: [status[n].lower() for n in ("name", "short_name")]
            for status in get_task_statuses()
        }
        self.current_user_id = persons_service.get_current_user()["id"]

    def create_and_update_tasks(
        self, tasks_update, entity, shot_creation=False
    ):
        if tasks_update:
            if shot_creation:
                tasks_map = {
                    task_type["id"]: create_task(task_type, entity.serialize())
                    for task_type in self.task_types_in_project_for_shots
                }
            else:
                tasks_map = {
                    task["task_type_id"]: task
                    for task in get_tasks_for_shot(str(entity.id))
                }

            for task_update in tasks_update:
                if task_update["task_type_id"] not in tasks_map:
                    tasks_map[task_update["task_type_id"]] = create_task(
                        get_task_type(task_update["task_type_id"]),
                        entity.serialize(),
                    )
                task = tasks_map[task_update["task_type_id"]]
                self.apply_task_update(task, task_update)
        elif shot_creation:
            self.created_shots.append(entity.serialize())

    def import_row(self, row, project_id):
        # An empty cell would create a sequence or a shot named "", from a
        # spreadsheet total row for instance.
        required_columns = ["Sequence", "Name"]
        if self.is_tv_show:
            required_columns.insert(0, "Episode")
        for column in required_columns:
            if not (row[column] or "").strip():
                raise RowException(f"{column} cannot be empty")

        if self.is_tv_show:
            episode_name = row["Episode"]
        sequence_name = row["Sequence"]
        shot_name = row["Name"]

        if self.is_tv_show:
            episode_key = f"{project_id}-{episode_name}"
            if episode_key not in self.episodes:
                self.episodes[episode_key] = self.get_or_create_episode(
                    project_id, episode_name
                )

            sequence_key = f"{project_id}-{episode_name}-{sequence_name}"
        else:
            sequence_key = f"{project_id}-{sequence_name}"

        if sequence_key not in self.sequences:
            if self.is_tv_show:
                episode = self.episodes[episode_key]
                self.sequences[sequence_key] = shots_service.create_sequence(
                    project_id,
                    episode["id"],
                    sequence_name,
                    created_by=self.current_user_id,
                )
            else:
                self.sequences[sequence_key] = shots_service.create_sequence(
                    project_id,
                    None,
                    sequence_name,
                    created_by=self.current_user_id,
                )
        sequence_id = self.get_id_from_cache(self.sequences, sequence_key)

        shot_type = entity_types_service.get_shot_type()

        shot_values = {
            "name": shot_name,
            "project_id": project_id,
            "parent_id": sequence_id,
            "entity_type_id": shot_type["id"],
        }

        entity = entities_service.find_entity_raw(**shot_values)

        shot_new_values = {}

        description = row.get("Description", None)
        if description is not None:
            shot_new_values["description"] = description

        nb_frames = row.get("Nb Frames", None) or row.get("Frames", None)
        if nb_frames is not None and nb_frames != "":
            try:
                shot_new_values["nb_frames"] = int(nb_frames)
            except (ValueError, TypeError):
                raise RowException(
                    f"nb_frames must be an integer, got '{nb_frames}'"
                )

        if entity is None or not entity.data:
            shot_new_values["data"] = {}
        else:
            shot_new_values["data"] = entity.data.copy()

        frame_in = row.get("Frame In", None) or row.get("In", None)
        if frame_in is not None and frame_in != "":
            try:
                shot_new_values["data"]["frame_in"] = int(frame_in)
            except (ValueError, TypeError):
                raise RowException(
                    f"frame_in must be an integer, got '{frame_in}'"
                )

        frame_out = row.get("Frame Out", None) or row.get("Out", None)
        if frame_out is not None and frame_out != "":
            try:
                shot_new_values["data"]["frame_out"] = int(frame_out)
            except (ValueError, TypeError):
                raise RowException(
                    f"frame_out must be an integer, got '{frame_out}'"
                )

        # Keep the frame count consistent with an imported frame range when
        # the CSV doesn't provide it explicitly.
        if "nb_frames" not in shot_new_values:
            try:
                frame_in_value = int(shot_new_values["data"]["frame_in"])
                frame_out_value = int(shot_new_values["data"]["frame_out"])
                if frame_out_value > frame_in_value:
                    shot_new_values["nb_frames"] = (
                        frame_out_value - frame_in_value + 1
                    )
            except (KeyError, TypeError, ValueError):
                pass

        fps = row.get("FPS", None)
        if fps is not None:
            shot_new_values["data"]["fps"] = fps

        resolution = row.get("Resolution", None)
        if resolution is not None:
            shot_new_values["data"]["resolution"] = resolution

        shot_new_values["data"] = self.get_descriptor_values(
            row, shot_new_values["data"]
        )

        tasks_update = self.get_tasks_update(
            row, self.task_types_in_project_for_shots
        )

        if entity is None:
            shot = shots_service.create_shot(
                project_id,
                sequence_id,
                shot_name,
                data=shot_new_values.get("data"),
                nb_frames=shot_new_values.get("nb_frames", 0),
                description=shot_new_values.get("description"),
                created_by=self.current_user_id,
                index=False,
            )
            entity = entities_service.get_entity_raw(shot["id"])
            self.shot_ids_to_index.append(entity.id)

            self.create_and_update_tasks(
                tasks_update, entity, shot_creation=True
            )

        elif self.is_update:
            shots_service.update_shot(
                str(entity.id), shot_new_values, index=False
            )
            self.shot_ids_to_index.append(entity.id)

            self.create_and_update_tasks(
                tasks_update, entity, shot_creation=False
            )

        return entity.serialize()

    def run_import(self, file_path, project_id):
        # Set before the import: prepare_import can fail before it does.
        self.created_shots = []
        self.task_types_in_project_for_shots = []
        self.shot_ids_to_index = []
        try:
            return super().run_import(file_path, project_id)
        finally:
            # Indexed at the end, without waiting for the indexer on every
            # row, the rows committed before a failing one included.
            index_service.index_shots(self.shot_ids_to_index)
            # The shots created before a failing line stay imported, and a
            # new import would not create their tasks: they get them here.
            for task_type in self.task_types_in_project_for_shots:
                create_tasks(task_type, self.created_shots)
