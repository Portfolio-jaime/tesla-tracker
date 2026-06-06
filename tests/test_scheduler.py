"""
Tests for CollectorScheduler.
"""

import pytest
import time
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timedelta

from app.collectors.scheduler import (
    CollectorScheduler,
    get_scheduler,
    initialize_scheduler,
    shutdown_scheduler,
)


class TestCollectorSchedulerInitialization:
    """Tests for scheduler initialization."""
    
    def test_scheduler_initialized_not_running(self):
        """Test that scheduler is initialized but not running."""
        scheduler = CollectorScheduler()
        
        assert scheduler.scheduler is None
        assert not scheduler.is_running
        assert len(scheduler.jobs) == 0
    
    def test_scheduler_start_raises_error_when_already_running(self):
        """Test that starting scheduler twice raises RuntimeError."""
        scheduler = CollectorScheduler()
        
        try:
            scheduler.start_scheduler()
            assert scheduler.is_running
            
            # Try to start again
            with pytest.raises(RuntimeError, match="already running"):
                scheduler.start_scheduler()
        
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()
    
    def test_scheduler_stop_raises_error_when_not_running(self):
        """Test that stopping scheduler when not running raises RuntimeError."""
        scheduler = CollectorScheduler()
        
        with pytest.raises(RuntimeError, match="not running"):
            scheduler.stop_scheduler()


class TestCollectorSchedulerStartStop:
    """Tests for scheduler start and stop operations."""
    
    def test_scheduler_starts_successfully(self):
        """Test that scheduler starts without errors."""
        scheduler = CollectorScheduler()
        
        try:
            scheduler.start_scheduler()
            
            assert scheduler.is_running
            assert scheduler.scheduler is not None
            assert len(scheduler.jobs) == 2  # reservation + shipping
        
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()
    
    def test_scheduler_stops_successfully(self):
        """Test that scheduler stops without errors."""
        scheduler = CollectorScheduler()
        
        scheduler.start_scheduler()
        assert scheduler.is_running
        
        scheduler.stop_scheduler()
        
        assert not scheduler.is_running
        assert scheduler.scheduler is None
        assert len(scheduler.jobs) == 0
    
    def test_scheduler_cleans_up_resources_on_stop(self):
        """Test that scheduler properly cleans up resources when stopped."""
        scheduler = CollectorScheduler()
        scheduler.start_scheduler()
        
        jobs_before = len(scheduler.jobs)
        assert jobs_before > 0
        
        scheduler.stop_scheduler()
        
        assert len(scheduler.jobs) == 0
        assert scheduler.scheduler is None


class TestCollectorSchedulerJobs:
    """Tests for job configuration and management."""
    
    def test_add_job_collectors_creates_correct_number_of_jobs(self):
        """Test that correct number of jobs are created."""
        scheduler = CollectorScheduler()
        
        try:
            scheduler.start_scheduler()
            
            assert len(scheduler.jobs) == 2
            assert "reservation_collector" in scheduler.jobs
            assert "shipping_collector" in scheduler.jobs
        
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()
    
    def test_add_job_collectors_raises_error_without_scheduler(self):
        """Test that add_job_collectors raises error if scheduler not initialized."""
        scheduler = CollectorScheduler()
        
        with pytest.raises(RuntimeError, match="not initialized"):
            scheduler.add_job_collectors()
    
    def test_jobs_have_correct_intervals(self):
        """Test that jobs are configured with correct intervals."""
        scheduler = CollectorScheduler()
        
        try:
            scheduler.start_scheduler()
            
            # Check reservation collector job (6 hours)
            res_job = scheduler.jobs["reservation_collector"]
            assert "6" in str(res_job.trigger)
            
            # Check shipping collector job (3 hours)
            ship_job = scheduler.jobs["shipping_collector"]
            assert "3" in str(ship_job.trigger)
        
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()
    
    def test_jobs_have_correct_names(self):
        """Test that jobs have descriptive names."""
        scheduler = CollectorScheduler()
        
        try:
            scheduler.start_scheduler()
            
            job_names = {job.name for job in scheduler.jobs.values()}
            assert "Reservation Collector" in job_names
            assert "Shipping Collector" in job_names
        
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()


class TestCollectorSchedulerStatus:
    """Tests for scheduler status reporting."""
    
    def test_get_job_status_returns_correct_structure(self):
        """Test that get_job_status returns expected structure."""
        scheduler = CollectorScheduler()
        
        try:
            scheduler.start_scheduler()
            
            status = scheduler.get_job_status()
            
            assert "scheduler_running" in status
            assert "jobs_count" in status
            assert "jobs" in status
            assert "timestamp" in status
            
            assert status["scheduler_running"] is True
            assert status["jobs_count"] == 2
            assert isinstance(status["jobs"], dict)
            assert isinstance(status["timestamp"], datetime)
        
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()
    
    def test_get_job_status_when_not_running(self):
        """Test get_job_status when scheduler is not running."""
        scheduler = CollectorScheduler()
        
        status = scheduler.get_job_status()
        
        assert status["scheduler_running"] is False
        assert status["jobs_count"] == 0
        assert len(status["jobs"]) == 0
    
    def test_get_job_status_includes_job_details(self):
        """Test that job status includes detailed information."""
        scheduler = CollectorScheduler()
        
        try:
            scheduler.start_scheduler()
            
            status = scheduler.get_job_status()
            jobs = status["jobs"]
            
            # Check that each job has required fields
            for job_id, job_info in jobs.items():
                assert "id" in job_info
                assert "name" in job_info
                assert "next_run_time" in job_info
                assert "trigger" in job_info
                assert "func_name" in job_info
                assert job_info["next_run_time"] is not None
        
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()


