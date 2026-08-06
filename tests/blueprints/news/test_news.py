from tests.base import ApiDBTestCase

from zou.app.services import comments_service, news_service


class NewsRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def test_get_last_news_for_project(self):
        self.generate_commented_shot_task()
        for i in range(1, 81):
            comment = comments_service.new_comment(
                self.task.id,
                self.task_status.id,
                self.user["id"],
                f"comment {i}",
            )
            news = news_service.create_news_for_task_and_comment(
                self.task_dict, comment
            )
        news_list = self.get(
            f"/data/projects/{self.task_dict['project_id']}/news"
        )
        self.assertEqual(len(news_list["data"]), 50)
        news = news_list["data"][0]
        self.assertEqual(news["project_name"], "Cosmos Landromat")
        self.assertEqual(news["full_entity_name"], "E01 / S01 / P01")
        self.assertEqual(news["project_id"], self.task_dict["project_id"])

        news_list = self.get(
            f"/data/projects/{self.task_dict['project_id']}/news?page=2"
        )
        self.assertEqual(len(news_list["data"]), 30)

        news = self.get(
            f"/data/projects/{self.task_dict['project_id']}/news/{news['id']}"
        )
        self.assertIsNotNone(news["created_at"])

    def test_get_global_news(self):
        self.generate_commented_shot_task()
        news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )
        news_list = self.get("/data/projects/news")
        self.assertEqual(len(news_list["data"]), 1)

    def test_news_embeds_author(self):
        self.generate_commented_shot_task()
        news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )
        news_list = self.get(
            "/data/projects/%s/news" % self.task_dict["project_id"]
        )
        news = news_list["data"][0]
        self.assertEqual(news["person"]["id"], news["author_id"])
        self.assertEqual(news["person"]["full_name"], "John Did")
        self.assertIn("has_avatar", news["person"])
