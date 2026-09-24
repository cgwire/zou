import unittest

from unittest.mock import MagicMock, patch

from nomad.api.exceptions import URLNotFoundNomadException

from zou.app.utils import remote_job


def complete_summary():
    return {"Summary": {"group": {"Failed": 0, "Lost": 0, "Complete": 1}}}


def running_summary():
    return {"Summary": {"group": {"Failed": 0, "Lost": 0, "Complete": 0}}}


class FakeJob:
    def __init__(self, meta=None):
        self.meta = dict(meta or {})
        self.saved_meta = None

    def save_meta(self):
        self.saved_meta = dict(self.meta)


class RunJobTestCase(unittest.TestCase):
    """
    A job waiting on Nomad hands the Nomad job over when its worker
    stops, and a resumed job watches the Nomad job it dispatched before.
    """

    def setUp(self):
        remote_job._handover_requested = False
        self.addCleanup(setattr, remote_job, "_handover_requested", False)
        self.app = MagicMock()
        self.config = MagicMock()
        self.config.__dict__ = {}
        self.ncli = MagicMock()
        self.ncli.job.dispatch_job.return_value = {
            "DispatchedJobID": "zou-tile/dispatch-1"
        }
        for target in [
            patch.object(remote_job.nomad, "Nomad", return_value=self.ncli),
            patch.object(
                remote_job.config_store, "get_nomad_host", return_value="h"
            ),
            patch.object(remote_job.time, "sleep"),
        ]:
            target.start()
            self.addCleanup(target.stop)

    def run_job(self, job):
        with patch.object(remote_job, "get_current_job", return_value=job):
            return remote_job.run_job(self.app, self.config, "zou-tile", {})

    def test_the_dispatched_nomad_job_is_recorded_on_the_rq_job(self):
        self.ncli.job.get_summary.return_value = complete_summary()
        job = FakeJob()
        self.assertTrue(self.run_job(job))
        self.assertEqual(
            job.saved_meta, {"nomad_job_id": "zou-tile/dispatch-1"}
        )

    def test_a_resumed_job_watches_the_same_nomad_job(self):
        self.ncli.job.get_summary.return_value = complete_summary()
        job = FakeJob({"nomad_job_id": "zou-tile/dispatch-0"})
        self.assertTrue(self.run_job(job))
        self.ncli.job.dispatch_job.assert_not_called()
        self.ncli.job.get_summary.assert_called_with("zou-tile/dispatch-0")

    def test_a_stop_while_waiting_hands_the_nomad_job_over(self):
        def summary(_):
            remote_job.request_handover()
            return running_summary()

        self.ncli.job.get_summary.side_effect = summary
        job = FakeJob()
        self.assertRaises(remote_job.NomadJobHandedOver, self.run_job, job)
        self.assertEqual(job.meta["nomad_job_id"], "zou-tile/dispatch-1")
        self.assertEqual(self.ncli.job.get_summary.call_count, 1)

    def test_a_stop_before_the_dispatch_dispatches_nothing(self):
        remote_job.request_handover()
        self.assertRaises(
            remote_job.NomadJobHandedOver, self.run_job, FakeJob()
        )
        self.ncli.job.dispatch_job.assert_not_called()

    def test_the_handover_is_not_caught_as_a_failure(self):
        self.assertFalse(issubclass(remote_job.NomadJobHandedOver, Exception))

    def test_a_resumed_job_forgotten_by_nomad_leaves_the_check_to_callers(
        self,
    ):
        self.ncli.job.get_summary.side_effect = URLNotFoundNomadException(
            MagicMock()
        )
        job = FakeJob({"nomad_job_id": "zou-tile/dispatch-0"})
        self.assertTrue(self.run_job(job))

    def test_a_fresh_job_unknown_to_nomad_fails(self):
        self.ncli.job.get_summary.side_effect = URLNotFoundNomadException(
            MagicMock()
        )
        self.assertRaises(URLNotFoundNomadException, self.run_job, FakeJob())

    def test_outside_of_rq_nothing_is_recorded(self):
        self.ncli.job.get_summary.return_value = complete_summary()
        self.assertTrue(self.run_job(None))
        self.assertFalse(remote_job.is_resumed())
