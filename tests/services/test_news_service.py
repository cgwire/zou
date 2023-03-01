from datetime import datetime, timedelta
from tests.base import ApiDBTestCase

from zou.app.models.news import News
from zou.app.services import comments_service, news_service


class NewsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(NewsServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()
        self.project_dict = self.sequence.serialize()

    def generate_fixture_comment(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.task_type_dict = self.task_type_animation.serialize()
        self.generate_fixture_task_status()
        self.task = self.generate_fixture_shot_task()
        self.task_dict = self.task.serialize()
        self.person_dict = self.generate_fixture_person(
            first_name="Jane", email="jane.doe@gmail.com"
        ).serialize()

        self.comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "first comment"
        )

    def test_create_news(self):
        self.generate_fixture_comment()
        news = news_service.create_news(
            comment_id=self.comment["id"],
            author_id=self.comment["person_id"],
            task_id=self.comment["object_id"],
        )
        news_again = News.get(news["id"])
        self.assertIsNotNone(news_again)

    def test_create_news_for_task_and_comment(self):
        self.generate_fixture_comment()
        news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )
        news_list = News.get_all()
        self.assertEqual(len(news_list), 1)
        self.assertEqual(str(news_list[0].author_id), self.user["id"])
        self.assertEqual(str(news_list[0].task_id), self.task_dict["id"])
        self.assertEqual(str(news_list[0].comment_id), self.comment["id"])

    def test_delete_news_for_comment(self):
        self.generate_fixture_comment()
        news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )
        news_service.delete_news_for_comment(self.comment["id"])
        news_list = News.get_all()
        self.assertEqual(len(news_list), 0)

    def test_get_last_news_for_project(self):
        self.generate_fixture_comment()
        for i in range(1, 81):
            comment = comments_service.new_comment(
                self.task.id,
                self.task_status.id,
                self.user["id"],
                "comment %s" % i,
            )
            news = news_service.create_news_for_task_and_comment(
                self.task_dict, comment
            )
        news_list = news_service.get_last_news_for_project(
            project_id=self.task_dict["project_id"]
        )
        self.assertEqual(len(news_list["data"]), 50)
        news = news_list["data"][0]
        self.assertEqual(news["project_name"], "Cosmos Landromat")
        self.assertEqual(news["full_entity_name"], "E01 / S01 / P01")
        self.assertEqual(news["project_id"], self.task_dict["project_id"])

        news_list = news_service.get_last_news_for_project(
            project_id=self.task_dict["project_id"], page=2
        )
        self.assertEqual(len(news_list["data"]), 30)

        news_list = news_service.get_last_news_for_project(
            project_id=self.task_dict["project_id"], news_id=news["id"]
        )
        self.assertEqual(len(news_list["data"]), 1)

    def test_get_last_news_for_project_with_dates(self):
        self.generate_fixture_comment()
        for i in range(1, 7):
            comment = comments_service.new_comment(
                self.task.id,
                self.task_status.id,
                self.user["id"],
                "comment %s" % i,
            )
            news_service.create_news_for_task_and_comment(
                self.task_dict,
                comment,
                created_at=datetime.now() - timedelta(days=i),
            )
        news_list = news_service.get_last_news_for_project(
            project_id=self.task_dict["project_id"]
        )
        self.assertEqual(len(news_list["data"]), 6)
        date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        news_list = news_service.get_last_news_for_project(
            project_id=self.task_dict["project_id"], after=date
        )
        self.assertEqual(len(news_list["data"]), 2)
        news_list = news_service.get_last_news_for_project(
            project_id=self.task_dict["project_id"], before=date
        )
        self.assertEqual(len(news_list["data"]), 4)
