"""
Base Workflow Classes for the JML Engine.

This module provides the foundation for Joiner, Mover, and Leaver workflows
with common functionality for executing IAM operations across multiple systems.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..audit.audit_logger import AuditLogger
from ..connectors import ConnectorResult, _get_connector_class
from ..engine.policy_mapper import PolicyMapper
from ..engine.state_manager import StateManager
from ..models import AccessEntitlement, AuditRecord, HREvent, UserIdentity, WorkflowResult

logger = logging.getLogger(__name__)


class WorkflowStep:
    """Represents a single step in a workflow execution."""

    def __init__(
        self,
        system: str,
        operation: str,
        resource: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ):
        self.system = system
        self.operation = operation
        self.resource = resource
        self.parameters = parameters or {}
        self.executed_at: Optional[datetime] = None
        self.success: bool = False
        self.error: Optional[str] = None
        self.result: Optional[Any] = None

    def mark_success(self, result: Any = None):
        """Mark step as successful."""
        self.executed_at = datetime.now(timezone.utc)
        self.success = True
        self.result = result

    def mark_failure(self, error: str):
        """Mark step as failed."""
        self.executed_at = datetime.now(timezone.utc)
        self.success = False
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary for serialization."""
        return {
            "system": self.system,
            "operation": self.operation,
            "resource": self.resource,
            "parameters": self.parameters,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "success": self.success,
            "error": self.error,
            "result": self.result,
        }


