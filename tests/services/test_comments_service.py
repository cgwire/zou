from tests.base import ApiDBTestCase

from zou.app.services import (
    comments_service,
    entities_service,
    persons_service,
    tasks_service,
    exception,
)

class CommentsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(CommentsServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.project.update({"max_retakes": 3})
        self.project.save()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.task_type_dict = self.task_type_animation.serialize()
        self.generate_fixture_task_status()
        self.task = self.generate_fixture_shot_task()
        self.task_dict = self.task.serialize(relations=True)
        self.person_id = str(self.person.id)
        self.person_dict = self.generate_fixture_person(
            first_name="Jane", email="jane.doe@gmail.com"
        ).serialize()
        self.wfa_status = self.generate_fixture_task_status_wfa()
        self.project_id = str(self.project.id)

    def generate_commment():
        pass

    def test_new_comment(self):
        self.comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "first comment"
        )
        self.assertTrue(self.comment["id"] is not None)
        self.assertTrue(self.comment["created_at"] is not None)
        self.assertEqual(self.comment["object_id"], str(self.task.id))
        self.comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            self.user["id"],
            "second comment",
            created_at="2024-01-23 10:00:00",
        )
        self.assertEqual(self.comment["created_at"], "2024-01-23T10:00:00")
        # TODO test attachment files

    def test_create_comment(self):
        # TODO
        pass

    def test_check_retake_capping(self):
        self.project.update({"max_retakes": 2})
        retake_status = self.generate_fixture_task_status_retake().serialize()
        task = self.task.serialize()
        comments_service._check_retake_capping(retake_status, task)
        self.task.update({"retake_count": 3})
        task = self.task.serialize()
        with self.assertRaises(exception.WrongParameterException):
            comments_service._check_retake_capping(retake_status, task)

        self.shot.update({"data": {"max_retakes": 4}})
        self.shot.save()
        entities_service.clear_entity_cache(task["entity_id"])
        comments_service._check_retake_capping(retake_status, task)
        self.task.update({"retake_count": 5})
        task = self.task.serialize()
        with self.assertRaises(exception.WrongParameterException):
            comments_service._check_retake_capping(retake_status, task)

    def test_get_comment_author(self):
        user_id = self.user["id"]
        author = comments_service._get_comment_author(self.user["id"])
        self.assertEqual(author["id"], user_id)

    def test_manage_status_change(self):
        self.comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "first comment"
        )
        task_status = self.task_status.serialize()
        retake_status = self.generate_fixture_task_status_retake().serialize()
        task = self.task.serialize()
        comment = self.comment
        (task, status_changed) = comments_service._manage_status_change(
            task_status, task, comment
        )
        self.assertFalse(status_changed)
        self.assertEqual(task["retake_count"], 0)
        (task, status_changed) = comments_service._manage_status_change(
            retake_status, task, comment
        )
        self.assertTrue(status_changed)
        self.assertEqual(task["retake_count"], 1)

        old_comment = comments_service.new_comment(
            self.task.id,
            retake_status["id"],
            self.user["id"],
            "old comment",
            created_at="1999-12-23 10:00:00",
        )
        (task, status_changed) = comments_service._manage_status_change(
            retake_status, task, old_comment
        )

        self.assertFalse(status_changed)
        self.assertEqual(task["retake_count"], 1)

        (task, status_changed) = comments_service._manage_status_change(
            self.wfa_status, task, comment
        )
        self.assertTrue(task["end_date"] is not None)

    def test_manage_subscriptions(self):
        # TODO
        pass

    def test_run_status_automation(self):
        # TODO
        pass

    def add_attachments_to_comment(self):
        # TODO
        pass

    def test_create_attachment(self):
        # TODO
        pass

    def test_get_attachment_file_path(self):
        # TODO
        pass

    def test_get_all_attachment_files_for_project(self):
        # TODO
        pass

    def test_manage_subscriptions(self):
        # TODO
        pass

    def test_run_status_automation(self):
        # TODO
        pass

    def add_attachments_to_comment(self):
        # TODO
        pass

    def test_create_attachment(self):
        # TODO
        pass

    def test_get_attachment_file_path(self):
        # TODO
        pass

    def test_get_all_attachment_files_for_project(self):
        # TODO
        pass

    def test_get_all_attachment_files_for_task(self):
        # TODO
        pass

    def test_acknowledge_comment(self):
        # TODO
        pass

    def test_ack_comment(self):
        # TODO
        pass

    def test_unack_comment(self):
        # TODO
        pass

    def test_reply_comment(self):
        reply_text = "first reply"
        comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            self.user["id"],
            "comment that starts a thread discussion",
        )
        comments_service.reply_comment(
            comment["id"], reply_text, person_id=self.user["id"]
        )
        comment = tasks_service.get_comment(comment["id"])
        self.assertEqual(len(comment["replies"]), 1)
        self.assertEqual(comment["replies"][0]["text"], reply_text)
        self.assertEqual(comment["replies"][0]["person_id"], self.user["id"])
        comments_service.reply_comment(
            comment["id"],
            "mention @Animation and @John Doe",
            person_id=self.user["id"],
        )
        tasks_service.clear_comment_cache(comment["id"])
        comment = tasks_service.get_comment(comment["id"])
        self.assertEqual(len(comment["replies"]), 2)
        self.assertListEqual(
            comment["replies"][1]["mentions"], [self.person_id]
        )
        self.assertListEqual(
            comment["replies"][1]["department_mentions"],
            [str(self.department_animation.id)],
        )

    def get_reply(self):
        # TODO
        pass

    def delete_reply(self):
        # TODO
        pass

    def test_reset_mentions(self):
        self.comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            self.user["id"],
            "mentions @Animation @John Doe",
        )
        comment = comments_service.reset_mentions(self.comment)
        self.assertListEqual(comment["mentions"], [self.person_id])
        self.assertListEqual(
            comment["department_mentions"], [str(self.department_animation.id)]
        )

    def test_get_comment_mentions(self):
        mentions = comments_service.get_comment_mentions(
            self.project_id,
            "nothing to mention",
        )
        self.assertListEqual(mentions, [])
        mentions = comments_service.get_comment_mentions(
            self.project_id,
            "mention @John Doe",
        )
        person = persons_service.get_person_raw(self.person_id)
        self.assertListEqual(mentions, [person])

    def test_get_comment_mention_ids(self):
        mentions = comments_service.get_comment_mention_ids(
            self.project_id,
            "nothing to mention",
        )
        self.assertListEqual(mentions, [])
        mentions = comments_service.get_comment_mention_ids(
            self.project_id,
            "mention @John Doe",
        )
        self.assertListEqual(mentions, [self.person_id])

    def test_get_comment_department_mentions(self):
        mentions = comments_service.get_comment_department_mentions(
            self.project_id,
            "nothing to mention",
        )
        self.assertListEqual(mentions, [])
        mentions = comments_service.get_comment_department_mentions(
            self.project_id,
            "mention @Animation",
        )
        self.assertListEqual(mentions, [self.department_animation])

    def test_get_comment_department_mention_ids(self):
        mentions = comments_service.get_comment_department_mention_ids(
            self.project_id,
            "nothing to mention",
        )
        self.assertListEqual(mentions, [])
        mentions = comments_service.get_comment_department_mention_ids(
            self.project_id,
            "mention @Animation",
        )
        self.assertListEqual(mentions, [str(self.department_animation.id)])

    def test_get_comment_hashtags(self):
        hashtags = comments_service.get_comment_hashtags(
            "Great work! #animation"
        )
        self.assertListEqual(hashtags, ["animation"])
        
        hashtags = comments_service.get_comment_hashtags(
            "Check this out #animation #lighting"
        )
        self.assertIn("animation", hashtags)
        self.assertIn("lighting", hashtags)
        
        hashtags = comments_service.get_comment_hashtags(
            "Great work! #ANIMATION"
        )
        self.assertListEqual(hashtags, ["animation"])
        
        hashtags = comments_service.get_comment_hashtags(
            "Great work! #animation."
        )
        self.assertListEqual(hashtags, ["animation"])

        hashtags = comments_service.get_comment_hashtags(
            "Great work! No hashtags here"
         )
        self.assertListEqual(hashtags, [])
        
    def test_get_comment_hashtags_all_priority(self):
        hashtags = comments_service.get_comment_hashtags(
            "Great work! #all #animation #lighting"
        )
        self.assertListEqual(hashtags, ["all"])
        
        hashtags = comments_service.get_comment_hashtags("Great work! #all")
        self.assertListEqual(hashtags, ["all"])

    def test_filter_tasks_by_hashtags(self):
        tasks = [
            {"id": "1", "task_type_name": "animation"},
            {"id": "2", "task_type_name": "modeling"},
            {"id": "3", "task_type_name": "lighting"},
            {"id": "4", "task_type_name": "rigging"}
        ]
        task_type_animation = {"id": "tt1", "name": "Animation"}
        
        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, ["modeling"], task_type_animation
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["task_type_name"], "modeling")
        
        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, ["modeling", "lighting"], task_type_animation
        )
        self.assertEqual(len(filtered), 2)
        task_types = [task["task_type_name"] for task in filtered]
        self.assertIn("modeling", task_types)
        self.assertIn("lighting", task_types)

        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, ["animation", "modeling"], task_type_animation
        )
        self.assertEqual(len(filtered), 1)

        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, ["all"], task_type_animation
        )
        self.assertEqual(len(filtered), 3)

        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, [], task_type_animation
        )
        self.assertEqual(len(filtered), 0)

    def test_create_comment_with_hashtags(self):
        """Integration test for create_comment with hashtag functionality"""
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        concept_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_concept.id
        )
        
        comment_text = "Great shot! Please check #modeling #concept"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        text = ""
        comments = tasks_service.get_comments(modeling_task.id)
        self.assertEqual(len(comments), 1)
        self.assertTrue("Animation" in comments[0]["text"])
        modeling_task = tasks_service.get_task_raw(modeling_task.id)
        self.assertEqual(
            str(modeling_task.task_status_id), 
            str(modeling_task.task_status_id)
        )
        comments = tasks_service.get_comments(concept_task.id)
        self.assertEqual(len(comments), 1)
        self.assertTrue("Animation" in comments[0]["text"])

        modeling_task = tasks_service.get_task_raw(modeling_task.id)
        self.assertEqual(
            str(modeling_task.task_status_id), 
            str(modeling_task.task_status_id)
        )
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
            with_hashtags=False
        )
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)

    def test_create_comment_with_all_hashtag(self):
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        concept_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_concept.id
        )
        
        comment_text = "Important update for everyone #all"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["person_id"], self.person_id)