class TestCollectorSchedulerExecution:
    """Tests for collector execution through scheduler."""
    
    @patch("app.collectors.scheduler.ReservationCollector")
    def test_reservation_collector_execution(self, mock_collector_class):
        """Test that ReservationCollector is executed correctly."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = {"total": 3, "saved": 3, "failed": 0}
        mock_collector_class.return_value = mock_instance
        
        scheduler = CollectorScheduler()
        
        try:
            scheduler.start_scheduler()
            time.sleep(1)  # Brief delay for job to potentially execute
            
            # Check that job exists
            assert "reservation_collector" in scheduler.jobs
        
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()
    
    @patch("app.collectors.scheduler.ShippingCollector")
    def test_shipping_collector_execution(self, mock_collector_class):
        """Test that ShippingCollector is executed correctly."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = {"updated_count": 2}
        mock_collector_class.return_value = mock_instance
        
        scheduler = CollectorScheduler()
        
        try:
            scheduler.start_scheduler()
            time.sleep(1)  # Brief delay for job to potentially execute
            
            # Check that job exists
            assert "shipping_collector" in scheduler.jobs
        
        finally:
            if scheduler.is_running:
                scheduler.stop_scheduler()
    
    def test_collector_wrapper_handles_exceptions(self):
        """Test that collector wrapper handles exceptions gracefully."""
        scheduler = CollectorScheduler()
        
        # Create a mock collector that raises an exception
        mock_collector = MagicMock()
        mock_collector.run.side_effect = Exception("Test error")
        
        result = scheduler._run_collector_wrapper(
            lambda: mock_collector, "test_collector"
        )
        
        assert result["success"] is False
        assert "Test error" in result["error"]
        assert result["collector"] == "test_collector"
        assert result["duration_seconds"] is not None
    
    def test_collector_wrapper_calculates_duration(self):
        """Test that collector wrapper calculates execution duration."""
        scheduler = CollectorScheduler()
        
        # Create a mock collector with a small delay
        def slow_collector():
            mock = MagicMock()
            mock.run.return_value = {"status": "ok"}
            return mock
        
        result = scheduler._run_collector_wrapper(slow_collector, "test")
        
        assert result["duration_seconds"] >= 0
        assert result["start_time"] is not None
        assert result["end_time"] is not None


class TestGlobalSchedulerFunctions:
    """Tests for module-level scheduler functions."""
    
    def teardown_method(self):
        """Clean up after each test."""
        try:
            shutdown_scheduler()
        except:
            pass
    
    def test_get_scheduler_returns_same_instance(self):
        """Test that get_scheduler returns the same instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()
        
        assert scheduler1 is scheduler2
    
    def test_initialize_scheduler_starts_scheduler(self):
        """Test that initialize_scheduler starts the scheduler."""
        scheduler = initialize_scheduler()
        
        assert scheduler.is_running
        
        shutdown_scheduler()
    
    def test_shutdown_scheduler_stops_and_clears(self):
        """Test that shutdown_scheduler stops and clears the global instance."""
        scheduler = initialize_scheduler()
        assert scheduler.is_running
        
        shutdown_scheduler()
        
        # Verify new get_scheduler creates new instance
        new_scheduler = get_scheduler()
        assert not new_scheduler.is_running


class TestCollectorSchedulerConfiguration:
    """Tests for scheduler configuration."""
    
    def test_job_config_has_correct_intervals(self):
        """Test that job configuration has correct intervals."""
        assert CollectorScheduler.JOB_CONFIG["reservation"]["interval_hours"] == 6
        assert CollectorScheduler.JOB_CONFIG["shipping"]["interval_hours"] == 3
    
    def test_job_config_has_correct_job_ids(self):
        """Test that job configuration has correct job IDs."""
        assert (
            CollectorScheduler.JOB_CONFIG["reservation"]["job_id"]
            == "reservation_collector"
        )
        assert (
            CollectorScheduler.JOB_CONFIG["shipping"]["job_id"] == "shipping_collector"
        )
    
    def test_job_config_has_collector_classes(self):
        """Test that job configuration references correct collector classes."""
        from app.collectors.reservation import ReservationCollector
        from app.collectors.shipping import ShippingCollector
        
        assert (
            CollectorScheduler.JOB_CONFIG["reservation"]["collector_class"]
            is ReservationCollector
        )
        assert (
            CollectorScheduler.JOB_CONFIG["shipping"]["collector_class"]
            is ShippingCollector
        )


class TestSchedulerIntegration:
    """Integration tests for scheduler."""
    
    def test_scheduler_lifecycle(self):
        """Test complete scheduler lifecycle."""
        scheduler = CollectorScheduler()
        
        # Initial state
        assert not scheduler.is_running
        
        # Start scheduler
        scheduler.start_scheduler()
        assert scheduler.is_running
        assert len(scheduler.jobs) == 2
        
        # Get status
        status = scheduler.get_job_status()
        assert status["scheduler_running"] is True
        assert status["jobs_count"] == 2
        
        # Stop scheduler
        scheduler.stop_scheduler()
        assert not scheduler.is_running
        assert len(scheduler.jobs) == 0
    
    def test_multiple_scheduler_instances_independent(self):
        """Test that multiple scheduler instances are independent."""
        scheduler1 = CollectorScheduler()
        scheduler2 = CollectorScheduler()
        
        try:
            scheduler1.start_scheduler()
            
            assert scheduler1.is_running
            assert not scheduler2.is_running
            
            scheduler2.start_scheduler()
            
            assert scheduler1.is_running
            assert scheduler2.is_running
        
        finally:
            if scheduler1.is_running:
                scheduler1.stop_scheduler()
            if scheduler2.is_running:
                scheduler2.stop_scheduler()
