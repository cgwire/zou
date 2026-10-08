from flasgger import swag_from
from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)

from zou.app.services import (
    assets_service,
    entities_service,
    index_service,
    projects_service,
    shots_service,
    persons_service,
    comments_service,
    tasks_service,
    entity_types_service,
    task_types_service,
)
from zou.app.exceptions import WrongParameterException


class AssetsCsvImportResource(BaseCsvProjectImportResource):
    @swag_from("openapi/AssetsCsvImportResource_post.yml")
    def post(self, project_id):
        """
        Import assets csv
        """
        return super().post(project_id)

    def prepare_import(self, project_id):
        self.episodes = {}
        self.entity_types = {}
        self.descriptor_fields = self.get_descriptor_field_map(
            project_id, "Asset"
        )
        project = projects_service.get_project(project_id, relations=True)
        self.is_tv_show = projects_service.is_tv_show(project)
        if self.is_tv_show:
            episodes = shots_service.get_episodes_for_project(project_id)
            self.episodes = {
                episode["name"]: episode["id"] for episode in episodes
            }
        asset_type_ids_in_project = set(project["asset_types"])
        self.asset_types_in_project = {
            asset_type["name"].lower(): asset_type["id"]
            for asset_type in entity_types_service.get_asset_types()
            if asset_type["id"] in asset_type_ids_in_project
        }
        task_types = projects_service.get_project_task_types_raw(
            project_id, "Asset"
        )
        # Serialized: model instances would be expired by every row commit,
        # and read again from the database on every row.
        self.task_types_in_project_for_assets = [
            task_type.serialize() for task_type in task_types
        ]
        self.task_type_ids_in_project_for_assets = [
            task_type["id"]
            for task_type in self.task_types_in_project_for_assets
        ]
        self.task_types_for_asset_type = {}
        self.task_statuses = {
            status["id"]: [status[n].lower() for n in ("name", "short_name")]
            for status in task_types_service.get_task_statuses()
        }
        self.current_user_id = persons_service.get_current_user()["id"]
        self.task_types_for_ready_for_map = {
            task_type.name: str(task_type.id)
            for task_type in projects_service.get_project_task_types_raw(
                project_id, "Shot"
            )
        }

    def get_tasks_update(self, row):
        tasks_update = []
        for task_type in self.task_types_in_project_for_assets:
            task_status_name = row.get(task_type["name"], None)
            task_status_id = None
            if task_status_name not in [None, ""]:
                for status_id, status_names in self.task_statuses.items():
                    if task_status_name.lower() in status_names:
                        task_status_id = status_id
                        break
                if task_status_id is None:
                    raise RowException(
                        f"Task status not found for {task_status_name}"
                    )

            task_comment_text = row.get(f"{task_type['name']} comment", None)
            task_assignees = self.get_assignation_ids(row, task_type["name"])

            if (
                task_status_id is not None
                or task_comment_text not in [None, ""]
                or task_assignees
            ):
                tasks_update.append(
                    {
                        "task_type_id": task_type["id"],
                        "task_status_id": task_status_id,
                        "comment": task_comment_text,
                        "assignees": task_assignees,
                    }
                )

        return tasks_update

    def create_missing_tasks(self, entity, tasks_map=None):
        """
        Create the workflow tasks the entity does not have yet, each at the
        default status, and return the map of task type id to task. This
        runs for every row, including the ones whose task columns are all
        empty: those are exactly the tasks the import must initialize.
        """
        if tasks_map is None:
            tasks_map = {
                task["task_type_id"]: task
                for task in tasks_service.get_tasks_for_asset(str(entity.id))
            }
        entity_dict = entity.serialize()
        for task_type_id in self.get_task_types_for_asset_type(
            entity.entity_type_id
        ):
            if task_type_id not in tasks_map:
                task = tasks_service.create_task(
                    {"id": task_type_id}, entity_dict
                )
                if task is not None:
                    tasks_map[task_type_id] = task
        return tasks_map

    def create_and_update_tasks(
        self, tasks_update, entity, asset_creation=False
    ):
        """
        Create the workflow tasks of the entity, then apply the statuses and
        comments read from the row.
        """
        tasks_map = self.create_missing_tasks(
            entity, {} if asset_creation else None
        )

        for task_update in tasks_update:
            task_type_id = task_update["task_type_id"]
            if task_type_id not in tasks_map:
                # The column names a task type outside the asset type
                # workflow: the explicit status still creates its task.
                task = tasks_service.create_task(
                    task_types_service.get_task_type(task_type_id),
                    entity.serialize(),
                )
                if task is None:
                    continue
                tasks_map[task_type_id] = task
            task = tasks_map[task_type_id]
            already_assigned = set(task.get("assignees") or [])
            for person_id in task_update["assignees"]:
                if person_id not in already_assigned:
                    tasks_service.assign_task(
                        task["id"], person_id, self.current_user_id
                    )
            # The status guard needs the explicit None check: an entry
            # created for its assignations alone must not post an empty
            # comment at the default status.
            if task_update["comment"] is not None or (
                task_update["task_status_id"] is not None
                and task_update["task_status_id"] != task["task_status_id"]
            ):
                try:
                    comments_service.create_comment(
                        self.current_user_id,
                        task["id"],
                        task_update["task_status_id"]
                        or task["task_status_id"],
                        task_update["comment"] or "",
                        [],
                        {},
                        "",
                    )
                except WrongParameterException:
                    pass

    def import_row(self, row, project_id):
        asset_name = row["Name"]
        entity_type_name = row["Type"]
        if entity_type_name is None or not entity_type_name.strip():
            # An empty cell used to create an asset type named "" that
            # every later empty row then reused.
            raise RowException("An asset type is required in the Type column")
        # An empty cell reads as "" with DictReader: it means no episode,
        # not an episode named "".
        episode_name = (row.get("Episode") or "").strip() or None
        episode_id = None

        if self.is_tv_show:
            if episode_name not in [None, "MP"] + list(self.episodes.keys()):
                self.episodes[episode_name] = shots_service.create_episode(
                    project_id, episode_name, created_by=self.current_user_id
                )["id"]
            episode_id = self.episodes.get(episode_name, None)
        elif episode_name is not None:
            raise RowException(
                "An episode column is present for a production that isn't a TV Show"
            )

        if self.asset_types_in_project:
            # An empty project asset type list means every type is allowed,
            # which is how Kitsu reads it too. A non-empty one is a closed
            # list, so the import never creates a type here: an unknown
            # name is a typo, not a new type. A type that exists but is
            # missing from the list is added to it, otherwise the imported
            # assets would be absent from the production filters and from
            # the schedule.
            entity_type_id = self.asset_types_in_project.get(
                entity_type_name.lower()
            )
            if entity_type_id is None:
                asset_type = entity_types_service.find_asset_type_by_name(
                    entity_type_name
                )
                if asset_type is None:
                    raise RowException(
                        f"Asset type {entity_type_name} is not configured "
                        "for this project"
                    )
                entity_type_id = str(asset_type.id)
                projects_service.add_asset_type_setting(
                    project_id, entity_type_id
                )
                self.asset_types_in_project[entity_type_name.lower()] = (
                    entity_type_id
                )
        else:
            self.add_to_cache_if_absent(
                self.entity_types,
                entity_types_service.get_or_create_asset_type,
                entity_type_name,
            )
            entity_type_id = self.get_id_from_cache(
                self.entity_types, entity_type_name
            )

        asset_values = {
            "name": asset_name,
            "project_id": project_id,
            "entity_type_id": entity_type_id,
            "source_id": episode_id,
        }

        # The entity table is polymorphic: without the type, a sequence or
        # an episode with the same name would be taken for the asset and
        # re-typed on update.
        entity = entities_service.find_entity_raw(
            name=asset_values["name"],
            project_id=asset_values["project_id"],
            entity_type_id=entity_type_id,
        )

        asset_new_values = {}

        description = row.get("Description", None)
        if description is not None:
            asset_new_values["description"] = description

        data = {} if entity is None else entity.data

        resolution = row.get("Resolution", None)
        if resolution is not None:
            data = {**(data or {}), "resolution": resolution}

        asset_new_values["data"] = self.get_descriptor_values(row, data)

        ready_for = row.get("Ready for", None)
        if ready_for is not None:
            if ready_for == "":
                asset_new_values["ready_for"] = None
            else:
                try:
                    asset_new_values["ready_for"] = (
                        self.task_types_for_ready_for_map[ready_for]
                    )
                except KeyError:
                    raise RowException(f"Task type not found for {ready_for}")

        tasks_update = self.get_tasks_update(row)

        if entity is None:
            asset = assets_service.create_asset(
                project_id,
                entity_type_id,
                asset_name,
                asset_new_values.get("description"),
                asset_new_values["data"],
                source_id=episode_id,
                created_by=self.current_user_id,
                ready_for=asset_new_values.get("ready_for"),
                index=False,
            )
            entity = entities_service.get_entity_raw(asset["id"])
            self.asset_ids_to_index.append(entity.id)

            self.create_and_update_tasks(
                tasks_update, entity, asset_creation=True
            )

        elif self.is_update:
            self.asset_ids_to_index.append(entity.id)
            assets_service.update_asset(
                str(entity.id),
                {**asset_values, **asset_new_values},
                index=False,
            )

            self.create_and_update_tasks(
                tasks_update, entity, asset_creation=False
            )

        else:
            # The asset is left untouched, but a re-import is the documented
            # way to repair a production whose assets miss their tasks.
            self.create_missing_tasks(entity)

        return entity.serialize()

    def run_import(self, file_path, project_id):
        self.asset_ids_to_index = []
        try:
            return super().run_import(file_path, project_id)
        finally:
            # Indexed at the end, without waiting for the indexer on every
            # row. The rows committed before a failing one stay imported:
            # they are indexed too.
            index_service.index_assets(self.asset_ids_to_index)

    def get_task_types_for_asset_type(self, asset_type_id):
        """
        Return the ids of the task types to create for a given asset type:
        the ones enabled on the project, narrowed by the asset type workflow
        when it defines one. Memoized on the resource instance only: the
        result depends on the project being imported, which a cache key
        built from the arguments alone cannot express.
        """
        asset_type_id = str(asset_type_id)
        if asset_type_id not in self.task_types_for_asset_type:
            task_type_ids = self.task_type_ids_in_project_for_assets
            asset_type = entity_types_service.get_asset_type(asset_type_id)
            type_task_type_ids = asset_type["task_types"]
            if len(type_task_type_ids) > 0:
                type_task_types_map = {
                    task_type_id: True for task_type_id in type_task_type_ids
                }
                task_type_ids = [
                    task_type_id
                    for task_type_id in task_type_ids
                    if task_type_id in type_task_types_map
                ]
            self.task_types_for_asset_type[asset_type_id] = task_type_ids
        return self.task_types_for_asset_type[asset_type_id]
