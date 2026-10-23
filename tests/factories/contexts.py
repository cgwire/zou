class ContextFactories:
    """
    Whole contexts, for the tests that need a production standing up.
    """

    def generate_base_context(self):
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()

    def generate_assigned_task(self):
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()

    def generate_shot_suite(self):
        self.generate_fixture_asset_type()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()

    def generate_fixture_shot_tasks_and_previews(self, task_type_id):
        episode_01 = self.episode
        sequence_01 = self.sequence
        shot_01 = self.shot
        shot_02 = self.generate_fixture_shot("SH02")
        shot_03 = self.generate_fixture_shot("SH03")

        self.generate_fixture_episode("E02")
        episode_02 = self.episode
        self.generate_fixture_sequence("S02", episode_id=episode_02.id)
        sequence_02 = self.sequence
        shot_e201 = self.generate_fixture_shot(
            "E2SH01", sequence_id=sequence_02.id
        )

        task_shot_01 = self.generate_fixture_shot_task(
            shot_id=shot_01.id, task_type_id=task_type_id
        )
        task_shot_02 = self.generate_fixture_shot_task(
            shot_id=shot_02.id, task_type_id=task_type_id
        )
        task_shot_03 = self.generate_fixture_shot_task(
            shot_id=shot_03.id, task_type_id=task_type_id
        )
        task_shot_e201 = self.generate_fixture_shot_task(
            shot_id=shot_e201.id, task_type_id=task_type_id
        )
        preview_01 = self.generate_fixture_preview_file(
            task_id=task_shot_01.id, revision=1, duration=15
        )
        preview_01 = self.generate_fixture_preview_file(
            task_id=task_shot_01.id, revision=2, duration=25
        )
        preview_01 = self.generate_fixture_preview_file(
            task_id=task_shot_01.id, revision=3, duration=30
        )
        preview_02 = self.generate_fixture_preview_file(
            task_id=task_shot_02.id, revision=1, duration=20
        )
        preview_03 = self.generate_fixture_preview_file(
            task_id=task_shot_03.id, revision=1, duration=10
        )
        preview_e201 = self.generate_fixture_preview_file(
            task_id=task_shot_e201.id, revision=1, duration=40
        )
        return (
            episode_01,
            episode_02,
            sequence_01,
            sequence_02,
            shot_01,
            shot_02,
            shot_03,
            shot_e201,
            task_shot_01,
            task_shot_02,
            task_shot_03,
            task_shot_e201,
            preview_01,
            preview_02,
            preview_03,
            preview_e201,
        )
