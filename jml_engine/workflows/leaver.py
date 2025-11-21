"""
Leaver Workflow for the JML Engine.

Handles employee termination and offboarding, systematically revoking
all access entitlements and deactivating accounts across all systems.
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from ..models import HREvent, LifecycleEvent, WorkflowResult
from .base_workflow import BaseWorkflow, WorkflowStep

logger = logging.getLogger(__name__)


class LeaverWorkflow(BaseWorkflow):
    """
    Workflow for processing employee termination/offboarding events.

    Revokes all access entitlements and deactivates accounts
    across AWS, Azure, GitHub, Google Workspace, and Slack.
    """

    def execute(self, hr_event: HREvent) -> WorkflowResult:
        """
        Execute the leaver workflow for an employee termination.

        Args:
            hr_event: HR event for the employee termination

        Returns:
            WorkflowResult with execution details
        """
        if hr_event.event not in [LifecycleEvent.TERMINATION, LifecycleEvent.CONTRACTOR_OFFBOARDING]:
            raise ValueError(f"Leaver workflow can only process TERMINATION/CONTRACTOR_OFFBOARDING events, got {hr_event.event}")

        self.started_at = datetime.now(timezone.utc)
        logger.info(f"Starting leaver workflow for employee {hr_event.employee_id}")

        try:
            # Get current identity and entitlements
            current_identity = self.state_manager.get_identity(hr_event.employee_id)
            if not current_identity:
                logger.warning(f"No identity found for terminating employee {hr_event.employee_id}")
                # Continue anyway to attempt cleanup

            # Execute deprovisioning steps
            self._execute_deprovisioning_steps(hr_event, current_identity)

            # Mark identity as terminated in state
            if current_identity:
                self.state_manager.deactivate_identity(hr_event.employee_id)

            # Mark workflow as completed
            self.completed_at = datetime.now(timezone.utc)

            # Create workflow result
            result = WorkflowResult(
                workflow_id=self.workflow_id,
                employee_id=hr_event.employee_id,
                event_type=hr_event.event,
                started_at=self.started_at,
                completed_at=self.completed_at,
                success=len(self.errors) == 0,
                actions_taken=[step.to_dict() for step in self.steps],
                errors=self.errors.copy()
            )

            logger.info(f"Completed leaver workflow for {hr_event.employee_id}: {len(self.steps)} steps, {len(self.errors)} errors")
            return result

        except Exception as e:
            logger.error(f"Leaver workflow failed for {hr_event.employee_id}: {e}")
            self.completed_at = datetime.now(timezone.utc)
            self.errors.append(str(e))

            return WorkflowResult(
                workflow_id=self.workflow_id,
                employee_id=hr_event.employee_id,
                event_type=hr_event.event,
                started_at=self.started_at,
                completed_at=self.completed_at,
                success=False,
                actions_taken=[step.to_dict() for step in self.steps],
                errors=self.errors.copy()
            )

    def _execute_deprovisioning_steps(self, hr_event: HREvent, identity: Optional[Any]):
        """
        Execute all deprovisioning steps for the terminating employee.

        Args:
            hr_event: The HR event
            identity: Current user identity (may be None)
        """
        # Revoke all access entitlements
        if identity and identity.entitlements:
            self._revoke_all_entitlements(hr_event, identity.entitlements)

        # Deactivate user accounts in each system
        self._deactivate_user_accounts(hr_event)

    def _revoke_all_entitlements(self, hr_event: HREvent, entitlements: List[Any]):
        """
        Revoke all access entitlements for the user.

        Args:
            hr_event: The HR event
            entitlements: List of current entitlements to revoke
        """
        for entitlement in entitlements:
            operation = self._get_revocation_operation(entitlement.resource_type)

            step = WorkflowStep(
                system=entitlement.system,
                operation=operation,
                resource=entitlement.resource_name,
                parameters={
                    'user_id': hr_event.employee_id,
                    'resource_name': entitlement.resource_name
                }
            )

            self.steps.append(step)
            success = self._execute_step(step)

            self._log_audit_event(
                employee_id=hr_event.employee_id,
                user_email=hr_event.email,
                event_type="revoke",
                system=entitlement.system,
                action=operation,
                resource=entitlement.resource_name,
                success=success,
                error=step.error if not success else None
            )

    def _deactivate_user_accounts(self, hr_event: HREvent):
        """Deactivate user accounts in all target systems."""
        systems_to_deactivate = ['aws', 'azure', 'github', 'google', 'slack']

        for system in systems_to_deactivate:
            step = WorkflowStep(
                system=system,
                operation='delete_user',
                resource='user_account',
                parameters={
                    'user_id': hr_event.employee_id
                }
            )

            self.steps.append(step)
            success = self._execute_step(step)

            self._log_audit_event(
                employee_id=hr_event.employee_id,
                user_email=hr_event.email,
                event_type="deprovision",
                system=system,
                action="delete_user",
                resource="user_account",
                success=success,
                error=step.error if not success else None
            )

    def _get_revocation_operation(self, resource_type: str) -> str:
        """
        Get the operation name for revoking a resource type.

        Args:
            resource_type: Type of resource (role, group, team, etc.)

        Returns:
            Operation name for revocation
        """
        operation_map = {
            'role': 'revoke_role',
            'group': 'remove_from_group',
            'team': 'remove_from_group',  # Teams are treated as groups
            'channel': 'remove_from_group'  # Channels are treated as groups
        }
        return operation_map.get(resource_type, 'revoke_role')
