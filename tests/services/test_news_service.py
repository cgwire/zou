from datetime import datetime, timedelta

from freezegun import freeze_time

from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.models.news import News
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.services import (
    comments_service,
    news_service,
    projects_service,
)

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class NewsWritingTestCase(ApiDBTestCase):
    """
    A news is the trace a comment leaves on the activity feed: written with
    the comment, and taken away before the comment can be.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_commented_shot_task()

    def test_create_news(self):
        news = news_service.create_news(
            comment_id=self.comment["id"],
            author_id=self.comment["person_id"],
            task_id=self.comment["object_id"],
            change=True,
        )

        stored = News.get(news["id"])
        self.assertEqual(str(stored.comment_id), self.comment["id"])
        self.assertEqual(str(stored.author_id), self.comment["person_id"])
        self.assertEqual(str(stored.task_id), self.comment["object_id"])
        self.assertTrue(stored.change)

    def test_create_news_for_task_and_comment(self):
        news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )

        news_list = News.get_all()
        self.assertEqual(len(news_list), 1)
        self.assertEqual(str(news_list[0].author_id), self.user["id"])
        self.assertEqual(str(news_list[0].task_id), self.task_dict["id"])
        self.assertEqual(str(news_list[0].comment_id), self.comment["id"])
        # A plain comment is not a change: only the ones that move a status
        # are counted by the stats.
        self.assertFalse(news_list[0].change)

    def test_creating_from_a_comment_announces_the_news(self):
        captured = self.capture_events("news:new")

        news = news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )

        self.assertEqual(len(captured), 1)
        self.assertEqual(
            (
                captured[0]["news_id"],
                captured[0]["task_status_id"],
                captured[0]["task_type_id"],
                captured[0]["project_id"],
            ),
            (
                news["id"],
                self.comment["task_status_id"],
                self.task_dict["task_type_id"],
                self.task_dict["project_id"],
            ),
        )

    def test_delete_news_for_comment(self):
        news = news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )

        deleted = news_service.delete_news_for_comment(self.comment["id"])

        self.assertEqual([row["id"] for row in deleted], [news["id"]])
        self.assertEqual(News.get_all(), [])

    def test_delete_news_for_a_comment_that_left_none(self):
        self.assertEqual(
            news_service.delete_news_for_comment(self.comment["id"]), []
        )

    def test_deleting_drops_the_memoized_news(self):
        """
        The single-news route reads through a memoized get_news. Deleting
        the comment has to drop that entry, or the news outlives it for the
        length of the TTL.
        """
        news = news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )
        project_id = self.task_dict["project_id"]
        self.assertEqual(
            len(news_service.get_news(project_id, news["id"])["data"]), 1
        )

        news_service.delete_news_for_comment(self.comment["id"])

        self.assertEqual(
            news_service.get_news(project_id, news["id"])["data"], []
        )

    def test_deleting_announces_the_news_it_took_away(self):
        news = news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )
        captured = self.capture_events("news:delete")

        news_service.delete_news_for_comment(self.comment["id"])

        self.assertEqual(
            [(event["news_id"], event["project_id"]) for event in captured],
            [(news["id"], self.task_dict["project_id"])],
        )


# Frozen mid-day: the date filters below are built from now(), which flakes
# around midnight otherwise.
@freeze_time("2026-07-06T12:00:00")
class NewsListingTestCase(ApiDBTestCase):
    """
    The activity feed. One query joins everything the display needs, so the
    listing is read once for its shape and once per filter the interface
    offers.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_commented_shot_task()
        self.project_id = self.task_dict["project_id"]

    def a_news(self, text="comment", author_id=None, status=None, **kwargs):
        """
        One entry of the feed, made the way the application makes them.
        """
        comment = comments_service.new_comment(
            self.task.id,
            (status or self.task_status).id,
            author_id or self.user["id"],
            text,
        )
        return news_service.create_news_for_task_and_comment(
            self.task_dict, comment, **kwargs
        )

    def a_news_elsewhere(self):
        """
        One entry belonging to another production, built by hand: the
        fixture generators repoint self.project on their way, and
        everything set up above belongs to the first one.
        """
        project = Project.create(name="Another Production")
        shot = Entity.create(
            name="P01",
            project_id=project.id,
            entity_type_id=self.shot_type.id,
        )
        task = Task.create(
            name="main",
            project_id=project.id,
            entity_id=shot.id,
            task_type_id=self.task_type_animation.id,
            task_status_id=self.task_status.id,
        )
        comment = comments_service.new_comment(
            task.id, self.task_status.id, self.user["id"], "elsewhere"
        )
        return news_service.create_news_for_task_and_comment(
            task.serialize(), comment
        )

    def days_ago(self, days):
        return datetime.now() - timedelta(days=days)

    def listing(self, **kwargs):
        return news_service.get_last_news_for_project(
            project_id=self.project_id, **kwargs
        )

    def ids(self, **kwargs):
        return [entry["id"] for entry in self.listing(**kwargs)["data"]]

    def test_the_listing_carries_what_the_feed_displays(self):
        news = self.a_news()

        entry = self.listing()["data"][0]

        self.assertEqual(entry["id"], news["id"])
        self.assertEqual(entry["project_id"], self.project_id)
        self.assertEqual(entry["project_name"], "Cosmos Landromat")
        self.assertEqual(entry["full_entity_name"], "E01 / S01 / P01")
        self.assertEqual(entry["episode_id"], str(self.episode.id))
        self.assertEqual(entry["task_id"], self.task_dict["id"])
        self.assertEqual(entry["task_type_id"], self.task_dict["task_type_id"])
        self.assertEqual(entry["task_status_id"], str(self.task_status.id))
        self.assertEqual(entry["task_entity_id"], str(self.shot.id))
        # The author is embedded so a guest author renders without a second
        # round trip.
        self.assertEqual(entry["person"]["id"], self.user["id"])

    def test_the_listing_is_newest_first(self):
        older = self.a_news("older", created_at=self.days_ago(2))
        newest = self.a_news("newest", created_at=self.days_ago(0))
        middle = self.a_news("middle", created_at=self.days_ago(1))

        self.assertEqual(self.ids(), [newest["id"], middle["id"], older["id"]])

    def test_the_listing_pages(self):
        news = [
            self.a_news(f"comment {day}", created_at=self.days_ago(day))
            for day in range(5)
        ]

        first = self.listing(limit=2)
        second = self.listing(limit=2, page=2)

        self.assertEqual((first["total"], first["nb_pages"]), (5, 3))
        self.assertEqual((first["page"], first["offset"]), (1, 0))
        self.assertEqual((second["page"], second["offset"]), (2, 2))
        self.assertEqual(
            [entry["id"] for entry in first["data"] + second["data"]],
            [entry["id"] for entry in news[:4]],
        )

    def test_the_listing_holds_one_named_news(self):
        news = self.a_news("wanted")
        self.a_news("other")

        self.assertEqual(self.ids(news_id=news["id"]), [news["id"]])

    def test_the_listing_holds_the_news_of_one_entity(self):
        news = self.a_news()

        self.assertEqual(self.ids(entity_id=str(self.shot.id)), [news["id"]])
        # The sequence is the shot's parent, not what the task is on.
        self.assertEqual(self.ids(entity_id=str(self.sequence.id)), [])

    def test_get_news_for_entity(self):
        news = self.a_news()

        result = news_service.get_news_for_entity(str(self.shot.id))

        self.assertEqual(
            [entry["id"] for entry in result["data"]], [news["id"]]
        )

    def test_the_listing_holds_the_news_of_one_author(self):
        mine = self.a_news("mine")
        self.a_news("hers", author_id=str(self.person.id))

        self.assertEqual(self.ids(author_id=self.user["id"]), [mine["id"]])

    def test_the_listing_holds_the_news_of_one_status(self):
        self.generate_fixture_task_status_wip()
        opened = self.a_news("open")
        self.a_news("wip", status=self.task_status_wip)

        self.assertEqual(
            self.ids(task_status_id=str(self.task_status.id)), [opened["id"]]
        )

    def test_the_listing_holds_the_news_of_one_task_type(self):
        news = self.a_news()

        self.assertEqual(
            self.ids(task_type_id=self.task_dict["task_type_id"]),
            [news["id"]],
        )
        self.assertEqual(self.ids(task_type_id=UNKNOWN), [])

    def test_the_listing_holds_the_news_that_carry_a_preview(self):
        preview_file = self.generate_fixture_preview_file()
        self.a_news("without")
        with_preview = news_service.create_news(
            comment_id=self.comment["id"],
            author_id=self.user["id"],
            task_id=self.task_dict["id"],
            preview_file_id=preview_file.id,
        )

        result = self.listing(only_preview=True)

        self.assertEqual(
            [entry["id"] for entry in result["data"]], [with_preview["id"]]
        )
        entry = result["data"][0]
        self.assertEqual(entry["preview_file_extension"], "mp4")
        self.assertEqual(entry["preview_file_revision"], 1)
        # The whole revision is attached, so a multi-part preview shows all
        # of its files.
        self.assertEqual(
            [held["id"] for held in entry["preview_files"]],
            [str(preview_file.id)],
        )

    def test_the_listing_holds_the_news_of_one_episode(self):
        news = self.a_news()

        self.assertEqual(
            self.ids(episode_id=str(self.episode.id)), [news["id"]]
        )
        self.assertEqual(self.ids(episode_id=UNKNOWN), [])

    def test_the_listing_is_bounded_by_dates(self):
        for day in range(1, 7):
            self.a_news(f"comment {day}", created_at=self.days_ago(day))
        # Midnight of the day before yesterday: two news are after it.
        date = self.days_ago(2).strftime("%Y-%m-%d")

        self.assertEqual(len(self.listing()["data"]), 6)
        self.assertEqual(len(self.listing(after=date)["data"]), 2)
        self.assertEqual(len(self.listing(before=date)["data"]), 4)

    def test_the_listing_is_scoped_to_its_production(self):
        news = self.a_news()
        self.a_news_elsewhere()

        self.assertEqual(self.ids(), [news["id"]])

    def test_the_listing_is_held_to_the_allowed_productions(self):
        """
        project_ids is the caller's allowlist, and it is checked on its own:
        asking for a production outside it returns nothing, whatever
        project_id says.
        """
        news = self.a_news()

        self.assertEqual(self.ids(project_ids=[self.project_id]), [news["id"]])
        self.assertEqual(self.ids(project_ids=[UNKNOWN]), [])

    def test_without_an_allowlist_a_person_sees_their_own_productions(self):
        news = self.a_news()

        self.assertEqual(self.ids(current_user=self.person), [])

        projects_service.add_team_member(self.project_id, str(self.person.id))

        self.assertEqual(self.ids(current_user=self.person), [news["id"]])


