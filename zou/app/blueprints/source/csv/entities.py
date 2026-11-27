from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)
from zou.app.services import (
    entities_service,
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
)


class BaseCsvEntityImportResource(BaseCsvProjectImportResource):
    """
    Base resource for the import of the entities that have a name, a
    description, metadata and tasks: edits, sequences and episodes. In a TV
    show, an edit or a sequence is under an episode. A subclass gives its
    entity type. It also tells how to create and update an entity, and how to
    list its tasks.
    """

    entity_type_name = None
    # In a TV show, an entity of this type is under an episode.
    has_episode = True
    # A line of a TV show must name that episode.
    is_episode_required = False

    def get_entity_type(self):
        raise NotImplementedError

    def create_entity(self, project_id, name, parent_id, values):
        raise NotImplementedError

    def update_entity(self, entity_id, values):
        raise NotImplementedError

    def get_tasks(self, entity_id):
        """
        Return the tasks of the entity with their assignee IDs. Thus an import
        does not assign again the people that a task already has.
        """
        raise NotImplementedError

    def get_extra_values(self, row):
        """
        Return the values of the columns that only this entity type has. The
        import uses them to create or update an entity.
        """
        return {}

    def prepare_import(self, project_id):
        self.descriptor_fields = self.get_descriptor_field_map(
            project_id, self.entity_type_name
        )
        project = projects_service.get_project(project_id)
        self.is_tv_show = projects_service.is_tv_show(project)
        self.episodes = {}
        if self.has_episode and self.is_tv_show:
            self.episodes = {
                episode["name"]: episode["id"]
                for episode in shots_service.get_episodes_for_project(
                    project_id
                )
            }
        self.entity_type_id = self.get_entity_type()["id"]
        # Serialized once: otherwise a query would run again for each row, and
        # each row commit would expire the active records.
        self.task_types = [
            task_type.serialize()
            for task_type in projects_service.get_project_task_types_raw(
                project_id, self.entity_type_name
            )
        ]
        self.task_statuses = {
            status["id"]: [status[n].lower() for n in ("name", "short_name")]
            for status in get_task_statuses()
        }
        self.current_user_id = persons_service.get_current_user()["id"]

    def create_and_update_tasks(self, tasks_update, entity, creation=False):
        """
        Apply the task changes of the row:
        - create the missing tasks,
        - add the assignees,
        - post a comment for a new status or a comment.
        On creation, create a task for each task type of the project. If the
        row has no task change, do nothing: run_import creates these tasks.
        """
        if tasks_update:
            if creation:
                tasks_map = {
                    task_type["id"]: create_task(task_type, entity.serialize())
                    for task_type in self.task_types
                }
            else:
                tasks_map = {
                    task["task_type_id"]: task
                    for task in self.get_tasks(str(entity.id))
                }

            for task_update in tasks_update:
                if task_update["task_type_id"] not in tasks_map:
                    tasks_map[task_update["task_type_id"]] = create_task(
                        get_task_type(task_update["task_type_id"]),
                        entity.serialize(),
                    )
                task = tasks_map[task_update["task_type_id"]]
                self.apply_task_update(task, task_update)
        elif creation:
            self.created_entities.append(entity.serialize())

    def get_episode_name(self, row):
        """
        Return the name of the episode that a line gives, or None for no
        episode. Check the name against the production.
        """
        # An empty cell reads as "" with DictReader: it means no episode,
        # not an episode named "".
        episode_name = (row.get("Episode") or "").strip() or None
        if not self.is_tv_show:
            if episode_name is not None:
                raise RowException(
                    "The Episode cell must be empty outside a TV show"
                )
            return None
        if episode_name is None and self.is_episode_required:
            raise RowException("Episode cannot be empty")
        return episode_name

    def get_episode_id(self, episode_name, project_id):
        """
        Return the ID of the episode with the given name. If the production
        does not have it yet, create it.
        """
        if episode_name not in self.episodes:
            self.episodes[episode_name] = self.get_or_create_episode(
                project_id, episode_name
            )["id"]
        return self.episodes[episode_name]

    def import_row(self, row, project_id):
        name = row["Name"]
        if not (name or "").strip():
            raise RowException("Name cannot be empty")
        episode_name = None
        if self.has_episode:
            episode_name = self.get_episode_name(row)

        # An episode the production does not have yet holds no entity.
        entity = None
        if episode_name is None or episode_name in self.episodes:
            entity = entities_service.find_entity_raw(
                name=name,
                project_id=project_id,
                entity_type_id=self.entity_type_id,
                parent_id=self.episodes.get(episode_name),
            )
        # Without update=true, the line of an entity that exists changes
        # nothing. The import does not read it either, thus an assignee renamed
        # after the export does not stop the import there.
        if entity is not None and not self.is_update:
            return entity.serialize()

        values = {}
        description = row.get("Description", None)
        if description is not None:
            values["description"] = description
        values["data"] = self.get_descriptor_values(
            row, {} if entity is None else entity.data
        )
        values.update(self.get_extra_values(row))

        tasks_update = self.get_tasks_update(row, self.task_types)

        # Create it after the import reads the full line: if the import refuses
        # the line, no episode stays behind.
        if entity is None:
            parent_id = None
            if episode_name is not None:
                parent_id = self.get_episode_id(episode_name, project_id)
            created = self.create_entity(project_id, name, parent_id, values)
            entity = entities_service.get_entity_raw(created["id"])
            self.create_and_update_tasks(tasks_update, entity, creation=True)
        else:
            self.update_entity(str(entity.id), values)
            self.create_and_update_tasks(tasks_update, entity)

        return entity.serialize()

    def run_import(self, file_path, project_id):
        # Set before the import: prepare_import can fail before it does.
        self.created_entities = []
        self.task_types = []
        try:
            return super().run_import(file_path, project_id)
        finally:
            # The entities created before a failing line stay imported, and
            # a new import would not create their tasks: they get them here.
            for task_type in self.task_types:
                create_tasks(task_type, self.created_entities)
