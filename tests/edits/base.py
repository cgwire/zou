from tests.base import ApiDBTestCase

from zou.app.utils import events


class BaseEditTestCase(ApiDBTestCase):
    def setUp(self):
        super(BaseEditTestCase, self).setUp()
        self.generate_fixture_project_status()
        project = self.generate_fixture_project()
        self.project_name = project.name

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()

        episode = self.generate_fixture_episode()
        self.episode_id = str(episode.id)
        self.episode_name = episode.name

        self.generate_fixture_edit(parent_id=episode.id)
        self.edit_id = self.edit.id
        self.edit_dict = self.edit.serialize(obj_type="Edit")

        self.generate_fixture_person()
        self.person_id = str(self.person.id)

        self.generate_fixture_assigner()
        self.generate_fixture_task_status()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.task_type_edit_dict = self.task_type_edit.serialize()

        self.generate_fixture_task()
        self.generate_fixture_task(
            name="Edit",
            entity_id=self.edit_id,
            task_type_id=self.task_type_edit.id,
        )
        self.generate_fixture_task(
            name="DCP",
            entity_id=self.edit_id,
            task_type_id=self.task_type_edit.id,
        )

        self.maxDiff = None

        self.is_event_fired = False
        events.unregister_all()