@freeze_time("2026-07-06T12:00:00")
class NewsStatsTestCase(ApiDBTestCase):
    """
    The counters above the feed: how many status changes per status. They
    share their filters with the listing, so only what is theirs is read
    here.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_commented_shot_task()
        self.generate_fixture_task_status_wip()
        self.project_id = self.task_dict["project_id"]

    def a_news(self, status, change):
        comment = comments_service.new_comment(
            self.task.id, status.id, self.user["id"], "comment"
        )
        return news_service.create_news_for_task_and_comment(
            self.task_dict, comment, change=change
        )

    def test_the_stats_count_the_changes_by_status(self):
        self.a_news(self.task_status, change=True)
        self.a_news(self.task_status, change=True)
        self.a_news(self.task_status_wip, change=True)
        # A comment that moved nothing is not a change.
        self.a_news(self.task_status_wip, change=False)

        stats = news_service.get_news_stats_for_project(
            project_id=self.project_id
        )

        self.assertEqual(
            stats,
            {
                str(self.task_status.id): 2,
                str(self.task_status_wip.id): 1,
            },
        )

    def test_the_stats_take_the_same_filters_as_the_listing(self):
        self.a_news(self.task_status, change=True)

        self.assertEqual(
            news_service.get_news_stats_for_project(
                project_id=self.project_id, project_ids=[UNKNOWN]
            ),
            {},
        )
        self.assertEqual(
            news_service.get_news_stats_for_project(
                project_id=self.project_id, current_user=self.person
            ),
            {},
        )
