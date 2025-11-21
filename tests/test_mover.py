"""
Tests for the Mover Workflow.

This module contains comprehensive tests for the MoverWorkflow class,
covering various scenarios and edge cases.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from ..models import HREvent, LifecycleEvent, WorkflowResult
from ..workflows import MoverWorkflow


class TestMoverWorkflow:
    """Test cases for MoverWorkflow."""

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
    def role_change_event(self):
        """Sample role change HR event."""
        return HREvent(
            event=LifecycleEvent.ROLE_CHANGE,
            employee_id="TEST001",
            name="John Doe",
            email="john.doe@company.com",
            department="Engineering",
            title="Senior Engineer",
            previous_department="Engineering",
            previous_title="Engineer",
            source_system="TEST"
        )

    @pytest.fixture
    def department_change_event(self):
        """Sample department change HR event."""
        return HREvent(
            event=LifecycleEvent.DEPARTMENT_CHANGE,
            employee_id="TEST002",
            name="Jane Smith",
            email="jane.smith@company.com",
            department="Marketing",
            title="Manager",
            previous_department="Sales",
            previous_title="Manager",
            source_system="TEST"
        )

    @pytest.fixture
    def workflow(self, mock_config):
        """Create a MoverWorkflow instance for testing."""
        return MoverWorkflow(mock_config)

    def test_workflow_initialization(self, workflow):
        """Test that workflow initializes correctly."""
        assert workflow.workflow_id is not None
        assert len(workflow.workflow_id) > 0
        assert workflow.started_at is None
        assert workflow.completed_at is None
        assert workflow.steps == []
        assert workflow.errors == []

    @pytest.mark.parametrize("event_type", [
        LifecycleEvent.NEW_STARTER,
        LifecycleEvent.TERMINATION
    ])
    def test_invalid_event_type(self, workflow, event_type):
        """Test that workflow rejects invalid event types."""
        invalid_event = HREvent(
            event=event_type,  # Wrong event type
            employee_id="TEST001",
            name="John Doe",
            email="john.doe@company.com",
            department="Engineering",
            title="Software Engineer"
        )

        with pytest.raises(ValueError, match="Mover workflow can only process ROLE_CHANGE/DEPARTMENT_CHANGE events"):
            workflow.execute(invalid_event)

    @patch('jml_engine.workflows.mover.PolicyMapper')
    @patch('jml_engine.workflows.mover.StateManager')
    def test_successful_role_change(self, mock_state_manager, mock_policy_mapper,
                                  workflow, role_change_event):
        """Test successful execution of role change workflow."""
        # Mock the policy mapper
        mock_policy_instance = Mock()
        mock_policy_instance.get_access_profile_from_event.return_value = Mock(
            aws_roles=["EC2ReadOnly"],
            azure_groups=["Engineering"],
            github_teams=["developers"],
            google_groups=["employees"],
            slack_channels=["engineering"]
        )
        mock_policy_mapper.return_value = mock_policy_instance

        # Mock the state manager
        mock_state_instance = Mock()
        mock_identity = Mock()
        mock_identity.entitlements = [
            Mock(system="aws", resource_type="role", resource_name="ReadOnlyAccess"),
            Mock(system="github", resource_type="team", resource_name="interns")
        ]
        mock_state_instance.get_identity.return_value = mock_identity
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
            connector.grant_role.return_value = Mock(success=True, message="Success")
            connector.add_to_group.return_value = Mock(success=True, message="Success")

        # Execute workflow
        result = workflow.execute(role_change_event)

        # Assertions
        assert isinstance(result, WorkflowResult)
        assert result.success is True
        assert result.employee_id == role_change_event.employee_id
        assert result.event_type == LifecycleEvent.ROLE_CHANGE
        assert result.started_at is not None
        assert result.completed_at is not None
        assert len(result.actions_taken) > 0
        assert len(result.errors) == 0

    def test_entitlement_change_calculation(self, workflow):
        """Test calculation of entitlement changes."""
        old_profile = Mock()
        old_profile.aws_roles = ["ReadOnlyAccess"]
        old_profile.azure_groups = ["Employees"]
        old_profile.github_teams = ["interns"]

        new_profile = Mock()
        new_profile.aws_roles = ["EC2ReadOnly", "S3ReadOnly"]
        new_profile.azure_groups = ["Engineering"]
        new_profile.github_teams = ["developers"]

        current_entitlements = [
            Mock(system="aws", resource_type="role", resource_name="ReadOnlyAccess"),
            Mock(system="github", resource_type="team", resource_name="interns")
        ]

        employee_id = "TEST001"

        to_remove, to_add = workflow._calculate_entitlement_changes(
            current_entitlements, old_profile, new_profile, employee_id
        )

        # Should remove interns team, add EC2ReadOnly, S3ReadOnly, Engineering group, developers team
        assert len(to_remove) == 1  # interns team
        assert len(to_add) == 4     # EC2ReadOnly, S3ReadOnly, Engineering, developers

    def test_workflow_with_partial_failures(self, workflow, role_change_event):
        """Test workflow with some connector failures."""
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

        mock_identity = Mock()
        mock_identity.entitlements = []
        workflow.state_manager.get_identity.return_value = mock_identity
        workflow.state_manager.update_entitlements.return_value = True

        # Mock connectors - AWS succeeds, others fail
        workflow.connectors = {
            'aws': Mock(),
            'azure': Mock(),
            'github': Mock(),
            'google': Mock(),
            'slack': Mock()
        }

        workflow.connectors['aws'].grant_role.return_value = Mock(success=True, message="Success")
        for name in ['azure', 'github', 'google', 'slack']:
            workflow.connectors[name].grant_role.return_value = Mock(
                success=False,
                message=f"{name} failed",
                error="Connection error"
            )

        # Execute workflow
        result = workflow.execute(role_change_event)

        # Assertions - workflow should still succeed but with errors
        assert isinstance(result, WorkflowResult)
        assert result.success is True  # Workflow succeeds even with some connector failures
        assert len(result.errors) > 0
        assert "azure" in str(result.errors)
        assert result.total_steps == 1  # Only AWS role to add

    def test_no_identity_found(self, workflow, role_change_event):
        """Test workflow when no identity is found."""
        workflow.state_manager = Mock()
        workflow.state_manager.get_identity.return_value = None

        result = workflow.execute(role_change_event)

        # Should fail gracefully
        assert isinstance(result, WorkflowResult)
        assert result.success is False
        assert len(result.errors) > 0

    def test_audit_logging_on_failure(self, workflow, role_change_event):
        """Test that audit events are logged even on failures."""
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

        mock_identity = Mock()
        mock_identity.entitlements = []
        workflow.state_manager.get_identity.return_value = mock_identity
        workflow.state_manager.update_entitlements.return_value = True

        # Mock connector to fail
        workflow.connectors = {'aws': Mock()}
        workflow.connectors['aws'].grant_role.return_value = Mock(
            success=False,
            message="Failed",
            error="Permission denied"
        )

        # Execute workflow
        result = workflow.execute(role_change_event)

        # Verify audit logging was called
        assert workflow.audit_logger.log_event.called
        audit_calls = workflow.audit_logger.log_event.call_args_list
        assert len(audit_calls) > 0

        # Check that failure was logged
        audit_record = audit_calls[0][0][0]  # First call, first argument
        assert audit_record.success is False
        assert audit_record.error_message == "Permission denied"
