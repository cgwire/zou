import io
import uuid

from contextlib import redirect_stdout
from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.commands import (
    sync_verify_service,
)


class VerifyProjectSyncTestCase(ApiDBTestCase):
    """
    The read-only row count comparison run after a sync. It prints a table,
    so the report itself is what the tests read.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def verify(self, project_name=None, remote_id=None, direction="pull"):
        """
        Run the report against a remote holding nothing, and return the
        lines it printed keyed by model.
        """
        if project_name is None:
            project_name = self.project.name
        if remote_id is None:
            remote_id = str(self.project.id)
        output = io.StringIO()
        with mock.patch.object(
            sync_verify_service.gazu.project,
            "get_project_by_name",
            return_value={"id": remote_id, "name": project_name},
        ), mock.patch.object(
            sync_verify_service.gazu.client, "fetch_all", return_value=[]
        ), redirect_stdout(
            output
        ):
            sync_verify_service.verify_project_sync(
                project_name, direction=direction
            )
        return output.getvalue()

    def row(self, report, label):
        for line in report.splitlines():
            if line.startswith(label):
                return line.split()
        return None

    def test_every_target_counter_compiles(self):
        """
        Every target side count helper must produce valid SQL on the current
        schema: a helper joining on a column that moved raises here rather
        than in front of the operator running the verification.
        """
        pid = str(self.project.id)
        counters = [
            sync_verify_service._tgt_entity_type(pid, "Shot"),
            sync_verify_service._tgt_entity_type(pid, "Sequence"),
            sync_verify_service._tgt_entity_type(pid, "Episode"),
            sync_verify_service._tgt_entity_type(pid, "Concept"),
            sync_verify_service._tgt_asset(pid),
            sync_verify_service._tgt_entity_link(pid),
            sync_verify_service._tgt_comment(pid),
            sync_verify_service._tgt_time_spent(pid),
            sync_verify_service._tgt_preview_file(pid),
            sync_verify_service._tgt_build_job(pid),
            sync_verify_service._tgt_attachment_file(pid),
            sync_verify_service._tgt_subscription(pid),
            sync_verify_service._tgt_notification(pid),
            sync_verify_service._tgt_news(pid),
            sync_verify_service._tgt_output_file(pid),
            sync_verify_service._tgt_working_file(pid),
            sync_verify_service._tgt_asset_instance(pid),
            sync_verify_service._tgt_chat(pid),
            sync_verify_service._tgt_budget_entry(pid),
            sync_verify_service._tgt_share_link(pid),
        ]
        for counter in counters:
            self.assertIsInstance(counter(), int)

    def test_an_asset_is_an_entity_of_no_structural_type(self):
        """
        Assets have no type of their own: they are counted by exclusion, so
        a shot and a sequence must not land in their row.
        """
        pid = str(self.project.id)
        self.assertEqual(sync_verify_service._tgt_asset(pid)(), 1)
        self.assertEqual(
            sync_verify_service._tgt_entity_type(pid, "Shot")(), 1
        )
        self.assertEqual(
            sync_verify_service._tgt_entity_type(pid, "Sequence")(), 1
        )

    def test_a_type_absent_from_this_instance_counts_as_zero(self):
        self.assertEqual(
            sync_verify_service._tgt_entity_type(
                str(self.project.id), "Concept"
            )(),
            0,
        )

    def test_a_pull_reads_the_remote_as_the_source(self):
        """
        After a sync-full the remote is where the rows come from, so the
        local extras show up as a positive delta.
        """
        self.assertEqual(
            self.row(self.verify(), "Asset"), ["Asset", "0", "1", "+1", "DIFF"]
        )

    def test_a_push_reads_the_local_instance_as_the_source(self):
        """
        Same two counts, read the other way round: sync-push sends the local
        rows out, so what the remote is missing is a negative delta.
        """
        self.assertEqual(
            self.row(self.verify(direction="push"), "Asset"),
            ["Asset", "1", "0", "-1", "DIFF"],
        )

    def test_a_table_out_of_scope_is_named_rather_than_compared(self):
        """
        A table the sync does not migrate holds the same count on both sides
        only because both are empty. Reading that as a match would tell the
        operator the transfer is complete when it never started.
        """
        self.assertEqual(
            self.row(self.verify(), "Budget"),
            ["Budget", "0", "0", "+0", "NOT", "SYNCED"],
        )

    def test_a_production_missing_locally_is_reported(self):
        report = self.verify(
            project_name="Elsewhere", remote_id=str(uuid.uuid4())
        )
        self.assertIn("not present locally", report)
        self.assertNotIn("Delta", report)

    def test_a_production_missing_on_the_remote_is_reported(self):
        output = io.StringIO()
        with mock.patch.object(
            sync_verify_service.gazu.project,
            "get_project_by_name",
            return_value=None,
        ), redirect_stdout(output):
            sync_verify_service.verify_project_sync("Elsewhere")
        self.assertIn("not found on source", output.getvalue())

    def test_an_unreachable_remote_is_reported_as_such(self):
        """
        Not as an absent production, and not as the AttributeError raised
        by an except clause naming an exception gazu does not define.
        """
        output = io.StringIO()
        with mock.patch.object(
            sync_verify_service.gazu.project,
            "get_project_by_name",
            side_effect=Exception("connection refused"),
        ), redirect_stdout(output):
            sync_verify_service.verify_project_sync("Elsewhere")
        self.assertIn("Could not reach", output.getvalue())

    def test_an_unreachable_count_does_not_abort_the_report(self):
        """
        One route the remote does not serve must leave the other rows
        readable: the point of the report is to find what is missing.
        """
        output = io.StringIO()
        with mock.patch.object(
            sync_verify_service.gazu.project,
            "get_project_by_name",
            return_value={
                "id": str(self.project.id),
                "name": self.project.name,
            },
        ), mock.patch.object(
            sync_verify_service.gazu.client,
            "fetch_all",
            side_effect=Exception("connection refused"),
        ), redirect_stdout(
            output
        ):
            sync_verify_service.verify_project_sync(self.project.name)
        self.assertEqual(
            self.row(output.getvalue(), "Asset"),
            ["Asset", "N/A", "1", "-", "ok"],
        )
