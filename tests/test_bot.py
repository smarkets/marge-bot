# pylint: disable=protected-access
from unittest.mock import MagicMock, patch

import pytest

from marge.bot import Bot
from marge.merge_request import MergeRequest


def _make_mr(labels=None):
    mr = MagicMock(spec=MergeRequest)
    mr.labels = labels or []
    return mr


class TestMergePriority:
    """Tests for merge_first label prioritization in Bot._process_merge_requests."""

    def setup_method(self, _method):
        self.api = MagicMock()
        config = MagicMock()
        config.batch = False
        self.config = config
        self.bot = Bot(api=self.api, config=config)
        self.bot._config.merge_opts = MagicMock()

    def _run_process(self, merge_requests):
        repo_manager = MagicMock()
        project = MagicMock()
        executed = []

        def fake_get_single_job(project, merge_request, repo, options):  # pylint: disable=unused-argument
            job = MagicMock()
            job.execute = MagicMock(side_effect=lambda: executed.append(merge_request))
            return job

        with patch.object(self.bot, '_get_single_job', side_effect=fake_get_single_job):
            self.bot._process_merge_requests(repo_manager, project, merge_requests)

        return executed

    def test_no_merge_first_picks_first_in_list(self):
        mr1 = _make_mr()
        mr2 = _make_mr()
        executed = self._run_process([mr1, mr2])
        assert executed == [mr1]

    def test_merge_first_label_jumps_to_front(self):
        mr_normal = _make_mr()
        mr_priority = _make_mr(labels=['merge_first'])
        executed = self._run_process([mr_normal, mr_priority])
        assert executed == [mr_priority]

    def test_first_merge_first_label_wins_when_multiple(self):
        mr_normal = _make_mr()
        mr_priority1 = _make_mr(labels=['merge_first'])
        mr_priority2 = _make_mr(labels=['merge_first', 'urgent'])
        executed = self._run_process([mr_normal, mr_priority1, mr_priority2])
        assert executed == [mr_priority1]

    def test_merge_first_among_other_labels(self):
        mr_normal = _make_mr()
        mr_priority = _make_mr(labels=['bug', 'merge_first', 'v2'])
        executed = self._run_process([mr_normal, mr_priority])
        assert executed == [mr_priority]

    def test_empty_merge_requests_does_nothing(self):
        repo_manager = MagicMock()
        project = MagicMock()
        # Should return early without error
        self.bot._process_merge_requests(repo_manager, project, [])
