from zou.app.models.status_automation import StatusAutomation
from zou.app.utils import fields
from zou.app.services import (
    comments_service,
    tasks_service,
    projects_service,
)

from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType


class TaskFactories:
    """
    Task types, statuses, automations, tasks and comments.
    """

    def generate_fixture_task_type(self):
        if hasattr(self, "task_type"):
            return
        self.generate_fixture_department()
        self.task_type = TaskType.create(
            name="Shaders",
            short_name="shd",
            color="#FFFFFF",
            for_entity="Asset",
            department_id=self.department.id,
        )
        self.task_type_concept = TaskType.create(
            name="Concept",
            short_name="cpt",
            color="#FFFFFF",
            for_entity="Asset",
            department_id=self.department.id,
        )
        self.task_type_modeling = TaskType.create(
            name="Modeling",
            short_name="mdl",
            color="#FFFFFF",
            for_entity="Asset",
            department_id=self.department.id,
        )
        self.task_type_animation = TaskType.create(
            name="Animation",
            short_name="anim",
            color="#FFFFFF",
            for_entity="Shot",
            department_id=self.department_animation.id,
        )
        self.task_type_layout = TaskType.create(
            name="Layout",
            short_name="layout",
            color="#FFFFFF",
            for_entity="Shot",
            department_id=self.department_animation.id,
        )
        self.task_type_edit = TaskType.create(
            name="Edit",
            short_name="edit",
            color="#FFFFFF",
            for_entity="Edit",
        )

    def generate_fixture_task_status(self):
        if hasattr(self, "task_status"):
            return self.task_status
        self.task_status = TaskStatus.create(
            name="Open", short_name="opn", color="#FFFFFF"
        )
        return self.task_status

    def generate_fixture_task_status_wip(self):
        if hasattr(self, "task_status_wip"):
            return self.task_status_wip
        self.task_status_wip = TaskStatus.create(
            name="WIP", short_name="wip", color="#FFFFFF", is_wip=True
        )
        return self.task_status_wip

    def generate_fixture_task_status_to_review(self):
        if hasattr(self, "task_status_to_review"):
            return self.task_status_to_review
        self.task_status_to_review = TaskStatus.create(
            name="To review", short_name="pndng", color="#FFFFFF"
        )
        return self.task_status_to_review

    def generate_fixture_task_status_retake(self):
        if hasattr(self, "task_status_retake"):
            return self.task_status_retake
        self.task_status_retake = TaskStatus.create(
            name="Retake", short_name="rtk", color="#FFFFFF", is_retake=True
        )
        return self.task_status_retake

    def generate_fixture_task_status_done(self):
        if hasattr(self, "task_status_done"):
            return self.task_status_done
        self.task_status_done = TaskStatus.create(
            name="Done", short_name="done", color="#FFFFFF", is_done=True
        )
        return self.task_status_done

    def generate_fixture_task_status_wfa(self):
        if hasattr(self, "task_status_wfa"):
            return self.task_status_wfa.serialize()
        self.task_status_wfa = TaskStatus.create(
            name="Waiting For Approval",
            short_name="wfa",
            color="#FFFFFF",
            is_feedback_request=True,
        )
        return self.task_status_wfa.serialize()

    def generate_fixture_task_status_todo(self):
        if hasattr(self, "task_status_todo"):
            return self.task_status_todo
        self.task_status_todo = tasks_service.get_default_task_status()
        return self.task_status_todo

    def generate_fixture_status_automation_to_status(self):
        if hasattr(self, "status_automation_to_status"):
            return self.status_automation_to_status
        self.generate_fixture_task_type()
        self.generate_fixture_task_status_done()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_project()
        self.status_automation_to_status = StatusAutomation.create(
            entity_type="asset",
            in_task_type_id=self.task_type_concept.id,
            in_task_status_id=self.task_status_done.id,
            out_field_type="status",
            out_task_type_id=self.task_type_modeling.id,
            out_task_status_id=self.task_status_wip.id,
        )
        projects_service.add_status_automation_setting(
            self.project_id, self.status_automation_to_status.id
        )
        return self.status_automation_to_status

    def generate_fixture_status_automation_to_ready_for(self):
        if hasattr(self, "status_automation_to_ready_for"):
            return self.status_automation_to_ready_for
        self.generate_fixture_task_type()
        self.generate_fixture_task_status_done()
        self.generate_fixture_project()
        self.status_automation_to_ready_for = StatusAutomation.create(
            entity_type="asset",
            in_task_type_id=self.task_type_modeling.id,
            in_task_status_id=self.task_status_done.id,
            out_field_type="ready_for",
            out_task_type_id=self.task_type_layout.id,
            out_task_status_id=None,
        )
        projects_service.add_status_automation_setting(
            self.project_id, self.status_automation_to_ready_for.id
        )
        return self.status_automation_to_ready_for

    # Tasks

    def generate_fixture_task(
        self, name="Master", entity_id=None, task_type_id=None, project_id=None
    ):
        if (
            name == "Master"
            and entity_id is None
            and task_type_id is None
            and project_id is None
            and hasattr(self, "task")
            and hasattr(self, "asset")
            and self.task.project_id == self.project.id
            and self.task.entity_id == self.asset.id
        ):
            return self.task
        self.generate_fixture_asset()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        if entity_id is None:
            entity_id = self.asset.id

        if task_type_id is None:
            task_type_id = self.task_type.id

        if project_id is None:
            project_id = self.project.id

        start_date = fields.get_date_object("2017-02-20")
        due_date = fields.get_date_object("2017-02-28")
        real_start_date = fields.get_date_object("2017-02-22")
        self.task = Task.create(
            name=name,
            project_id=project_id,
            task_type_id=task_type_id,
            task_status_id=self.task_status.id,
            entity_id=entity_id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
            duration=50,
            estimation=40,
            start_date=start_date,
            due_date=due_date,
            real_start_date=real_start_date,
        )
        self.task_id = self.task.id
        self.project.team.append(self.person)
        self.project.save()
        return self.task

    def generate_fixture_task_standard(self):
        if hasattr(self, "task_standard"):
            return self.task_standard
        self.generate_fixture_asset_standard()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        start_date = fields.get_date_object("2017-02-20")
        due_date = fields.get_date_object("2017-02-28")
        real_start_date = fields.get_date_object("2017-02-22")
        self.task_standard = Task.create(
            name="Super modeling",
            project_id=self.project_standard.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset_standard.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
            duration=50,
            estimation=40,
            start_date=start_date,
            due_date=due_date,
            real_start_date=real_start_date,
        )
        self.project.team.append(self.person)
        self.project.save()
        return self.task_standard

    def generate_fixture_shot_task(
        self, name="Master", shot_id=None, task_type_id=None
    ):
        if (
            name == "Master"
            and shot_id is None
            and task_type_id is None
            and hasattr(self, "shot_task")
            and hasattr(self, "shot")
            and self.shot_task.entity_id == self.shot.id
        ):
            return self.shot_task
        if not hasattr(self, "shot"):
            self.generate_fixture_shot()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        if task_type_id is None:
            task_type_id = self.task_type_animation.id

        if shot_id is None:
            shot_id = self.shot.id

        self.shot_task = Task.create(
            name=name,
            project_id=self.project.id,
            task_type_id=task_type_id,
            task_status_id=self.task_status.id,
            entity_id=shot_id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        self.project.team.append(self.person)
        self.project.save()
        return self.shot_task

    def generate_fixture_shot_task_standard(self):
        if hasattr(self, "shot_task_standard"):
            return self.shot_task_standard
        self.generate_fixture_shot_standard()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.shot_task_standard = Task.create(
            name="Super animation",
            project_id=self.project_standard.id,
            task_type_id=self.task_type_animation.id,
            task_status_id=self.task_status.id,
            entity_id=self.shot_standard.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        self.project.team.append(self.person)
        self.project.save()
        return self.shot_task_standard

    def generate_fixture_edit_task(self, name="Edit", task_type_id=None):
        if (
            name == "Edit"
            and task_type_id is None
            and hasattr(self, "edit_task")
        ):
            return self.edit_task
        if not hasattr(self, "edit"):
            self.generate_fixture_edit()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        if task_type_id is None:
            task_type_id = self.task_type_edit.id

        self.edit_task = Task.create(
            name=name,
            project_id=self.project.id,
            task_type_id=task_type_id,
            task_status_id=self.task_status.id,
            entity_id=self.edit.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        self.project.team.append(self.person)
        self.project.save()
        return self.edit_task

    def generate_fixture_episode_task(self, name="Master"):
        if name == "Master" and hasattr(self, "episode_task"):
            return self.episode_task
        if not hasattr(self, "episode"):
            self.generate_fixture_episode()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.episode_task = Task.create(
            name=name,
            project_id=self.project.id,
            task_type_id=self.task_type_animation.id,
            task_status_id=self.task_status.id,
            entity_id=self.episode.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        self.project.team.append(self.person)
        self.project.save()
        return self.episode_task

    def generate_fixture_scene_task(self, name="Master"):
        if name == "Master" and hasattr(self, "scene_task"):
            return self.scene_task
        self.generate_fixture_scene()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.scene_task = Task.create(
            name=name,
            project_id=self.project.id,
            task_type_id=self.task_type_animation.id,
            task_status_id=self.task_status.id,
            entity_id=self.scene.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        self.project.team.append(self.person)
        self.project.save()
        return self.scene_task

    def generate_fixture_sequence_task(self, name="Master"):
        if name == "Master" and hasattr(self, "sequence_task"):
            return self.sequence_task
        self.generate_fixture_sequence()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.sequence_task = Task.create(
            name=name,
            project_id=self.project.id,
            task_type_id=self.task_type_animation.id,
            task_status_id=self.task_status.id,
            entity_id=self.sequence.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        self.project.team.append(self.person)
        self.project.save()
        return self.sequence_task

    # Comments

    def generate_fixture_comment(
        self, person=None, task_id=None, task_status_id=None
    ):
        self.generate_fixture_person()
        if not hasattr(self, "task"):
            self.generate_fixture_task()
        self.generate_fixture_task_status()
        if person is None:
            person = self.person.serialize()
        if task_id is None:
            task_id = self.task.id
        if task_status_id is None:
            task_status_id = self.task_status.id
        self.comment = comments_service.new_comment(
            task_id, task_status_id, person["id"], "first comment"
        )
        return self.comment

    def generate_commented_shot_task(self):
        """
        A shot task with one comment on it, and a second person around to be
        notified. Named apart from generate_fixture_comment, which comments
        on whatever task the caller already has.
        """
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.task = self.generate_fixture_shot_task()
        self.task_dict = self.task.serialize()
        self.generate_fixture_person(
            first_name="Jane", email="jane.doe@gmail.com"
        )
        self.comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "first comment"
        )
        return self.comment
