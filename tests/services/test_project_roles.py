from unittest import mock

from flask import g
from flask_jwt_extended import verify_jwt_in_request

from tests.base import ApiDBTestCase

from zou.app import app, db
from zou.app.models.person import Person
from zou.app.models.project import ProjectPersonLink
from zou.app.models.studio import Studio
from zou.app.services import (
    comments_service,
    entities_service,
    projects_service,
    tasks_service,
    user_service,
)
from zou.app.services.exception import WrongParameterException
from zou.app.utils import permissions


class ProjectPersonLinkRoleTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_person()

    def test_role_column_defaults_to_none(self):
        self.project.team.append(self.person)
        self.project.save()
        link = ProjectPersonLink.query.filter_by(
            project_id=self.project.id, person_id=self.person.id
        ).first()
        self.assertIsNotNone(link)
        self.assertIsNone(link.role)
        link.role = "supervisor"
        db.session.commit()
        link = ProjectPersonLink.query.filter_by(
            project_id=self.project.id, person_id=self.person.id
        ).first()
        self.assertEqual(link.role.code, "supervisor")


class GetProjectRoleTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_person()

    def add_to_team(self, person, role=None):
        self.project.team.append(person)
        self.project.save()
        if role is not None:
            link = ProjectPersonLink.query.filter_by(
                project_id=self.project.id, person_id=person.id
            ).first()
            link.role = role
            db.session.commit()

    def test_explicit_link_role_wins(self):
        self.add_to_team(self.person, role="supervisor")
        self.assertEqual(
            user_service.get_project_role(
                str(self.person.id), str(self.project.id)
            ),
            "supervisor",
        )

    def test_null_link_role_inherits_global_role(self):
        self.add_to_team(self.person)
        self.assertEqual(
            user_service.get_project_role(
                str(self.person.id), str(self.project.id)
            ),
            self.person.role.code,
        )

    def test_no_link_falls_back_to_global_role(self):
        self.assertEqual(
            user_service.get_project_role(
                str(self.person.id), str(self.project.id)
            ),
            self.person.role.code,
        )

    def test_failed_membership_check_clears_the_role_slot(self):
        project_a = self.project
        self.add_to_team(self.person, role="supervisor")
        project_b = self.generate_fixture_project("Other project")
        current_user = self.person.serialize()
        with app.test_request_context():
            with mock.patch.object(
                user_service.persons_service,
                "get_current_user",
                return_value=current_user,
            ):
                self.assertTrue(
                    user_service.check_belong_to_project(str(project_a.id))
                )
                self.assertEqual(g.get("project_role"), "supervisor")
                self.assertFalse(
                    user_service.check_belong_to_project(str(project_b.id))
                )
                self.assertIsNone(g.get("project_role"))


class PermissionOverrideTestCase(ApiDBTestCase):
    def test_project_role_overrides_global_checks(self):
        with app.test_request_context():
            g.project_role = "manager"
            self.assertTrue(permissions.has_manager_permissions())
            self.assertFalse(permissions.has_supervisor_permissions())
            self.assertTrue(permissions.has_at_least_supervisor_permissions())
            self.assertFalse(permissions.has_client_permissions())

        with app.test_request_context():
            g.project_role = "user"
            self.assertFalse(permissions.has_manager_permissions())
            self.assertTrue(permissions.has_artist_permissions())

        with app.test_request_context():
            g.project_role = "vendor"
            self.assertTrue(permissions.has_vendor_permissions())
            self.assertFalse(permissions.has_at_least_supervisor_permissions())


