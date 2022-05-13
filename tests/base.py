import datetime
import unittest
import json
import os
import ntpath

from mixer.backend.flask import mixer

from zou.app import app
from zou.app.models.status_automation import StatusAutomation
from zou.app.utils import fields, auth, fs
from zou.app.services import (
    breakdown_service,
    comments_service,
    file_tree_service,
    tasks_service,
    projects_service,
)

from zou.app.models.asset_instance import AssetInstance
from zou.app.models.build_job import BuildJob
from zou.app.models.day_off import DayOff
from zou.app.models.department import Department
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.file_status import FileStatus
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.milestone import Milestone
from zou.app.models.notification import Notification
from zou.app.models.output_file import OutputFile
from zou.app.models.output_type import OutputType
from zou.app.models.organisation import Organisation
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.models.software import Software
from zou.app.models.working_file import WorkingFile

TEST_FOLDER = os.path.join("tests", "tmp")


class ApiTestCase(unittest.TestCase):
    """
    Set of helpers to make test development easier.
    """

    def setUp(self):
        """
        Configure Flask application before each test.
        """
        app.test_request_context(headers={"mimetype": "application/json"})
        self.flask_app = app
        self.app = app.test_client()
        self.base_headers = {}
        self.post_headers = {"Content-type": "application/json"}
        from zou.app.utils import cache

        cache.clear()

    def log_in(self, email):
        tokens = self.post(
            "auth/login", {"email": email, "password": "mypassword"}, 200
        )
        self.auth_headers = {
            "Authorization": "Bearer %s" % tokens["access_token"]
        }
        self.base_headers.update(self.auth_headers)
        self.post_headers.update(self.auth_headers)

    def log_in_admin(self):
        self.log_in(self.user["email"])

    def log_in_manager(self):
        self.log_in(self.user_manager["email"])

    def log_in_cg_artist(self):
        self.log_in(self.user_cg_artist["email"])

    def log_in_client(self):
        self.log_in(self.user_client["email"])

    def log_in_vendor(self):
        self.log_in(self.user_vendor["email"])

    def log_out(self):
        try:
            self.get("auth/logout")
        except AssertionError:
            pass

    def get(self, path, code=200):
        """
        Get data provided at given path. Format depends on the path.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        return json.loads(response.data.decode("utf-8"))

    def get_raw(self, path, code=200):
        """
        Get data provided at given path. Format depends on the path. Do not
        parse the json.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        return response.data.decode("utf-8")

    def get_first(self, path, code=200):
        """
        Get first element of data at given path. It makes the assumption that
        returned data is an array.
        """
        rows = self.get(path, code)
        return rows[0]

    def get_404(self, path):
        """
        Make sure that given path returns a 404 error for GET requests.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, 404)

    def post(self, path, data, code=201):
        """
        Run a post request at given path while making sure it sends data at
        JSON format.
        """
        clean_data = fields.serialize_value(data)
        response = self.app.post(
            path, data=json.dumps(clean_data), headers=self.post_headers
        )
        if response.status_code == 500:
            print(response.data)
        self.assertEqual(response.status_code, code)
        return json.loads(response.data.decode("utf-8"))

    def post_404(self, path, data):
        """
        Make sure that given path returns a 404 error for POST requests.
        """
        response = self.app.post(
            path, data=json.dumps(data), headers=self.post_headers
        )
        self.assertEqual(response.status_code, 404)

    def put(self, path, data, code=200):
        """
        Run a put request at given path while making sure it sends data at JSON
        format.
        """
        response = self.app.put(
            path, data=json.dumps(data), headers=self.post_headers
        )
        self.assertEqual(response.status_code, code)
        return json.loads(response.data.decode("utf-8"))

    def put_404(self, path, data):
        """
        Make sure that given path returns a 404 error for PUT requests.
        """
        response = self.app.put(
            path, data=json.dumps(data), headers=self.post_headers
        )
        self.assertEqual(response.status_code, 404)

    def delete(self, path, code=204):
        """
        Run a delete request at given path.
        """
        response = self.app.delete(path, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        return response.data

    def delete_404(self, path):
        """
        Make sure that given path returns a 404 error for DELETE requests.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, 404)

    def upload_file(self, path, file_path, code=201, extra_fields={}):
        """
        Upload a file at given path. File data are sent in the request body.
        """
        file_content = open(file_path, "rb")
        file_name = ntpath.basename(file_path)
        data = {"file": (file_content, file_name)}
        if len(extra_fields.keys()) > 0:
            data.update(extra_fields)
        response = self.app.post(path, data=data, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        return response.data

    def download_file(self, path, target_file_path, code=200):
        """
        Download a file located at given url path and save it at given file
        path.
        """
        response = self.app.get(path, headers=self.base_headers)
        self.assertEqual(response.status_code, code)
        file_descriptor = open(target_file_path, "wb")
        file_descriptor.write(response.data)
        return open(target_file_path, "rb").read()

    def tearDown(self):
        pass


class ApiDBTestCase(ApiTestCase):
    def setUp(self):
        """
        Reset database before each test.
        """
        super(ApiDBTestCase, self).setUp()

        from zou.app.utils import dbhelpers

        dbhelpers.drop_all()
        dbhelpers.create_all()
        self.generate_fixture_user()
        self.log_in_admin()

    def tearDown(self):
        """
        Delete database after each test.
        """
        from zou.app.utils import dbhelpers

        dbhelpers.drop_all()

    def generate_data(self, cls, number, **kwargs):
        """
        Generate random data for a given data model.
        """
        mixer.init_app(self.flask_app)
        return mixer.cycle(number).blend(cls, id=fields.gen_uuid, **kwargs)

    def generate_fixture_project_status(self):
        self.open_status = ProjectStatus.create(name="Open", color="#FFFFFF")

    def generate_fixture_project_closed_status(self):
        self.closed_status = ProjectStatus.create(
            name="closed", color="#FFFFFF"
        )

    def generate_fixture_project(self, name="Cosmos Landromat"):
        self.project = Project.create(
            name=name, project_status_id=self.open_status.id
        )
        self.project_id = self.project.id
        self.project.update(
            {"file_tree": file_tree_service.get_tree_from_file("simple")}
        )
        return self.project

    def generate_fixture_project_closed(self):
        self.project_closed = Project.create(
            name="Old Project", project_status_id=self.closed_status.id
        )

    def generate_fixture_project_standard(self):
        self.project_standard = Project.create(
            name="Big Buck Bunny", project_status_id=self.open_status.id
        )
        self.project_standard.update(
            {"file_tree": file_tree_service.get_tree_from_file("default")}
        )

    def generate_fixture_project_no_preview_tree(self):
        self.project_no_preview_tree = Project.create(
            name="Agent 327", project_status_id=self.open_status.id
        )
        self.project_no_preview_tree.update(
            {"file_tree": file_tree_service.get_tree_from_file("no_preview")}
        )

    def generate_fixture_asset(
        self, name="Tree", description="Description Tree", asset_type_id=None
    ):
        if asset_type_id is None:
            asset_type_id = self.asset_type.id

        self.asset = Entity.create(
            name=name,
            description=description,
            project_id=self.project.id,
            entity_type_id=asset_type_id,
        )
        return self.asset

    def generate_fixture_asset_character(
        self, name="Rabbit", description="Main char"
    ):
        self.asset_character = Entity.create(
            name=name,
            description=description,
            project_id=self.project.id,
            entity_type_id=self.asset_type_character.id,
        )
        return self.asset_character

    def generate_fixture_asset_camera(self):
        self.asset_camera = Entity.create(
            name="Main camera",
            description="Description Camera",
            project_id=self.project.id,
            entity_type_id=self.asset_type_camera.id,
        )

    def generate_fixture_asset_standard(self):
        self.asset_standard = Entity.create(
            name="Car",
            project_id=self.project_standard.id,
            entity_type_id=self.asset_type.id,
        )

    def generate_fixture_sequence(
        self, name="S01", episode_id=None, project_id=None
    ):
        if episode_id is None and hasattr(self, "episode"):
            episode_id = self.episode.id

        if project_id is None:
            project_id = self.project.id

        self.sequence = Entity.create(
            name=name,
            project_id=project_id,
            entity_type_id=self.sequence_type.id,
            parent_id=episode_id,
        )
        return self.sequence

    def generate_fixture_sequence_standard(self):
        self.sequence_standard = Entity.create(
            name="S01",
            project_id=self.project_standard.id,
            entity_type_id=self.sequence_type.id,
        )
        return self.sequence_standard

    def generate_fixture_episode(self, name="E01", project_id=None):
        if project_id is None:
            project_id = self.project.id
        self.episode = Entity.create(
            name=name,
            project_id=project_id,
            entity_type_id=self.episode_type.id,
        )
        return self.episode

    def generate_fixture_shot(self, name="P01", nb_frames=0):
        self.shot = Entity.create(
            name=name,
            description="Description Shot 01",
            data={"fps": 25, "frame_in": 0, "frame_out": 100},
            project_id=self.project.id,
            entity_type_id=self.shot_type.id,
            parent_id=self.sequence.id,
            nb_frames=nb_frames,
        )
        return self.shot

    def generate_fixture_scene(
        self, name="SC01", project_id=None, sequence_id=None
    ):
        if project_id is None:
            project_id = self.project.id

        if sequence_id is None:
            sequence_id = self.sequence.id

        self.scene = Entity.create(
            name=name,
            description="Description Scene 01",
            data={},
            project_id=project_id,
            entity_type_id=self.scene_type.id,
            parent_id=self.sequence.id,
        )
        return self.scene

    def generate_fixture_shot_standard(self, name="SH01"):
        self.shot_standard = Entity.create(
            name=name,
            description="Description Shot 01",
            data={"fps": 25, "frame_in": 0, "frame_out": 100},
            project_id=self.project_standard.id,
            entity_type_id=self.shot_type.id,
            parent_id=self.sequence_standard.id,
        )
        return self.shot_standard

    def generate_fixture_shot_asset_instance(
        self, shot, asset_instance, number=1
    ):
        self.shot.instance_casting.append(asset_instance)
        self.shot.save()
        return self.shot

    def generate_fixture_scene_asset_instance(
        self, asset=None, scene=None, number=1
    ):
        if asset is None:
            asset = self.asset
        if scene is None:
            scene = self.scene
        self.asset_instance = AssetInstance.create(
            asset_id=asset.id,
            scene_id=scene.id,
            number=number,
            name=breakdown_service.build_asset_instance_name(
                self.asset.id, number
            ),
            description="Asset instance description",
        )
        return self.asset_instance

    def generate_fixture_asset_asset_instance(
        self, asset=None, target_asset=None, number=1
    ):
        if asset is None:
            asset = self.asset_character
        if target_asset is None:
            target_asset = self.asset
        self.asset_instance = AssetInstance.create(
            asset_id=asset.id,
            target_asset_id=target_asset.id,
            number=number,
            name=breakdown_service.build_asset_instance_name(asset.id, number),
            description="Asset instance description",
        )
        return self.asset_instance

    def generate_fixture_user(self):
        self.user = Person.create(
            first_name="John",
            last_name="Did",
            role="admin",
            email="john.did@gmail.com",
            password=auth.encrypt_password("mypassword"),
        ).serialize()
        return self.user

    def generate_fixture_user_manager(self):
        self.user_manager = Person.create(
            first_name="John",
            last_name="Did2",
            role="manager",
            email="john.did.manager@gmail.com",
            password=auth.encrypt_password("mypassword"),
        ).serialize()
        return self.user_manager

    def generate_fixture_user_cg_artist(self):
        self.user_cg_artist = Person.create(
            first_name="John",
            last_name="Did3",
            email="john.did.cg.artist@gmail.com",
            role="user",
            password=auth.encrypt_password("mypassword"),
        ).serialize(relations=True)
        return self.user_cg_artist

    def generate_fixture_user_client(self):
        self.user_client = Person.create(
            first_name="John",
            last_name="Did4",
            role="client",
            email="john.did.client@gmail.com",
            password=auth.encrypt_password("mypassword"),
        ).serialize()
        return self.user_client

    def generate_fixture_user_vendor(self):
        self.user_vendor = Person.create(
            first_name="John",
            last_name="Did5",
            role="vendor",
            email="john.did.vendor@gmail.com",
            password=auth.encrypt_password("mypassword"),
        ).serialize()
        return self.user_vendor

    def generate_fixture_person(
        self,
        first_name="John",
        last_name="Doe",
        desktop_login="john.doe",
        email="john.doe@gmail.com",
    ):
        self.person = Person.get_by(email=email)
        if self.person is None:
            self.person = Person.create(
                first_name=first_name,
                last_name=last_name,
                desktop_login=desktop_login,
                email=email,
                password=auth.encrypt_password("mypassword"),
            )
        return self.person

    def generate_fixture_asset_type(self):
        self.asset_type = EntityType.create(name="Props")
        self.asset_type_props = self.asset_type
        self.shot_type = EntityType.create(name="Shot")
        self.sequence_type = EntityType.create(name="Sequence")
        self.episode_type = EntityType.create(name="Episode")
        self.scene_type = EntityType.create(name="Scene")
        self.edit_type = EntityType.create(name="Edit")

    def generate_fixture_asset_types(self):
        self.asset_type_character = EntityType.create(name="Character")
        self.asset_type_environment = EntityType.create(name="Environment")
        self.asset_type_camera = EntityType.create(name="Camera")

    def generate_fixture_department(self):
        self.department = Department.create(name="Modeling", color="#FFFFFF")
        self.department_animation = Department.create(
            name="Animation", color="#FFFFFF"
        )
        return self.department

    def generate_fixture_task_type(self):
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
        self.task_status = TaskStatus.create(
            name="Open", short_name="opn", color="#FFFFFF"
        )
        return self.task_status

    def generate_fixture_task_status_wip(self):
        self.task_status_wip = TaskStatus.create(
            name="WIP", short_name="wip", color="#FFFFFF"
        )
        return self.task_status_wip

    def generate_fixture_task_status_to_review(self):
        self.task_status_to_review = TaskStatus.create(
            name="To review", short_name="pndng", color="#FFFFFF"
        )
        return self.task_status_to_review

    def generate_fixture_task_status_retake(self):
        self.task_status_retake = TaskStatus.create(
            name="Retake", short_name="rtk", color="#FFFFFF", is_retake=True
        )
        return self.task_status_retake

    def generate_fixture_task_status_done(self):
        self.task_status_done = TaskStatus.create(
            name="Done", short_name="done", color="#FFFFFF", is_done=True
        )
        return self.task_status_done

    def generate_fixture_task_status_wfa(self):
        self.task_status_wfa = TaskStatus.create(
            name="Waiting For Approval",
            short_name="wfa",
            color="#FFFFFF",
            is_feedback_request=True,
        )
        return self.task_status_wfa.serialize()

    def generate_fixture_task_status_todo(self):
        self.task_status_todo = tasks_service.get_default_status()
        return self.task_status_todo

    def generate_fixture_status_automation_to_status(self):
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

    def generate_fixture_assigner(self):
        self.assigner = Person.create(first_name="Ema", last_name="Peel")
        return self.assigner

    def generate_fixture_task(
        self, name="Master", entity_id=None, task_type_id=None
    ):
        if entity_id is None:
            entity_id = self.asset.id

        if task_type_id is None:
            task_type_id = self.task_type.id

        start_date = fields.get_date_object("2017-02-20")
        due_date = fields.get_date_object("2017-02-28")
        real_start_date = fields.get_date_object("2017-02-22")
        self.task = Task.create(
            name=name,
            project_id=self.project.id,
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

    def generate_fixture_shot_task(self, name="Master", task_type_id=None):
        if task_type_id is None:
            task_type_id = self.task_type_animation.id

        self.shot_task = Task.create(
            name=name,
            project_id=self.project.id,
            task_type_id=task_type_id,
            task_status_id=self.task_status.id,
            entity_id=self.shot.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        self.project.team.append(self.person)
        self.project.save()
        return self.shot_task

    def generate_fixture_edit_task(self, name="Edit", task_type_id=None):
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

    def generate_fixture_shot_task_standard(self):
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

    def generate_fixture_comment(
        self, person=None, task_id=None, task_status_id=None
    ):
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

    def generate_fixture_file_status(self):
        self.file_status = FileStatus.create(name="To review", color="#FFFFFF")

    def generate_fixture_working_file(self, name="main", revision=1):
        self.working_file = WorkingFile.create(
            name=name,
            comment="",
            revision=revision,
            task_id=self.task.id,
            entity_id=self.asset.id,
            person_id=self.person.id,
            software_id=self.software.id,
        )
        return self.working_file

    def generate_fixture_shot_working_file(self):
        self.working_file = WorkingFile.create(
            name="main",
            comment="",
            revision=1,
            task_id=self.shot_task.id,
            entity_id=self.shot.id,
            person_id=self.person.id,
            software_id=self.software.id,
        )

    def generate_fixture_output_file(
        self,
        output_type=None,
        revision=1,
        name="main",
        representation="",
        asset_instance=None,
        temporal_entity_id=None,
        task=None,
    ):
        if output_type is None:
            output_type = self.output_type

        if task is None:
            task_type_id = self.task_type.id
            asset_id = self.asset.id
        else:
            task_type_id = task.task_type_id
            asset_id = task.entity_id

        if asset_instance is None:
            asset_instance_id = None
        else:
            asset_instance_id = asset_instance.id
            if temporal_entity_id is None:
                temporal_entity_id = self.scene.id

        self.output_file = OutputFile.create(
            comment="",
            revision=revision,
            task_type_id=task_type_id,
            entity_id=asset_id,
            person_id=self.person.id,
            file_status_id=self.file_status.id,
            output_type_id=output_type.id,
            asset_instance_id=asset_instance_id,
            representation=representation,
            temporal_entity_id=temporal_entity_id,
            name=name,
        )
        return self.output_file

    def generate_fixture_output_type(self, name="Geometry", short_name="Geo"):
        self.output_type = OutputType.create(name=name, short_name=short_name)
        return self.output_type

    def generate_fixture_software(self):
        self.software = Software.create(
            name="Blender", short_name="bdr", file_extension=".blender"
        )
        self.software_max = Software.create(
            name="3dsMax", short_name="max", file_extension=".max"
        )

    def generate_fixture_organisation(self):
        self.organisation = Organisation.create(
            name="My Studio", hours_by_day=8, use_original_file_name=False
        )

    def generate_fixture_preview_file(
        self, revision=1, name="main", position=1, status="ready"
    ):
        self.preview_file = PreviewFile.create(
            name=name,
            revision=revision,
            description="test description",
            source="pytest",
            task_id=self.task.id,
            extension="mp4",
            person_id=self.person.id,
            position=position,
            status=status,
        )
        return self.preview_file

    def get_fixture_file_path(self, relative_path):
        current_path = os.getcwd()
        file_path_fixture = os.path.join(
            current_path, "tests", "fixtures", relative_path
        )
        return file_path_fixture

    def generate_fixture_metadata_descriptor(self, entity_type="Asset"):
        self.meta_descriptor = MetadataDescriptor.create(
            project_id=self.project.id,
            name="Contractor",
            field_name="contractor",
            choices=["value 1", "value 2"],
            entity_type=entity_type,
        )
        return self.meta_descriptor

    def generate_fixture_playlist(
        self,
        name,
        project_id=None,
        episode_id=None,
        for_entity="shot",
        for_client=False,
        is_for_all=False,
        task_type_id=None,
    ):
        if project_id is None:
            project_id = self.project.id
        self.playlist = Playlist.create(
            name=name,
            project_id=project_id,
            episode_id=episode_id,
            for_entity=for_entity,
            is_for_all=is_for_all,
            for_client=for_client,
            task_type_id=task_type_id,
            shots=[],
        )
        return self.playlist.serialize()

    def generate_fixture_build_job(self, ended_at, playlist_id=None):
        if playlist_id is None:
            playlist_id = self.playlist.id
        self.build_job = BuildJob.create(
            status="succeeded",
            job_type="movie",
            ended_at=ended_at,
            playlist_id=playlist_id,
        )
        return self.build_job.serialize()

    def generate_fixture_subscription(self, task_id=None):
        task = self.task
        if task_id is not None:
            task = Task.get(task_id)

        self.subscription = Subscription.create(
            person_id=self.user["id"],
            task_id=task.id,
            entity_id=task.entity_id,
            task_type_id=task.task_type_id,
        )
        return self.subscription.serialize()

    def generate_fixture_notification(self):
        self.notification = Notification.create(
            type="comment",
            person_id=self.user["id"],
            author_id=self.person.id,
            comment_id=self.comment["id"],
            task_id=self.task.id,
        )
        return self.notification.serialize()

    def generate_fixture_milestone(self):
        self.milestone = Milestone.create(
            name="Test Milestone",
            project_id=self.project.id,
            task_type_id=self.task_type.id,
        )
        return self.milestone.serialize()

    def generate_fixture_schedule_item(
        self, task_type_id=None, object_id=None
    ):
        if task_type_id is None:
            task_type_id = self.task_type.id
        self.schedule_item = ScheduleItem.create(
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            object_id=object_id,
        )
        return self.schedule_item.serialize()

    def generate_fixture_day_off(self, date, person_id=None):
        if person_id is None:
            person_id = self.person.id
        self.day_off = DayOff.create(date=date, person_id=person_id)
        return self.day_off.serialize()

    def generate_fixture_edit(self, name="Edit", parent_id=None):
        self.edit = Entity.create(
            name=name,
            description="Description of the Edit",
            project_id=self.project.id,
            entity_type_id=self.edit_type.id,
            parent_id=parent_id,
        )
        return self.edit

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

    def assign_task(self, task_id, user_id):
        return tasks_service.assign_task(task_id, user_id)

    def assign_task_to_artist(self, task_id):
        if self.user_cg_artist is None:
            self.generate_fixture_user_cg_artist()
        self.assign_task(task_id, self.user_cg_artist["id"])

    def now(self):
        return datetime.datetime.now().replace(microsecond=0).isoformat()

    def upload_csv(self, path, name):
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "%s.csv" % name)
        )
        self.upload_file(path, file_path_fixture)

    def get_file_path(self, filename):
        current_path = os.path.dirname(__file__)
        result_file_path = os.path.join(TEST_FOLDER, filename)
        return os.path.join(current_path, "..", result_file_path)

    def create_test_folder(self):
        os.mkdir(TEST_FOLDER)

    def delete_test_folder(self):
        fs.rm_rf(TEST_FOLDER)
