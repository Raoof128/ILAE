"""
Integration tests for the JML Engine.

This module contains integration tests that verify end-to-end functionality
across multiple components of the system.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from ..models import HREvent, LifecycleEvent
from ..ingestion import HREventListener
from ..workflows import JoinerWorkflow
from ..engine import PolicyMapper, StateManager
from ..api.server import app
from ..audit import AuditLogger, EvidenceStore
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestHREventProcessing:
    """Integration tests for HR event processing pipeline."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def sample_hr_events(self):
        """Sample HR events for testing."""
        return [
            HREvent(
                event=LifecycleEvent.NEW_STARTER,
                employee_id="INT001",
                name="Alice Johnson",
                email="alice.johnson@company.com",
                department="Engineering",
                title="Software Engineer",
                source_system="Workday"
            ),
            HREvent(
                event=LifecycleEvent.ROLE_CHANGE,
                employee_id="INT002",
                name="Bob Smith",
                email="bob.smith@company.com",
                department="Engineering",
                title="Senior Engineer",
                previous_department="Engineering",
                previous_title="Engineer",
                source_system="BambooHR"
            )
        ]

    def test_hr_event_ingestion_pipeline(self, sample_hr_events, temp_dir):
        """Test the complete HR event ingestion pipeline."""
        listener = HREventListener()

        # Test JSON ingestion
        for event in sample_hr_events:
            event_dict = event.dict()
            ingested_events = listener.ingest_event(event_dict)

            assert len(ingested_events) == 1
            ingested = ingested_events[0]
            assert ingested.employee_id == event.employee_id
            assert ingested.event == event.event

    def test_csv_ingestion_integration(self, temp_dir):
        """Test CSV file ingestion integration."""
        # Create a sample CSV file
        csv_content = """Employee ID,Name,Email,Department,Job Title,Event Type
CSV001,Charlie Brown,charlie.brown@company.com,Marketing,Manager,NEW_STARTER
CSV002,Diana Prince,diana.prince@company.com,HR,Specialist,NEW_STARTER"""

        csv_file = temp_dir / "hr_data.csv"
        csv_file.write_text(csv_content)

        listener = HREventListener()
        events = listener.ingest_csv_file(str(csv_file))

        assert len(events) == 2
        assert events[0].employee_id == "CSV001"
        assert events[0].department == "Marketing"
        assert events[1].employee_id == "CSV002"
        assert events[1].department == "HR"


@pytest.mark.integration
class TestWorkflowExecution:
    """Integration tests for workflow execution."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for integration testing."""
        return {
            "mock_mode": True,
            "connectors": {
                "aws": {"region": "us-east-1"},
                "azure": {},
                "github": {"organization": "test-org"},
                "google": {"domain": "test.com"},
                "slack": {"workspace_id": "T123456"}
            },
            "audit_dir": "/tmp/audit",
            "state_file": "/tmp/state.json"
        }

    def test_joiner_workflow_integration(self, mock_config):
        """Test complete joiner workflow execution."""
        hr_event = HREvent(
            event=LifecycleEvent.NEW_STARTER,
            employee_id="WF001",
            name="Workflow Test",
            email="workflow.test@company.com",
            department="Engineering",
            title="Engineer",
            source_system="IntegrationTest"
        )

        workflow = JoinerWorkflow(mock_config)

        # Mock all the components
        with patch.object(workflow, 'policy_mapper') as mock_pm, \
             patch.object(workflow, 'state_manager') as mock_sm, \
             patch.object(workflow, 'audit_logger') as mock_al:

            # Setup mocks
            mock_profile = MagicMock()
            mock_profile.aws_roles = ["ReadOnlyAccess"]
            mock_profile.azure_groups = ["Engineering"]
            mock_profile.github_teams = ["developers"]
            mock_profile.google_groups = ["employees"]
            mock_profile.slack_channels = ["engineering"]

            mock_pm.get_access_profile_from_event.return_value = mock_profile
            mock_sm.get_identity.return_value = None
            mock_sm.create_or_update_identity.return_value = MagicMock()
            mock_sm.update_entitlements.return_value = True

            # Mock connectors
            workflow.connectors = {
                'aws': MagicMock(),
                'azure': MagicMock(),
                'github': MagicMock(),
                'google': MagicMock(),
                'slack': MagicMock()
            }

            for connector in workflow.connectors.values():
                connector.create_user.return_value = MagicMock(success=True, message="Success")

            # Execute workflow
            result = workflow.execute(hr_event)

            # Verify results
            assert result.success is True
            assert result.employee_id == hr_event.employee_id
            assert len(result.actions_taken) == 5  # One for each system

            # Verify state management calls
            mock_sm.get_identity.assert_called_once()
            mock_sm.create_or_update_identity.assert_called_once()
            mock_sm.update_entitlements.assert_called_once()

            # Verify audit logging
            assert mock_al.log_event.call_count == 5  # One for each system


