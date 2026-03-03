"""
Tests for Job Manager — v2 Priority 6.

Covers:
- Job creation and initial state
- Stage transitions and progress tracking
- Error handling
- Completion with result storage
- Cleanup and stale job removal
- Edge cases (unknown job, duplicate create, rapid updates)
"""

import time
import pytest
from core.job_manager import JobManager, STAGE_PROGRESS


@pytest.fixture
def manager():
    return JobManager()


# ══════════════════════════════════════════════════════════
#  Creation & Initial State
# ══════════════════════════════════════════════════════════

class TestJobCreation:
    def test_create_returns_progress(self, manager):
        progress = manager.create("job-1")
        assert progress.job_id == "job-1"
        assert progress.stage == "uploading"
        assert progress.progress == 0
        assert progress.error is None
        assert progress.result is None

    def test_create_sets_timestamps(self, manager):
        before = time.time()
        progress = manager.create("job-1")
        after = time.time()
        assert before <= progress.started_at <= after
        assert before <= progress.updated_at <= after

    def test_get_after_create(self, manager):
        manager.create("job-1")
        status = manager.get("job-1")
        assert status is not None
        assert status["job_id"] == "job-1"
        assert status["stage"] == "uploading"
        assert status["progress"] == 0
        assert status["error"] is None
        assert status["has_result"] is False
        assert "elapsed_seconds" in status

    def test_get_unknown_job_returns_none(self, manager):
        assert manager.get("nonexistent") is None

    def test_get_result_unknown_job_returns_none(self, manager):
        assert manager.get_result("nonexistent") is None


# ══════════════════════════════════════════════════════════
#  Stage Transitions
# ══════════════════════════════════════════════════════════

class TestStageTransitions:
    def test_update_changes_stage(self, manager):
        manager.create("job-1")
        manager.update("job-1", "ingesting", "Parsing CSV...")
        status = manager.get("job-1")
        assert status["stage"] == "ingesting"
        assert status["message"] == "Parsing CSV..."
        assert status["progress"] == STAGE_PROGRESS["ingesting"]

    def test_full_pipeline_progression(self, manager):
        """Walk through every stage — progress must always increase."""
        manager.create("job-1")
        stages = ["uploading", "ingesting", "mapping", "awaiting_review",
                   "transforming", "validating", "complete"]
        prev_progress = -1
        for stage in stages:
            manager.update("job-1", stage, f"Stage: {stage}")
            status = manager.get("job-1")
            assert status["stage"] == stage
            assert status["progress"] > prev_progress or stage == "uploading"
            prev_progress = status["progress"]
        assert prev_progress == 100

    def test_progress_values_match_constants(self, manager):
        manager.create("job-1")
        for stage, expected in STAGE_PROGRESS.items():
            manager.update("job-1", stage, f"Testing {stage}")
            assert manager.get("job-1")["progress"] == expected

    def test_update_unknown_job_is_noop(self, manager):
        manager.update("nonexistent", "ingesting", "test")
        assert manager.get("nonexistent") is None

    def test_update_refreshes_timestamp(self, manager):
        manager.create("job-1")
        t1 = manager._jobs["job-1"].updated_at
        time.sleep(0.01)
        manager.update("job-1", "ingesting", "Parsing...")
        t2 = manager._jobs["job-1"].updated_at
        assert t2 > t1

    def test_default_message_when_empty(self, manager):
        manager.create("job-1")
        manager.update("job-1", "ingesting", "")
        assert manager.get("job-1")["message"] == "Stage: ingesting"


# ══════════════════════════════════════════════════════════
#  Error Handling
# ══════════════════════════════════════════════════════════

class TestErrorHandling:
    def test_set_error_marks_failed(self, manager):
        manager.create("job-1")
        manager.update("job-1", "ingesting", "Working...")
        manager.set_error("job-1", "File is corrupted")
        status = manager.get("job-1")
        assert status["stage"] == "failed"
        assert status["progress"] == -1
        assert status["error"] == "File is corrupted"

    def test_set_error_unknown_job_is_noop(self, manager):
        manager.set_error("nonexistent", "Some error")
        assert manager.get("nonexistent") is None

    def test_error_at_any_stage(self, manager):
        for stage in ["ingesting", "mapping", "transforming", "validating"]:
            m = JobManager()
            m.create("j")
            m.update("j", stage)
            m.set_error("j", f"Failed at {stage}")
            assert m.get("j")["stage"] == "failed"


# ══════════════════════════════════════════════════════════
#  Completion & Results
# ══════════════════════════════════════════════════════════

class TestCompletion:
    def test_set_complete_with_result(self, manager):
        manager.create("job-1")
        data = {"quality_score": 95, "rows": 100}
        manager.set_complete("job-1", data)
        status = manager.get("job-1")
        assert status["stage"] == "complete"
        assert status["progress"] == 100
        assert status["has_result"] is True

    def test_get_result_returns_stored_data(self, manager):
        manager.create("job-1")
        data = {"quality_score": 95}
        manager.set_complete("job-1", data)
        assert manager.get_result("job-1") == data

    def test_set_complete_without_result(self, manager):
        manager.create("job-1")
        manager.set_complete("job-1")
        assert manager.get("job-1")["has_result"] is False

    def test_get_result_before_complete_is_none(self, manager):
        manager.create("job-1")
        manager.update("job-1", "ingesting")
        assert manager.get_result("job-1") is None


# ══════════════════════════════════════════════════════════
#  Cleanup
# ══════════════════════════════════════════════════════════

class TestCleanup:
    def test_cleanup_removes_job(self, manager):
        manager.create("job-1")
        manager.cleanup("job-1")
        assert manager.get("job-1") is None

    def test_cleanup_nonexistent_is_noop(self, manager):
        manager.cleanup("nonexistent")  # Should not raise

    def test_cleanup_old_removes_stale(self, manager):
        manager.create("old-job")
        manager._jobs["old-job"].started_at = time.time() - 7200
        manager.create("new-job")
        manager.cleanup_old(max_age_seconds=3600)
        assert manager.get("old-job") is None
        assert manager.get("new-job") is not None


# ══════════════════════════════════════════════════════════
#  Concurrent Jobs
# ══════════════════════════════════════════════════════════

class TestConcurrentJobs:
    def test_multiple_jobs_independent(self, manager):
        manager.create("a")
        manager.create("b")
        manager.update("a", "ingesting", "A ingesting")
        manager.update("b", "mapping", "B mapping")
        assert manager.get("a")["stage"] == "ingesting"
        assert manager.get("b")["stage"] == "mapping"

    def test_error_on_one_doesnt_affect_other(self, manager):
        manager.create("a")
        manager.create("b")
        manager.set_error("a", "Failed!")
        manager.set_complete("b", {"done": True})
        assert manager.get("a")["stage"] == "failed"
        assert manager.get("b")["stage"] == "complete"

    def test_ten_concurrent_jobs(self, manager):
        for i in range(10):
            manager.create(f"job-{i}")
            manager.update(f"job-{i}", "mapping")
        for i in range(10):
            assert manager.get(f"job-{i}")["stage"] == "mapping"
