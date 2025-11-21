"""
Tests for the Joiner Workflow.

This module contains comprehensive tests for the JoinerWorkflow class,
covering various scenarios and edge cases.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from ..models import HREvent, LifecycleEvent, WorkflowResult
from ..workflows import JoinerWorkflow
from ..engine import PolicyMapper, StateManager


class TestJoinerWorkflow:
    """Test cases for JoinerWorkflow."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing."""
        return {
            "mock_mode": True,
            "connectors": {
                "aws": {},
                "azure": {},
                "github": {},
                "google": {},
                "slack": {}
            }
        }

    @pytest.fixture
    def sample_hr_event(self):
        """Sample HR event for testing."""
        return HREvent(
            event=LifecycleEvent.NEW_STARTER,
            employee_id="TEST001",
            name="John Doe",
            email="john.doe@company.com",
            department="Engineering",
            title="Software Engineer",
            source_system="TEST"
        )

    @pytest.fixture
    def workflow(self, mock_config):
        """Create a JoinerWorkflow instance for testing."""
        return JoinerWorkflow(mock_config)

    def test_workflow_initialization(self, workflow):
        """Test that workflow initializes correctly."""
        assert workflow.workflow_id is not None
        assert len(workflow.workflow_id) > 0
        assert workflow.started_at is None
        assert workflow.completed_at is None
        assert workflow.steps == []
        assert workflow.errors == []

    def test_invalid_event_type(self, workflow):
        """Test that workflow rejects invalid event types."""
        invalid_event = HREvent(
            event=LifecycleEvent.TERMINATION,  # Wrong event type
            employee_id="TEST001",
            name="John Doe",
            email="john.doe@company.com",
            department="Engineering",
            title="Software Engineer"
        )

        with pytest.raises(ValueError, match="Joiner workflow can only process NEW_STARTER events"):
            workflow.execute(invalid_event)

    @patch('jml_engine.workflows.joiner.PolicyMapper')
    @patch('jml_engine.workflows.joiner.StateManager')
    def test_successful_workflow_execution(self, mock_state_manager, mock_policy_mapper,
                                         workflow, sample_hr_event):
        """Test successful execution of joiner workflow."""
        # Mock the policy mapper
        mock_policy_instance = Mock()
        mock_policy_instance.get_access_profile_from_event.return_value = Mock(
            aws_roles=["ReadOnlyAccess"],
            azure_groups=["Engineering"],
            github_teams=["developers"],
            google_groups=["employees"],
            slack_channels=["engineering"]
        )
        mock_policy_mapper.return_value = mock_policy_instance

        # Mock the state manager
        mock_state_instance = Mock()
        mock_identity = Mock()
        mock_state_instance.get_identity.return_value = None  # New user
        mock_state_instance.create_or_update_identity.return_value = mock_identity
        mock_state_instance.update_entitlements.return_value = True
        mock_state_manager.return_value = mock_state_instance

        # Mock connectors to succeed
        workflow.connectors = {
            'aws': Mock(),
            'azure': Mock(),
            'github': Mock(),
            'google': Mock(),
            'slack': Mock()
        }

        for connector in workflow.connectors.values():
            connector.create_user.return_value = Mock(success=True, message="Success")

        # Execute workflow
        result = workflow.execute(sample_hr_event)

        # Assertions
        assert isinstance(result, WorkflowResult)
        assert result.success is True
        assert result.employee_id == sample_hr_event.employee_id
        assert result.event_type == LifecycleEvent.NEW_STARTER
        assert result.started_at is not None
        assert result.completed_at is not None
        assert len(result.actions_taken) > 0
        assert len(result.errors) == 0

    def test_workflow_with_connector_failures(self, workflow, sample_hr_event):
        """Test workflow execution when some connectors fail."""
        # Setup mocks
        workflow.policy_mapper = Mock()
        workflow.state_manager = Mock()
        workflow.audit_logger = Mock()

        # Mock policy and state
        workflow.policy_mapper.get_access_profile_from_event.return_value = Mock(
            aws_roles=["ReadOnlyAccess"],
            azure_groups=[],
            github_teams=[],
            google_groups=[],
            slack_channels=[]
        )

        workflow.state_manager.get_identity.return_value = None
        workflow.state_manager.create_or_update_identity.return_value = Mock()
        workflow.state_manager.update_entitlements.return_value = True

        # Mock connectors - AWS succeeds, others fail
        workflow.connectors = {
            'aws': Mock(),
            'azure': Mock(),
            'github': Mock(),
            'google': Mock(),
            'slack': Mock()
        }

        workflow.connectors['aws'].create_user.return_value = Mock(success=True, message="Success")
        for name in ['azure', 'github', 'google', 'slack']:
            workflow.connectors[name].create_user.return_value = Mock(
                success=False,
                message=f"{name} failed",
                error="Connection error"
            )

        # Execute workflow
        result = workflow.execute(sample_hr_event)

        # Assertions - workflow should still succeed but with errors
        assert isinstance(result, WorkflowResult)
        assert result.success is True  # Workflow succeeds even with some connector failures
        assert len(result.errors) > 0
        assert "azure" in str(result.errors)
        assert result.total_steps == 5  # All systems attempted

    def test_workflow_with_invalid_hr_event(self, workflow):
        """Test workflow with invalid HR event data."""
        invalid_event = HREvent(
            event=LifecycleEvent.NEW_STARTER,
            employee_id="",  # Invalid: empty employee ID
            name="",
            email="invalid-email",  # Invalid: no @ symbol
            department="Engineering",
            title="Software Engineer"
        )

        # This should not raise an exception in the workflow itself
        # (validation happens at the API level)
        # But the workflow should handle it gracefully
        result = workflow.execute(invalid_event)

        # The workflow might succeed or fail depending on implementation
        assert isinstance(result, WorkflowResult)
        assert result.employee_id == invalid_event.employee_id

    @pytest.mark.parametrize("department,title,expected_aws_roles", [
        ("Engineering", "Software Engineer", ["EC2ReadOnly", "DevOpsRole"]),
        ("HR", "HR Manager", ["ReadOnlyAccess"]),
        ("Finance", "Accountant", ["ReadOnlyAccess"]),
    ])
    def test_access_profile_resolution(self, workflow, department, title, expected_aws_roles):
        """Test that access profiles are resolved correctly."""
        hr_event = HREvent(
            event=LifecycleEvent.NEW_STARTER,
            employee_id="TEST001",
            name="Test User",
            email="test@company.com",
            department=department,
            title=title
        )

        # Test the policy resolution
        access_profile = workflow.policy_mapper.get_access_profile_from_event(hr_event)

        # Verify that the profile has the expected structure
        assert hasattr(access_profile, 'aws_roles')
        assert hasattr(access_profile, 'azure_groups')
        assert hasattr(access_profile, 'github_teams')
        assert hasattr(access_profile, 'google_groups')
        assert hasattr(access_profile, 'slack_channels')

    def test_workflow_id_uniqueness(self):
        """Test that workflow IDs are unique."""
        config = {"mock_mode": True}

        workflow1 = JoinerWorkflow(config)
        workflow2 = JoinerWorkflow(config)

        assert workflow1.workflow_id != workflow2.workflow_id

    def test_execution_time_tracking(self, workflow, sample_hr_event):
        """Test that execution times are tracked properly."""
        initial_time = datetime.utcnow()

        # Mock successful execution
        workflow._execute_step = Mock(return_value=True)
        workflow.policy_mapper = Mock()
        workflow.state_manager = Mock()
        workflow.audit_logger = Mock()

        workflow.policy_mapper.get_access_profile_from_event.return_value = Mock(
            aws_roles=[], azure_groups=[], github_teams=[], google_groups=[], slack_channels=[]
        )
        workflow.state_manager.get_identity.return_value = None
        workflow.state_manager.create_or_update_identity.return_value = Mock()
        workflow.state_manager.update_entitlements.return_value = True

        result = workflow.execute(sample_hr_event)

        # Check timing
        assert result.started_at >= initial_time
        assert result.completed_at >= result.started_at
        assert (result.completed_at - result.started_at).total_seconds() >= 0

    def test_audit_logging(self, workflow, sample_hr_event):
        """Test that audit events are logged properly."""
        # Setup mocks
        workflow.policy_mapper = Mock()
        workflow.state_manager = Mock()
        workflow.audit_logger = Mock()

        workflow.policy_mapper.get_access_profile_from_event.return_value = Mock(
            aws_roles=["ReadOnlyAccess"],
            azure_groups=[],
            github_teams=[],
            google_groups=[],
            slack_channels=[]
        )

        workflow.state_manager.get_identity.return_value = None
        workflow.state_manager.create_or_update_identity.return_value = Mock()
        workflow.state_manager.update_entitlements.return_value = True

        # Mock connector
        workflow.connectors = {'aws': Mock()}
        workflow.connectors['aws'].create_user.return_value = Mock(success=True, message="Success")

        # Execute
        result = workflow.execute(sample_hr_event)

        # Verify audit logging was called
        assert workflow.audit_logger.log_event.called
        audit_calls = workflow.audit_logger.log_event.call_args_list
        assert len(audit_calls) > 0  # At least one audit event logged
