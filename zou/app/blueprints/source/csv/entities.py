from zou.app.blueprints.source.csv.base import (
    BaseCsvProjectImportResource,
    RowException,
)
from zou.app.exceptions import WrongParameterException
from zou.app.services import (
    entities_service,
    persons_service,
    projects_service,
    shots_service,
)
from zou.app.services.comments_service import create_comment
from zou.app.services.task_types_service import (
    get_task_statuses,
    get_task_type,
)
from zou.app.services.tasks_service import (
    assign_task,
    create_task,
    create_tasks,
)


class BaseCsvEntityImportResource(BaseCsvProjectImportResource):
    """
    Import of the entities that carry a name, a description, metadata, and
    tasks: edits, sequences, and episodes. In a TV show, an edit or a
    sequence hangs under an episode. A subclass names its entity type, and
    says how to create and update an entity and how to list its tasks.
    """

    entity_type_name = None
    # An entity of the type hangs under an episode in a TV show.
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
        Tasks of the entity with their assignee ids, so an import does not
        assign again the people a task already has.
        """
        raise NotImplementedError

    def get_extra_values(self, row):
        """
        Values of the columns only the entity type has, to create or update
        an entity with.
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
        # Serialized once: a query would run again on every row, and model
        # instances would be expired by every row commit.
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

    def get_tasks_update(self, row):
        """
        Return the task changes of the row: one entry per task type whose
        status, comment or assignation cell is filled. Raise RowException
        on an unknown status.
        """
        tasks_update = []
        for task_type in self.task_types:
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

            # An empty cell holds no comment, as a missing column does.
            task_comment_text = (
                row.get(f"{task_type['name']} comment", None) or None
            )
            task_assignees = self.get_assignation_ids(row, task_type["name"])

            if (
                task_status_id is not None
                or task_comment_text is not None
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

    def create_and_update_tasks(self, tasks_update, entity, creation=False):
        """
        Apply the task changes of the row: create the missing tasks, add
        the assignees, and post a comment for a new status or a comment.
        On creation, create a task for each task type of the project; with
        no change, leave that to run_import.
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
                # Assignations only add people: an import never removes one.
                already_assigned = set(task.get("assignees") or [])
                for person_id in task_update["assignees"]:
                    if person_id not in already_assigned:
                        assign_task(
                            task["id"], person_id, self.current_user_id
                        )
                # The status guard needs the explicit None check: an entry
                # created for its assignations alone must not post an
                # empty comment at the default status.
                if task_update["comment"] is not None or (
                    task_update["task_status_id"] is not None
                    and task_update["task_status_id"] != task["task_status_id"]
                ):
                    try:
                        create_comment(
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
        elif creation:
            self.created_entities.append(entity.serialize())

    def get_episode_name(self, row):
        """
        Name of the episode a line gives, None for no episode, checked
        against the production.
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
        Id of the episode of given name, created when the production does not
        have it yet.
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
        # nothing: it is not read either, so an assignee renamed since the
        # export does not stop the import there.
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

        tasks_update = self.get_tasks_update(row)

        # Created once the whole line is read: a line refused as it is read
        # leaves no episode behind.
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
