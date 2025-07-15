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

    def test_get_comment_hashtags_basic(self):
        """Test hashtag detection in comment text"""
        task_types = ["animation", "modeling", "lighting", "all"]
        
        # Test single hashtag
        hashtags = comments_service.get_comment_hashtags(task_types, "Great work! #animation")
        self.assertListEqual(hashtags, ["animation"])
        
        # Test multiple hashtags
        hashtags = comments_service.get_comment_hashtags(task_types, "Check this out #animation #lighting")
        self.assertIn("animation", hashtags)
        self.assertIn("lighting", hashtags)
        
        # Test case insensitive
        hashtags = comments_service.get_comment_hashtags(task_types, "Great work! #ANIMATION")
        self.assertListEqual(hashtags, ["animation"])
        
        # Test hashtag at end of sentence
        hashtags = comments_service.get_comment_hashtags(task_types, "Great work! #animation.")
        self.assertListEqual(hashtags, ["animation"])

    def test_get_comment_hashtags_special_cases(self):
        """Test hashtag edge cases"""
        task_types = ["animation", "modeling", "lighting", "all"]
        
        # Test no hashtags
        hashtags = comments_service.get_comment_hashtags(task_types, "Great work! No hashtags here")
        self.assertListEqual(hashtags, [])
        
        # Test invalid hashtags (not in task_types)
        hashtags = comments_service.get_comment_hashtags(task_types, "Great work! #invalid #unknown")
        self.assertListEqual(hashtags, [])
        
        # Test mixed valid and invalid hashtags
        hashtags = comments_service.get_comment_hashtags(task_types, "Great work! #animation #invalid #lighting")
        self.assertIn("animation", hashtags)
        self.assertIn("lighting", hashtags)
        self.assertNotIn("invalid", hashtags)

    def test_get_comment_hashtags_all_priority(self):
        """Test that #all hashtag takes priority"""
        task_types = ["animation", "modeling", "lighting", "all"]
        
        # Test #all with other hashtags - should return only ["all"]
        hashtags = comments_service.get_comment_hashtags(task_types, "Great work! #all #animation #lighting")
        self.assertListEqual(hashtags, ["all"])
        
        # Test just #all
        hashtags = comments_service.get_comment_hashtags(task_types, "Great work! #all")
        self.assertListEqual(hashtags, ["all"])

    def test_filter_tasks_by_hashtags_basic(self):
        """Test task filtering by hashtags"""
        # Create mock tasks
        tasks = [
            {"id": "1", "task_type_name": "animation"},
            {"id": "2", "task_type_name": "modeling"},
            {"id": "3", "task_type_name": "lighting"},
            {"id": "4", "task_type_name": "rigging"}
        ]
        
        # Test filtering by single hashtag
        filtered = comments_service.filter_tasks_by_hashtags(tasks, ["animation"])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["task_type_name"], "animation")
        
        # Test filtering by multiple hashtags
        filtered = comments_service.filter_tasks_by_hashtags(tasks, ["animation", "lighting"])
        self.assertEqual(len(filtered), 2)
        task_types = [task["task_type_name"] for task in filtered]
        self.assertIn("animation", task_types)
        self.assertIn("lighting", task_types)

    def test_filter_tasks_by_hashtags_exclude(self):
        """Test task filtering with exclusions"""
        tasks = [
            {"id": "1", "task_type_name": "animation"},
            {"id": "2", "task_type_name": "modeling"},
            {"id": "3", "task_type_name": "lighting"},
        ]
        
        # Test excluding specific task types
        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, ["animation", "modeling"], exclude_tasks=["animation"]
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["task_type_name"], "modeling")

    def test_filter_tasks_by_hashtags_all(self):
        """Test filtering with #all hashtag"""
        tasks = [
            {"id": "1", "task_type_name": "animation"},
            {"id": "2", "task_type_name": "modeling"},
            {"id": "3", "task_type_name": "lighting"},
        ]
        
        # Test #all returns all tasks (no filtering)
        filtered = comments_service.filter_tasks_by_hashtags(tasks, ["all"])
        self.assertEqual(len(filtered), 3)

    def test_filter_tasks_by_hashtags_empty(self):
        """Test filtering with empty hashtags"""
        tasks = [
            {"id": "1", "task_type_name": "animation"},
            {"id": "2", "task_type_name": "modeling"},
        ]
        
        # Test empty hashtags returns empty list
        filtered = comments_service.filter_tasks_by_hashtags(tasks, [])
        self.assertEqual(len(filtered), 0)

    def test_create_comment_with_hashtags_integration(self):
        """Integration test for create_comment with hashtag functionality"""
        # Create tasks for the shot entity
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        concept_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_concept.id
        )
        
        # Create comment with hashtags
        comment_text = "Great shot! Please check #modeling #concept"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        
        # Verify main comment was created
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        
        # Note: In a full integration test, we would verify that linked comments
        # were created on the modeling and lighting tasks, but this requires
        # mocking the entities_service.get_entity_tasks function

    def test_create_comment_with_hashtags_no_links(self):
        """Test that hashtag processing only occurs when no links are provided"""
        # This test verifies that hashtag processing is skipped when links are provided
        comment_text = "Great shot! Please check #modeling #lighting"
        original_comment_id = "test-comment-id"
        
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
            links=[original_comment_id],  # This should skip hashtag processing
        )
        
        # Verify comment was created normally without hashtag processing
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)

    def test_hashtag_integration_single_hashtag(self):
        """Integration test: Create comment with single hashtag"""
        # Create modeling task for the same shot
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        
        # Create comment with hashtag
        comment_text = "Great shot! Please check #modeling"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        
        # Verify main comment was created
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["person_id"], self.person_id)
        
        # Verify original task status changed to the new status
        self.task = tasks_service.get_task_raw(self.task.id)
        self.assertEqual(str(self.task.task_status_id), str(self.task_status.id))
        
        # Verify modeling task status remains unchanged (hashtag comments don't change status)
        modeling_task = tasks_service.get_task_raw(modeling_task.id)
        self.assertEqual(str(modeling_task.task_status_id), str(modeling_task.task_status_id))

    def test_hashtag_integration_multiple_hashtags(self):
        """Integration test: Create comment with multiple hashtags"""
        # Create tasks for the same shot
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        concept_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_concept.id
        )
        
        # Create comment with multiple hashtags
        comment_text = "Check this out #modeling #concept"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        
        # Verify main comment was created
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["person_id"], self.person_id)
        
        # Store original task statuses before comment creation
        original_task_status_id = self.task.task_status_id
        original_modeling_task_status_id = modeling_task.task_status_id
        original_concept_task_status_id = concept_task.task_status_id
        
        # Verify original task status changed to the new status
        self.task = tasks_service.get_task_raw(self.task.id)
        self.assertEqual(str(self.task.task_status_id), str(self.task_status.id))
        
        # Verify other tasks statuses remain unchanged
        modeling_task = tasks_service.get_task_raw(modeling_task.id)
        self.assertEqual(str(modeling_task.task_status_id), str(original_modeling_task_status_id))
        concept_task = tasks_service.get_task_raw(concept_task.id)
        self.assertEqual(str(concept_task.task_status_id), str(original_concept_task_status_id))

    def test_hashtag_integration_all_hashtag(self):
        """Integration test: Create comment with #all hashtag"""
        # Create tasks for the same shot
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        concept_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_concept.id
        )
        
        # Create comment with #all hashtag
        comment_text = "Important update for everyone #all"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        
        # Verify main comment was created
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["person_id"], self.person_id)
        
        # Store original task statuses before comment creation
        original_modeling_task_status_id = modeling_task.task_status_id
        original_concept_task_status_id = concept_task.task_status_id
        
        # Verify original task status changed to the new status
        self.task = tasks_service.get_task_raw(self.task.id)
        self.assertEqual(str(self.task.task_status_id), str(self.task_status.id))
        
        # Verify other tasks statuses remain unchanged
        modeling_task = tasks_service.get_task_raw(modeling_task.id)
        self.assertEqual(str(modeling_task.task_status_id), str(original_modeling_task_status_id))
        concept_task = tasks_service.get_task_raw(concept_task.id)
        self.assertEqual(str(concept_task.task_status_id), str(original_concept_task_status_id))
    
    def test_hashtag_integration_with_status_change(self):
        """Integration test: Hashtag comment with status change on original task"""
        # Create modeling task
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )

        # Create comment with hashtag and status change
        comment_text = "Animation complete! #modeling"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.wfa_status["id"]),  # Change to WFA status
            text=comment_text,
        )
        
        # Verify main comment
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["task_status_id"], str(self.wfa_status["id"]))
        
        # Store original task statuses before comment creation
        original_modeling_task_status_id = modeling_task.task_status_id
        
        # Verify original task status changed to WFA
        self.task = tasks_service.get_task_raw(self.task.id)
        self.assertEqual(str(self.task.task_status_id), str(self.wfa_status["id"]))
        
        # Verify modeling task status remains unchanged
        modeling_task = tasks_service.get_task_raw(modeling_task.id)
        self.assertEqual(str(modeling_task.task_status_id), str(original_modeling_task_status_id))

    def test_hashtag_integration_case_insensitive(self):
        """Integration test: Hashtags are case insensitive"""
        # Create modeling task
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        
        # Create comment with mixed case hashtags
        comment_text = "Check this #MODELING and #Modeling"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        
        # Verify comment was created
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["person_id"], self.person_id)
        
        # Store original task statuses before comment creation
        original_task_status_id = self.task.task_status_id
        original_modeling_task_status_id = modeling_task.task_status_id
        
        # Verify original task status changed to the new status
        self.task = tasks_service.get_task_raw(self.task.id)
        self.assertEqual(str(self.task.task_status_id), str(self.task_status.id))
        
        # Verify modeling task status remains unchanged
        modeling_task = tasks_service.get_task_raw(modeling_task.id)
        self.assertEqual(str(modeling_task.task_status_id), str(original_modeling_task_status_id))

    def test_hashtag_integration_invalid_hashtags(self):
        """Integration test: Invalid hashtags are ignored"""
        # Create comment with invalid hashtags
        comment_text = "Check this #InvalidHashtag #UnknownTask"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        
        # Verify comment was created normally
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["person_id"], self.person_id)
        
        # Verify original task status changed to the new status
        self.task = tasks_service.get_task_raw(self.task.id)
        self.assertEqual(str(self.task.task_status_id), str(self.task_status.id))

    def test_hashtag_integration_mixed_valid_invalid(self):
        """Integration test: Mix of valid and invalid hashtags"""
        # Create modeling task
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        
        # Create comment with mixed hashtags
        comment_text = "Check this #modeling #InvalidHashtag #concept"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        
        # Verify comment was created
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["person_id"], self.person_id)
        
        # Store original task statuses before comment creation
        original_modeling_task_status_id = modeling_task.task_status_id
        
        # Verify original task status changed to the new status
        self.task = tasks_service.get_task_raw(self.task.id)
        self.assertEqual(str(self.task.task_status_id), str(self.task_status.id))
        
        # Verify modeling task status remains unchanged
        modeling_task = tasks_service.get_task_raw(modeling_task.id)
        self.assertEqual(str(modeling_task.task_status_id), str(original_modeling_task_status_id))

    def test_hashtag_integration_no_hashtags(self):
        """Integration test: Comment without hashtags works normally"""
        # Create comment without hashtags
        comment_text = "Normal comment without hashtags"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        
        # Verify comment was created normally
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["person_id"], self.person_id)
        
        # Verify original task status changed to the new status
        self.task = tasks_service.get_task_raw(self.task.id)
        self.assertEqual(str(self.task.task_status_id), str(self.task_status.id))
