import os
import tempfile

from tests.base import ApiDBTestCase
from zou.app.models.comment import Comment
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import projects_service, shots_service


class ImportCsvEpisodesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.project.update({"production_type": "tvshow"})
        self.path = f"/import/csv/projects/{self.project.id}/episodes"

    def write_csv(self, content):
        descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        self.addCleanup(os.remove, file_path)
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def get_episodes(self):
        return shots_service.get_episodes({"project_id": self.project.id})

    def test_import_episodes(self):
        self.upload_file(
            self.path, self.write_csv("Name,Description\nE01,Pilot\n")
        )

        self.assertEqual(
            [
                (episode["name"], episode["description"], episode["status"])
                for episode in self.get_episodes()
            ],
            [("E01", "Pilot", "running")],
        )

    def test_import_reads_a_file_of_a_single_column(self):
        # The delimiter sniffer finds none in such a file: it gave up, or
        # took a letter for one.
        self.upload_file(self.path, self.write_csv("Name\nE01\nE02\n"))
        self.upload_file(self.path, self.write_csv("Name\nOpening\n"))

        self.assertEqual(
            [episode["name"] for episode in self.get_episodes()],
            ["E01", "E02", "Opening"],
        )

    def test_import_reads_a_quoted_single_column(self):
        # The sniffer takes the quote of such a file for its delimiter, which
        # Python 3.13 refuses. Kitsu quotes every cell it uploads.
        self.upload_file(
            self.path, self.write_csv('"Name"\n"E;01"\n"L\'éveil"\n')
        )
        self.upload_file(self.path, self.write_csv("'Name'\n'E02'\n"))

        self.assertEqual(
            sorted(episode["name"] for episode in self.get_episodes()),
            ["E02", "E;01", "L'éveil"],
        )

    def test_a_quoted_single_column_keeps_the_delimiters_of_its_cells(self):
        # A doubled quote in a name makes the sniffer take a letter for the
        # delimiter: the comma of a quoted cell holds no doubt.
        names = ['"Episode 1 ""Pilot"""'] + [
            f'"Episode {number}"' for number in range(2, 12)
        ]
        lines = ['"Name"'] + names + ['"Episode 12, part 2"']
        self.upload_file(self.path, self.write_csv("\n".join(lines) + "\n"))

        self.assertEqual(len(self.get_episodes()), 12)

    def test_import_sniffs_the_other_usual_delimiters(self):
        self.upload_file(
            self.path, self.write_csv("Name:Description\nE01:Pilot\n")
        )
        self.upload_file(
            self.path, self.write_csv("Name Description\nE02 Finale\n")
        )

        self.assertEqual(
            [
                (episode["name"], episode["description"])
                for episode in self.get_episodes()
            ],
            [("E01", "Pilot"), ("E02", "Finale")],
        )

    def test_import_reads_the_header_as_the_first_record(self):
        # Not as the first line: a pandas index writes an empty first header,
        # and a quoted header can hold a line break.
        self.upload_file(self.path, self.write_csv("\tName\n0\tE01\n"))
        self.upload_file(
            self.path, self.write_csv('"Note\n(free)";"Name"\n"x";"E02"\n')
        )

        self.assertEqual(
            [episode["name"] for episode in self.get_episodes()],
            ["E01", "E02"],
        )

    def test_import_reads_a_tilde_delimiter(self):
        self.upload_file(
            self.path, self.write_csv("Name~Description\nE01~Pilot\n")
        )

        self.assertEqual(
            [
                (episode["name"], episode["description"])
                for episode in self.get_episodes()
            ],
            [("E01", "Pilot")],
        )

    def test_import_reads_a_byte_order_mark(self):
        # Excel starts a "CSV UTF-8" file with one.
        self.upload_file(
            self.path, self.write_csv("\ufeffName,Description\nE01,Pilot\n")
        )
        self.upload_file(self.path, self.write_csv("\ufeffName\nE02\n"))

        self.assertEqual(
            [
                (episode["name"], episode["description"])
                for episode in self.get_episodes()
            ],
            [("E01", "Pilot"), ("E02", "")],
        )

    def test_a_file_in_another_encoding_is_refused(self):
        # Spreadsheets save a plain "CSV" in the encoding of the system, such
        # as Windows-1252. Nothing is imported, even from the lines before
        # the first byte that is not UTF-8.
        lines = "".join(
            f"E{number:02d},{'x' * 1000}\n" for number in range(10)
        )
        for content in (
            "Name\nSéquence\n",
            "Name,Description\n" + lines + "E10,Séquence\n",
        ):
            with self.subTest(lines=content.count("\n")):
                descriptor, file_path = tempfile.mkstemp(suffix=".csv")
                self.addCleanup(os.remove, file_path)
                with os.fdopen(descriptor, "wb") as f:
                    f.write(content.encode("cp1252"))
                result = self.upload_file(self.path, file_path, code=400)
                self.assertEqual(
                    result["message"], "The file is not encoded in UTF-8"
                )
        self.assertEqual(self.get_episodes(), [])

    def test_a_line_wider_than_its_header_is_not_a_single_column(self):
        self.upload_file(self.path, self.write_csv('"Name"\n"E01";"Pilot"\n'))

        self.assertEqual(
            [episode["name"] for episode in self.get_episodes()], ["E01"]
        )

    def test_a_single_column_after_a_blank_line_is_refused(self):
        # Read as the header, it leaves no column to the lines, which would
        # then import nothing without a word.
        for content in ("\nName\nE01\n", '\n"Name"\n"E01"\n'):
            with self.subTest(content=content):
                result = self.upload_file(
                    self.path, self.write_csv(content), code=400
                )
                self.assertEqual(
                    result["message"], "Could not determine delimiter"
                )
        self.assertEqual(self.get_episodes(), [])

    def test_an_unquoted_delimiter_under_a_header_of_one_is_refused(self):
        # "E01;Pilot" can be a name, or two cells under a header of one,
        # wherever the line is: the sniffer reads the first lines only, and
        # takes "E" for the delimiter of the longer files here.
        names = "".join(f"E{number:02d}\n" for number in range(2, 31))
        for content in (
            "Name\nE01;Pilot\n",
            "Name\nE01;Pilot\n" + names,
            "Name\n" + names * 100 + "E01;Pilot\n",
        ):
            with self.subTest(lines=content.count("\n")):
                result = self.upload_file(
                    self.path, self.write_csv(content), code=400
                )
                self.assertEqual(
                    result["message"], "Could not determine delimiter"
                )
        self.assertEqual(self.get_episodes(), [])

    def test_a_quote_left_open_is_refused(self):
        # Read as it is, the file merges the next lines into one name,
        # whether the sniffer gives up, takes the quote for the delimiter, or
        # takes a letter and skips the spaces before a quote.
        quoted = "".join(f'"E{number:02d}"\n' for number in range(1, 21))
        for content in (
            'Name\n"Pilot\nE02\nE03\n',
            '"Name"\n"E01\n"E02"\n"E03"\n',
            '"Name"\n' + quoted + '"E21\n"E22"\n"E23"\n',
            "Name\n" + quoted + '  "E21\nE22\nE23\n',
        ):
            with self.subTest(content=content):
                result = self.upload_file(
                    self.path, self.write_csv(content), code=400
                )
                self.assertEqual(
                    result["message"], "Could not determine delimiter"
                )
        self.assertEqual(self.get_episodes(), [])

    def test_a_unit_separator_out_of_quotes_is_refused(self):
        # A single column reads with this control character as delimiter: the
        # import would drop the rest of its line without a word.
        names = "".join(f"E{number:02d}\n" for number in range(1, 21))
        for content in (
            "Name\nE01\x1fPilot\n",
            "Name\n" + names + 'E21\x1f"E22\nE23\nE24\n',
        ):
            with self.subTest(content=content):
                result = self.upload_file(
                    self.path, self.write_csv(content), code=400
                )
                self.assertEqual(
                    result["message"], "Could not determine delimiter"
                )
        self.assertEqual(self.get_episodes(), [])

    def test_import_reads_the_status_in_any_case(self):
        self.upload_file(
            self.path,
            self.write_csv("Name,Status\nE01,Complete\nE02, standby\nE03,\n"),
        )

        self.assertEqual(
            [
                (episode["name"], episode["status"])
                for episode in self.get_episodes()
            ],
            [("E01", "complete"), ("E02", "standby"), ("E03", "running")],
        )

    def test_an_unknown_status_is_refused(self):
        # It became "running" without a word.
        result = self.upload_file(
            self.path,
            self.write_csv("Name,Status\nE01,running\nE02,En cours\n"),
            code=400,
        )

        self.assertEqual(result["line_number"], 3)
        self.assertEqual(
            result["message"], "Episode status not found for En cours"
        )
        self.assertEqual(result["imported_rows"], 1)
        self.assertEqual(
            [episode["name"] for episode in self.get_episodes()], ["E01"]
        )

    def test_an_existing_episode_changes_with_the_update_option_only(self):
        self.upload_file(self.path, self.write_csv("Name,Status\nE01,\n"))
        self.upload_file(
            self.path, self.write_csv("Name,Status\nE01,canceled\n")
        )
        self.assertEqual(
            [episode["status"] for episode in self.get_episodes()],
            ["running"],
        )

        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv("Name,Status\nE01,canceled\n"),
        )
        self.assertEqual(
            [episode["status"] for episode in self.get_episodes()],
            ["canceled"],
        )

        # An empty status cell leaves the status as it is.
        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv("Name,Status,Description\nE01,,Night\n"),
        )
        self.assertEqual(
            [
                (episode["status"], episode["description"])
                for episode in self.get_episodes()
            ],
            [("canceled", "Night")],
        )

    def test_import_is_refused_outside_a_tv_show(self):
        self.project.update({"production_type": "short"})
        result = self.upload_file(
            self.path, self.write_csv("Name\nE01\n"), code=400
        )

        self.assertEqual(
            result["message"], "Episodes can only be imported in a TV show"
        )
        self.assertEqual(self.get_episodes(), [])

    def test_a_line_without_name_is_refused(self):
        result = self.upload_file(
            self.path, self.write_csv("Name,Description\n,Pilot\n"), code=400
        )

        self.assertEqual(result["message"], "Name cannot be empty")
        self.assertEqual(self.get_episodes(), [])

    def test_import_reads_the_metadata_columns(self):
        self.generate_fixture_metadata_descriptor(entity_type="Episode")
        self.upload_file(
            self.path, self.write_csv("Name,Contractor\nE01,value 1\n")
        )

        self.assertEqual(
            self.get_episodes()[0]["data"], {"contractor": "value 1"}
        )

    def test_import_sets_the_status_comment_and_assignees_of_a_task(self):
        task_type = TaskType.create(
            name="Script",
            short_name="scr",
            color="#FFFFFF",
            for_entity="Episode",
        )
        projects_service.add_task_type_setting(self.project.id, task_type.id)
        self.generate_fixture_task_status_wip()
        self.generate_fixture_person()
        self.upload_file(
            self.path,
            self.write_csv(
                "Name,Script,Script comment,Script assignations\n"
                "E01,wip,First draft,John Doe\n"
                "E02,,,\n"
            ),
        )

        tasks = {
            shots_service.get_episode(str(task.entity_id))["name"]: task
            for task in Task.query.all()
        }
        self.assertEqual(sorted(tasks), ["E01", "E02"])
        self.assertEqual(tasks["E01"].task_type_id, task_type.id)
        self.assertEqual(tasks["E01"].task_status_id, self.task_status_wip.id)
        self.assertEqual(
            [person.id for person in tasks["E01"].assignees],
            [self.person.id],
        )
        self.assertEqual(
            [comment.text for comment in Comment.query.all()], ["First draft"]
        )

    def test_an_update_assigns_only_the_people_not_yet_assigned(self):
        task_type = TaskType.create(
            name="Script",
            short_name="scr",
            color="#FFFFFF",
            for_entity="Episode",
        )
        projects_service.add_task_type_setting(self.project.id, task_type.id)
        self.generate_fixture_person()
        self.upload_file(
            self.path,
            self.write_csv("Name,Script assignations\nE01,John Doe\n"),
        )

        assigned = self.capture_events("task:assign")
        self.upload_file(
            f"{self.path}?update=true",
            self.write_csv(
                'Name,Script assignations\nE01,"John Doe, John Did"\n'
            ),
        )

        self.assertEqual(
            [str(event["person_id"]) for event in assigned], [self.user["id"]]
        )
        self.assertEqual(
            sorted(str(person.id) for person in Task.query.one().assignees),
            sorted([str(self.person.id), self.user["id"]]),
        )