class BaseWorkflow(ABC):
    """
    Abstract base class for JML workflows.

    Provides common functionality for executing IAM operations across
    multiple systems with proper error handling and audit logging.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the workflow.

        Args:
            config: Configuration dictionary with connector settings
        """
        self.config = config or {}
        self.workflow_id = str(uuid.uuid4())
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.steps: List[WorkflowStep] = []
        self.errors: List[str] = []

        # Initialize components
        self.policy_mapper = PolicyMapper()
        self.state_manager = StateManager(self.config.get("state_file"))
        self.audit_logger = AuditLogger(self.config.get("audit_dir", "audit"))

        # Initialize connectors
        self.connectors = self._initialize_connectors()

        logger.info(f"Initialized {self.__class__.__name__} workflow {self.workflow_id}")

    def _initialize_connectors(self) -> Dict[str, Any]:
        """Initialize all system connectors."""
        connectors_config = self.config.get("connectors", {})

        connectors = {}
        mock_mode = self.config.get("mock_mode", True)
        for system in ["aws", "azure", "github", "google", "slack"]:
            connector_class = _get_connector_class(system, mock=mock_mode)
            connectors[system] = connector_class(connectors_config.get(system), mock_mode=mock_mode)

        return connectors

    @abstractmethod
    def execute(self, hr_event: HREvent) -> WorkflowResult:
        """
        Execute the workflow for the given HR event.

        Args:
            hr_event: The HR event to process

        Returns:
            WorkflowResult with execution details
        """
        pass

    def _execute_step(self, step: WorkflowStep) -> bool:
        """
        Execute a single workflow step.

        Args:
            step: The step to execute

        Returns:
            True if successful, False otherwise
        """
        try:
            connector = self.connectors.get(step.system)
            if not connector:
                error_msg = f"No connector available for system: {step.system}"
                step.mark_failure(error_msg)
                self.errors.append(error_msg)
                return False

            # Execute the operation
            result = self._call_connector_method(connector, step.operation, step.parameters)

            if result.success:
                step.mark_success(result.data)
                logger.info(f"Step completed: {step.system}.{step.operation}({step.resource})")
                return True
            else:
                step.mark_failure(result.error or "Unknown error")
                self.errors.append(f"{step.system}.{step.operation}: {result.error}")
                return False

        except Exception as e:
            error_msg = f"Exception during {step.system}.{step.operation}: {str(e)}"
            step.mark_failure(error_msg)
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False

    def _call_connector_method(
        self, connector: Any, operation: str, params: Dict[str, Any]
    ) -> ConnectorResult:
        """
        Call the appropriate connector method based on operation name.

        Args:
            connector: The connector instance
            operation: Operation name (create_user, add_to_group, etc.)
            params: Parameters for the operation

        Returns:
            ConnectorResult from the operation
        """
        method_map = {
            "create_user": lambda c, p: c.create_user(p["user"]),
            "delete_user": lambda c, p: c.delete_user(p["user_id"]),
            "add_to_group": lambda c, p: c.add_to_group(p["user_id"], p["group_name"]),
            "remove_from_group": lambda c, p: c.remove_from_group(p["user_id"], p["group_name"]),
            "grant_role": lambda c, p: c.grant_role(p["user_id"], p["role_name"]),
            "revoke_role": lambda c, p: c.revoke_role(p["user_id"], p["role_name"]),
        }

        if operation not in method_map:
            return ConnectorResult(False, f"Unknown operation: {operation}")

        return method_map[operation](connector, params)

    def _get_user_identity(self, hr_event: HREvent) -> Optional[UserIdentity]:
        """
        Get or create user identity for the HR event.

        Args:
            hr_event: The HR event

        Returns:
            UserIdentity for the user
        """
        identity = self.state_manager.get_identity(hr_event.employee_id)
        if not identity:
            # Create new identity
            access_profile = self.policy_mapper.get_access_profile_from_event(hr_event)
            entitlements = self._profile_to_entitlements(access_profile, hr_event.employee_id)
            identity = self.state_manager.create_or_update_identity(hr_event, entitlements)

        return identity

    def _profile_to_entitlements(self, profile: Any, employee_id: str) -> List[AccessEntitlement]:
        """
        Convert access profile to entitlement objects.

        Args:
            profile: AccessProfile object
            employee_id: Employee ID

        Returns:
            List of AccessEntitlement objects
        """
        entitlements = []

        # Helper function to safely iterate over profile attributes
        def safe_iterate(attr_value):
            """Safely iterate over an attribute that might be a Mock object."""
            if hasattr(attr_value, "__iter__") and not isinstance(attr_value, (str, bytes)):
                try:
                    return list(attr_value)
                except (TypeError, AttributeError):
                    return []
            return []

        # AWS roles
        for role in safe_iterate(profile.aws_roles):
            entitlements.append(
                AccessEntitlement(
                    system="aws",
                    resource_type="role",
                    resource_name=role,
                    permission_level="assume",
                )
            )

        # Azure groups
        for group in safe_iterate(profile.azure_groups):
            entitlements.append(
                AccessEntitlement(
                    system="azure",
                    resource_type="group",
                    resource_name=group,
                    permission_level="member",
                )
            )

        # GitHub teams
        for team in safe_iterate(profile.github_teams):
            entitlements.append(
                AccessEntitlement(
                    system="github",
                    resource_type="team",
                    resource_name=team,
                    permission_level="member",
                )
            )

        # Google groups
        for group in safe_iterate(profile.google_groups):
            entitlements.append(
                AccessEntitlement(
                    system="google",
                    resource_type="group",
                    resource_name=group,
                    permission_level="member",
                )
            )

        # Slack channels
        for channel in safe_iterate(profile.slack_channels):
            entitlements.append(
                AccessEntitlement(
                    system="slack",
                    resource_type="channel",
                    resource_name=channel,
                    permission_level="member",
                )
            )

        return entitlements

    def _log_audit_event(
        self,
        employee_id: str,
        user_email: str,
        event_type: str,
        system: str,
        action: str,
        resource: str,
        success: bool,
        error: Optional[str] = None,
    ) -> str:
        """
        Log an audit event.

        Args:
            employee_id: Employee ID
            event_type: Type of event
            system: Target system
            action: Action performed
            resource: Resource affected
            success: Whether the action succeeded
            error: Error message if failed

        Returns:
            Audit record ID
        """
        audit_record = AuditRecord(
            id=str(uuid.uuid4()),
            employee_id=employee_id,
            user_email=user_email,
            event_type=event_type,
            system=system,
            action=action,
            resource=resource,
            success=success,
            error_message=error,
            workflow_id=self.workflow_id,
        )

        self.audit_logger.log_event(audit_record)
        return audit_record.id

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of workflow execution."""
        successful_steps = len([s for s in self.steps if s.success])
        total_steps = len(self.steps)

        return {
            "workflow_id": self.workflow_id,
            "workflow_type": self.__class__.__name__,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_steps": total_steps,
            "successful_steps": successful_steps,
            "failed_steps": total_steps - successful_steps,
            "errors": self.errors.copy(),
        }