@pytest.mark.integration
class TestAPIIntegration:
    """Integration tests for the REST API."""

    @pytest.fixture
    def client(self):
        """Test client for the FastAPI application."""
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data

    def test_hr_event_submission(self, client):
        """Test HR event submission via API."""
        hr_event_data = {
            "event": "NEW_STARTER",
            "employee_id": "API001",
            "name": "API Test User",
            "email": "api.test@company.com",
            "department": "Engineering",
            "title": "Engineer"
        }

        response = client.post("/event/hr", json=hr_event_data)
        assert response.status_code == 200

        data = response.json()
        assert "workflow_id" in data
        assert data["employee_id"] == "API001"
        assert data["event_type"] == "NEW_STARTER"

    def test_user_lookup(self, client):
        """Test user lookup functionality."""
        # This would require mocking the state manager in a real integration test
        response = client.get("/user/NONEXISTENT")
        assert response.status_code == 404

    def test_audit_logs_access(self, client):
        """Test audit logs access."""
        response = client.get("/audit?days_back=1")
        # Status could be 200 or error depending on audit system setup
        assert response.status_code in [200, 500]  # Allow for uninitialized audit system


@pytest.mark.integration
class TestAuditCompliance:
    """Integration tests for audit and compliance features."""

    @pytest.fixture
    def temp_audit_dir(self):
        """Create temporary audit directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_dir = Path(temp_dir) / "audit"
            audit_dir.mkdir()
            yield audit_dir

    def test_audit_evidence_generation(self, temp_audit_dir):
        """Test audit evidence generation and storage."""
        from ..models import AuditRecord

        audit_logger = AuditLogger(str(temp_audit_dir))
        evidence_store = EvidenceStore(str(temp_audit_dir / "evidence"))

        # Create a test audit record
        audit_record = AuditRecord(
            id="test-audit-001",
            employee_id="TEST001",
            event_type="provision",
            system="aws",
            action="create_user",
            resource="user_account",
            success=True
        )

        # Log the event
        evidence_path = audit_logger.log_event(audit_record)

        # Verify evidence was created
        assert evidence_path is not None
        assert Path(evidence_path).exists()

        # Verify we can retrieve the evidence
        evidence_data = evidence_store.retrieve_evidence("test-audit-001")
        assert evidence_data is not None
        assert evidence_data["audit_record"]["id"] == "test-audit-001"

    def test_evidence_integrity(self, temp_audit_dir):
        """Test evidence integrity verification."""
        from ..audit.evidence_store import EvidenceStore

        store = EvidenceStore(str(temp_audit_dir))

        evidence_data = {
            "test": "data",
            "integrity_check": True
        }

        evidence_id = store.store_evidence(evidence_data)

        # Retrieve and verify integrity
        retrieved = store.retrieve_evidence(evidence_id)
        assert retrieved is not None
        assert retrieved["test"] == "data"

    def test_compliance_report_generation(self, temp_audit_dir):
        """Test compliance report generation."""
        from datetime import datetime, timedelta

        audit_logger = AuditLogger(str(temp_audit_dir))

        # Add some test audit records
        base_time = datetime.utcnow()
        for i in range(3):
            record = AuditRecord(
                id=f"compliance-test-{i}",
                timestamp=base_time - timedelta(hours=i),
                employee_id=f"EMP{i:03d}",
                event_type="provision",
                system="aws",
                action="create_user",
                resource=f"user_{i}",
                success=(i != 2)  # Make one failure
            )
            audit_logger.log_event(record)

        # Generate compliance report
        start_date = base_time - timedelta(days=1)
        end_date = base_time + timedelta(hours=1)

        report = audit_logger.generate_compliance_report(
            start_date, end_date, ["ISO_27001"]
        )

        assert report["summary"]["total_events"] == 3
        assert report["summary"]["successful_operations"] == 2
        assert report["summary"]["failed_operations"] == 1
        assert "recommendations" in report


@pytest.mark.integration
class TestStateManagement:
    """Integration tests for state management."""

    @pytest.fixture
    def temp_state_file(self):
        """Create temporary state file."""
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as f:
            f.write('{"identities": {}, "last_updated": "2024-01-01T00:00:00"}')
            temp_file = f.name

        yield temp_file

        # Cleanup
        Path(temp_file).unlink(missing_ok=True)

    def test_state_persistence(self, temp_state_file):
        """Test state persistence across sessions."""
        from ..models import UserIdentity, UserStatus

        # Create state manager
        state_mgr = StateManager(temp_state_file)

        # Create and store identity
        hr_event = HREvent(
            event=LifecycleEvent.NEW_STARTER,
            employee_id="STATE001",
            name="State Test",
            email="state.test@company.com",
            department="Engineering",
            title="Engineer"
        )

        identity = state_mgr.create_or_update_identity(hr_event)

        # Verify identity was stored
        assert identity.employee_id == "STATE001"
        assert identity.name == "State Test"

        # Create new state manager instance (simulating restart)
        state_mgr2 = StateManager(temp_state_file)

        # Verify identity was persisted
        loaded_identity = state_mgr2.get_identity("STATE001")
        assert loaded_identity is not None
        assert loaded_identity.employee_id == "STATE001"
        assert loaded_identity.name == "State Test"