class ProjectRoleRouteTestCase(ApiDBTestCase):
    """
    Promotion and demotion through a manager-gated route:
    POST /data/projects/<id>/team goes through
    check_manager_project_access.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        # generate_fixture_project reassigns self.project on every call, so
        # the first project must be captured before creating the second one.
        self.project_a = self.project
        self.project_b = self.generate_fixture_project("Second project")
        self.generate_fixture_person()
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_user_manager()

    def set_team_role(self, project, person_id, role):
        link = ProjectPersonLink.query.filter_by(
            project_id=project.id, person_id=person_id
        ).first()
        link.role = role
        db.session.commit()

    def add_member(self, project, person_id, role=None):
        projects_service.add_team_member(str(project.id), person_id)
        if role is not None:
            self.set_team_role(project, person_id, role)

    def test_project_manager_can_manage_team_on_their_project_only(self):
        artist_id = str(self.user_cg_artist["id"])
        person_id = str(self.person.id)
        # Pre-add the target person so the POST under test only has to
        # clear the permission gate, not also perform a fresh team insert.
        projects_service.add_team_member(str(self.project_a.id), person_id)
        self.add_member(self.project_a, artist_id, role="manager")
        self.add_member(self.project_b, artist_id)
        self.log_in_cg_artist()
        data = {"person_id": person_id}
        self.post(f"data/projects/{self.project_a.id}/team", data, 201)
        self.post(f"data/projects/{self.project_b.id}/team", data, 403)

    def test_demoted_manager_cannot_manage_team(self):
        manager_id = str(self.user_manager["id"])
        self.add_member(self.project_a, manager_id, role="user")
        self.log_in_manager()
        data = {"person_id": str(self.person.id)}
        self.post(f"data/projects/{self.project_a.id}/team", data, 403)


class ProjectRoleSemanticsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_person()
        self.generate_fixture_user_cg_artist()

    def add_member(self, project, person_id, role=None):
        project.team.append(Person.get(person_id))
        project.save()
        if role is not None:
            link = ProjectPersonLink.query.filter_by(
                project_id=project.id, person_id=person_id
            ).first()
            link.role = role
            db.session.commit()

    def test_admin_ignores_project_roles(self):
        # ApiDBTestCase creates and logs in a global admin (self.user).
        # A link role never demotes an admin.
        admin_id = str(self.user["id"])
        self.add_member(self.project, admin_id, role="user")
        data = {"person_id": str(self.person.id)}
        self.post(f"data/projects/{self.project.id}/team", data, 201)

    def test_project_vendor_restricted_to_assigned_entities(self):
        # Global artist set as vendor on the project: entity access
        # restrictions apply, the unassigned task becomes forbidden.
        artist_id = str(self.user_cg_artist["id"])
        self.add_member(self.project, artist_id, role="vendor")
        self.log_in_cg_artist()
        self.get(f"data/tasks/{self.task.id}", 403)


class TeamRoleServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_person()

    def test_add_team_member_with_role(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id), role="supervisor"
        )
        self.assertEqual(
            projects_service.get_team_roles(str(self.project.id)),
            {str(self.person.id): "supervisor"},
        )

    def test_add_team_member_without_role_inherits(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id)
        )
        self.assertEqual(
            projects_service.get_team_roles(str(self.project.id)), {}
        )

    def test_update_team_member_role(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id)
        )
        projects_service.update_team_member_role(
            str(self.project.id), str(self.person.id), "manager"
        )
        self.assertEqual(
            projects_service.get_team_roles(str(self.project.id)),
            {str(self.person.id): "manager"},
        )
        projects_service.update_team_member_role(
            str(self.project.id), str(self.person.id), None
        )
        self.assertEqual(
            projects_service.get_team_roles(str(self.project.id)), {}
        )

    def test_update_team_member_role_requires_membership(self):
        self.assertRaises(
            WrongParameterException,
            projects_service.update_team_member_role,
            str(self.project.id),
            str(self.person.id),
            "manager",
        )

    def test_update_team_member_role_rejects_admin(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id)
        )
        self.assertRaises(
            WrongParameterException,
            projects_service.update_team_member_role,
            str(self.project.id),
            str(self.person.id),
            "admin",
        )

    def test_add_team_member_rejects_admin_without_partial_state(self):
        self.assertRaises(
            WrongParameterException,
            projects_service.add_team_member,
            str(self.project.id),
            str(self.person.id),
            "admin",
        )
        project = projects_service.get_project_raw(str(self.project.id))
        self.assertEqual(len(project.team), 0)


class TeamRoleApiTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_person()

    def test_add_team_member_with_role(self):
        data = {"person_id": str(self.person.id), "role": "supervisor"}
        self.post(f"data/projects/{self.project.id}/team", data, 201)
        team = self.get(f"data/projects/{self.project.id}/team")
        self.assertEqual(team[0]["project_role"], "supervisor")

    def test_add_team_member_rejects_admin_role(self):
        data = {"person_id": str(self.person.id), "role": "admin"}
        self.post(f"data/projects/{self.project.id}/team", data, 400)

    def test_put_team_member_role(self):
        self.post(
            f"data/projects/{self.project.id}/team",
            {"person_id": str(self.person.id)},
            201,
        )
        result = self.put(
            f"data/projects/{self.project.id}/team/{self.person.id}",
            {"role": "manager"},
        )
        self.assertEqual(result["role"], "manager")
        result = self.put(
            f"data/projects/{self.project.id}/team/{self.person.id}",
            {"role": None},
        )
        self.assertIsNone(result["role"])
        team = self.get(f"data/projects/{self.project.id}/team")
        self.assertIsNone(team[0]["project_role"])

    def test_put_team_member_role_requires_membership(self):
        # update_team_member_role raises WrongParameterException for a
        # non-member, which maps to 400, not 404.
        self.put(
            f"data/projects/{self.project.id}/team/{self.person.id}",
            {"role": "manager"},
            400,
        )

    def test_put_team_member_role_rejects_admin(self):
        self.post(
            f"data/projects/{self.project.id}/team",
            {"person_id": str(self.person.id)},
            201,
        )
        self.put(
            f"data/projects/{self.project.id}/team/{self.person.id}",
            {"role": "admin"},
            400,
        )


class DirectRoleReadTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_person()

    def make_comment(self, author_id):
        return comments_service.create_comment(
            person_id=author_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text="hello",
        )

    def test_last_comment_map_uses_project_role(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id), role="client"
        )
        self.make_comment(str(self.person.id))
        comment_map = tasks_service.get_last_comment_map([str(self.task.id)])
        self.assertEqual(comment_map, {})


class AllShotsRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: shots/resources.py AllShotsResource.get moves
    check_project_access above the vendor filter so a project-scoped
    vendor demotion is honored.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        self.generate_fixture_user_manager()

    def test_demoted_vendor_scoped_to_assigned_shots(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="vendor"
        )
        self.log_in_manager()
        shots = self.get(f"data/shots?project_id={self.project.id}")
        self.assertEqual(len(shots), 0)
        tasks_service.assign_task(str(self.shot_task.id), manager_id)
        shots = self.get(f"data/shots?project_id={self.project.id}")
        self.assertEqual(len(shots), 1)


class ProjectPersonQuotasRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: shots/resources.py ProjectPersonQuotasResource.get
    resolves the project role before branching, so a demoted manager falls
    to the person-access branch instead of the project-wide one.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_user_manager()
        self.generate_fixture_person()

    def test_demoted_manager_cannot_view_other_person_quotas(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="user"
        )
        self.log_in_manager()
        self.get(
            f"data/projects/{self.project.id}/quotas/persons/"
            f"{self.person.id}",
            403,
        )


class TaskCommentDeleteRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: tasks/resources.py TaskCommentResource.delete
    resolves the project role before branching, so a demoted manager
    cannot delete another person's comment.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_comment()
        self.generate_fixture_user_manager()

    def test_demoted_manager_cannot_delete_others_comment(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="user"
        )
        self.log_in_manager()
        self.delete(
            f"data/tasks/{self.task.id}/comments/{self.comment['id']}", 403
        )


class CommentUpdateRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: crud/comments.py
    CommentResource.check_update_permissions resolves the project role via
    check_belong_to_project before the has_manager check, so a demoted
    manager loses comment-edit powers.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_comment()
        self.generate_fixture_user_manager()

    def test_demoted_manager_cannot_edit_others_comment(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="user"
        )
        self.log_in_manager()
        self.put(
            f"data/comments/{self.comment['id']}",
            {"text": "Edited"},
            403,
        )


class CommentReplyRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: comments/resources.py reply() runs
    check_task_action_access (which resolves the project role) before the
    client-isolation branch, so a demoted client cannot reply across
    studios.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_user_manager()
        self.generate_fixture_user_client()

    def test_demoted_client_blocked_from_replying_across_studios(self):
        studio_a = Studio.create(name="Studio A", color="#FF0000")
        studio_b = Studio.create(name="Studio B", color="#00FF00")

        author_id = str(self.user_client["id"])
        author = Person.get(author_id)
        author.update({"studio_id": studio_a.id})
        projects_service.add_team_member(
            str(self.project.id), author_id, role="client"
        )
        comment = comments_service.create_comment(
            person_id=author_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text="Client note",
        )

        manager_id = str(self.user_manager["id"])
        manager = Person.get(manager_id)
        manager.update({"studio_id": studio_b.id})
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="client"
        )

        self.log_in_manager()
        self.post(
            f"data/tasks/{self.task.id}/comments/{comment['id']}/reply",
            {"text": "reply"},
            403,
        )


class PreviewThumbnailRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: previews/resources.py
    BasePreviewFileThumbnailResource.is_allowed resolves the project role
    before checking has_vendor_permissions, so a demoted vendor does not
    get the shared-preview shortcut.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_preview_file()
        self.asset.update(
            {
                "preview_file_id": str(self.preview_file.id),
                "is_shared": True,
            }
        )
        self.generate_fixture_user_manager()

    def test_demoted_vendor_must_be_assigned_for_shared_thumbnail(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="vendor"
        )
        self.log_in_manager()
        self.get(
            f"/pictures/thumbnails/preview-files/{self.preview_file.id}.png",
            403,
        )


class PreviewFileReadRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: crud/preview_file.py
    PreviewFileResource.check_read_permissions resolves the project role
    before checking has_vendor_permissions, so a demoted vendor must be
    working on the task.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_preview_file()
        self.generate_fixture_user_manager()

    def test_demoted_vendor_not_working_on_task_cannot_read(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="vendor"
        )
        self.log_in_manager()
        self.get(f"data/preview-files/{self.preview_file.id}", 403)


class OutputFileUpdateRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: crud/output_file.py
    OutputFileResource.check_update_permissions checks
    has_manager_project_access instead of the global
    has_manager_permissions, so a demoted manager must be working on the
    entity.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_output_type()
        self.generate_fixture_output_file()
        self.generate_fixture_user_manager()

    def test_demoted_manager_must_be_working_on_entity(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="user"
        )
        self.log_in_manager()
        self.put(
            f"data/output-files/{self.output_file.id}",
            {"comment": "Updated"},
            403,
        )


class ProductionScheduleVersionRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: crud/production_schedule_version.py
    check_read_permissions methods run check_project_access before the
    has_vendor/has_client deny, so a demoted client is caught by the deny
    instead of slipping through on a stale global role.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_user_manager()
        self.version = self.post(
            "data/production-schedule-versions",
            {"name": "Version 1", "project_id": str(self.project.id)},
        )

    def test_demoted_client_cannot_read_production_schedule_version(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="client"
        )
        self.log_in_manager()
        self.get(
            f"data/production-schedule-versions/{self.version['id']}", 403
        )

    def test_global_vendor_gets_403_not_500_with_no_query_args(self):
        self.generate_fixture_user_vendor()
        self.log_in_vendor()
        self.get("data/production-schedule-versions", 403)


class AllEditsRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: edits/resources.py AllEditsResource.get moves
    check_project_access above the vendor filter so a project-scoped
    vendor demotion is honored.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_edit()
        self.generate_fixture_edit_task()
        self.generate_fixture_user_manager()

    def test_demoted_vendor_scoped_to_assigned_edits(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="vendor"
        )
        self.log_in_manager()
        edits = self.get(f"data/edits?project_id={self.project.id}")
        self.assertEqual(len(edits), 0)
        tasks_service.assign_task(str(self.edit_task.id), manager_id)
        edits = self.get(f"data/edits?project_id={self.project.id}")
        self.assertEqual(len(edits), 1)


class EntityMetadataRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: user_service.check_metadata_department_access
    resolves check_belong_to_project before has_manager/has_supervisor, so
    a demoted manager loses entity metadata write access.

    Exercised at the service level: crud/entity.py's EntityResource.put
    wraps check_update_permissions in a bare `except Exception` that
    downgrades PermissionDenied (403) to 400 before the response reaches
    the client, a pre-existing bug unrelated to this fix. Calling the
    service directly under a real, JWT-verified request context isolates
    the ordering fix from that unrelated bug.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_user_manager()

    def test_demoted_manager_cannot_update_entity_metadata(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="user"
        )
        self.log_in_manager()
        entity = entities_service.get_entity(str(self.asset.id))
        with app.test_request_context(headers=self.auth_headers):
            verify_jwt_in_request()
            self.assertRaises(
                permissions.PermissionDenied,
                user_service.check_metadata_department_access,
                entity,
                {"name": "Updated Tree"},
            )


class AllDepartmentsAccessRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: user_service.check_all_departments_access resolves
    check_belong_to_project before has_manager/has_supervisor, so a
    demoted manager loses department-wide access.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_user_manager()

    def test_demoted_manager_cannot_create_metadata_descriptor(self):
        manager_id = str(self.user_manager["id"])
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="user"
        )
        self.log_in_manager()
        data = {
            "name": "Custom Field",
            "data_type": "string",
            "entity_type": "Asset",
        }
        self.post(
            f"data/projects/{self.project.id}/metadata-descriptors",
            data,
            403,
        )
