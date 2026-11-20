from tests.base import ApiDBTestCase
from zou.app.models.comment import Comment
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.services import projects_service


class PreviewActionsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_task()

        self.first = self.generate_fixture_preview_file(
            name="first", position=1
        ).serialize()
        self.second = self.generate_fixture_preview_file(
            name="second", position=2
        ).serialize()
        self.third = self.generate_fixture_preview_file(
            name="third", position=3
        ).serialize()

    def positions(self):
        """
        Read the stored positions keyed by name. The route answers with the
        previews in their former order and only the position field carries
        the new one, so ordering the response would prove nothing.
        """
        previews = PreviewFile.query.filter_by(task_id=self.task.id).all()
        return {preview.name: preview.position for preview in previews}

    def test_update_preview_position(self):
        self.assertEqual(
            self.positions(), {"first": 1, "second": 2, "third": 3}
        )

        self.put(
            f"/actions/preview-files/{self.third['id']}/update-position",
            {"position": 1},
        )

        self.assertEqual(
            self.positions(), {"third": 1, "first": 2, "second": 3}
        )

    def test_update_preview_position_out_of_range(self):
        """
        A position outside 1..len is ignored rather than raising, so a client
        racing against a deletion cannot 500 the route.
        """
        self.put(
            f"/actions/preview-files/{self.first['id']}/update-position",
            {"position": 99},
        )
        self.assertEqual(
            self.positions(), {"first": 1, "second": 2, "third": 3}
        )

    def test_extract_frame_from_a_picture(self):
        """
        Only a movie has frames to extract. A preview of any other extension
        is a 404, not a crash inside ffmpeg.
        """
        picture = self.generate_fixture_preview_file(name="picture")
        picture.update({"extension": "png"})
        self.get(f"/actions/preview-files/{picture.id}/extract-frame", 404)


class PreviewTrimTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_task()
        self.main = self.generate_fixture_preview_file(name="main", position=1)
        self.extra = self.generate_fixture_preview_file(
            name="extra", position=2
        )
        # A key Zou writes itself: the trim must never drop it.
        self.extra.update({"data": {"movie_prefixes": ["previews"]}})
        self.path = f"/actions/preview-files/{self.extra.id}/update-trim"

    def stored_data(self):
        return PreviewFile.get(self.extra.id).data

    def join_team(self, person):
        projects_service.add_team_member(self.project.id, person["id"])

    def test_set_and_clear_trim(self):
        result = self.put(self.path, {"handle_in": 12}, 200)
        self.assertEqual(result["handle_in"], 12)
        self.assertIsNone(result["handle_out"])

        # Only the sent key changes.
        result = self.put(self.path, {"handle_out": 48}, 200)
        self.assertEqual(result["handle_in"], 12)
        self.assertEqual(result["handle_out"], 48)
        self.assertEqual(
            self.stored_data(),
            {
                "movie_prefixes": ["previews"],
                "handle_in": 12,
                "handle_out": 48,
            },
        )

        # Null clears a handle.
        self.put(self.path, {"handle_out": None}, 200)
        self.assertEqual(
            self.stored_data(),
            {"movie_prefixes": ["previews"], "handle_in": 12},
        )

    def test_trim_on_data_that_is_not_an_object(self):
        self.extra.update({"data": None})
        self.put(self.path, {"handle_in": 3}, 200)
        self.assertEqual(self.stored_data(), {"handle_in": 3})

    def test_trim_leaves_other_previews_alone(self):
        self.put(self.path, {"handle_in": 12}, 200)
        self.assertFalse((PreviewFile.get(self.main.id).data or {}))

    def test_negative_handle_is_refused(self):
        self.put(self.path, {"handle_in": -1}, 400)

    def test_unknown_preview_file(self):
        self.put(
            "/actions/preview-files/a24a6ea4-ce75-4665-a070-57453082c250"
            "/update-trim",
            {"handle_in": 1},
            404,
        )

    def test_comment_previews_carry_their_trim(self):
        comment = Comment.get(
            self.generate_fixture_comment(task_id=self.task.id)["id"]
        )
        comment.previews.append(self.main)
        comment.previews.append(self.extra)
        comment.save()
        self.put(self.path, {"handle_in": 5, "handle_out": 20}, 200)

        comments = self.get(f"/data/tasks/{self.task.id}/comments")
        previews = {p["id"]: p for p in comments[0]["previews"]}
        self.assertEqual(previews[str(self.extra.id)]["handle_in"], 5)
        self.assertEqual(previews[str(self.extra.id)]["handle_out"], 20)
        self.assertIsNone(previews[str(self.main.id)]["handle_in"])
        self.assertIsNone(previews[str(self.main.id)]["handle_out"])

    def test_manager_can_trim(self):
        self.generate_fixture_user_manager()
        self.join_team(self.user_manager)
        self.log_in_manager()
        self.put(self.path, {"handle_in": 1}, 200)

    def test_supervisor_without_department_can_trim(self):
        self.generate_fixture_user_supervisor()
        self.join_team(self.user_supervisor)
        self.log_in_supervisor()
        self.put(self.path, {"handle_in": 1}, 200)

    def test_department_supervisor_cannot_trim(self):
        self.generate_fixture_user_supervisor()
        self.join_team(self.user_supervisor)
        self.generate_fixture_department()
        supervisor = Person.get(self.user_supervisor["id"])
        supervisor.departments = [self.department]
        supervisor.save()
        self.log_in_supervisor()
        self.put(self.path, {"handle_in": 1}, 403)

    def test_artist_cannot_trim(self):
        self.generate_fixture_user_cg_artist()
        self.join_team(self.user_cg_artist)
        self.log_in_cg_artist()
        self.put(self.path, {"handle_in": 1}, 403)
