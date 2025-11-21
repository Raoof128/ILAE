"""
Joiner Workflow for the JML Engine.

Handles the onboarding process for new employees, creating accounts
and assigning initial access entitlements across all integrated systems.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from .base_workflow import BaseWorkflow, WorkflowStep
from ..models import HREvent, WorkflowResult, LifecycleEvent

logger = logging.getLogger(__name__)


class JoinerWorkflow(BaseWorkflow):
    """
    Workflow for processing new employee join events.

    Creates user accounts and assigns baseline access entitlements
    across AWS, Azure, GitHub, Google Workspace, and Slack.
    """

    def execute(self, hr_event: HREvent) -> WorkflowResult:
        """
        Execute the joiner workflow for a new employee.

        Args:
            hr_event: HR event for the new joiner

        Returns:
            WorkflowResult with execution details
        """
        if hr_event.event != LifecycleEvent.NEW_STARTER:
            raise ValueError(f"Joiner workflow can only process NEW_STARTER events, got {hr_event.event}")

        self.started_at = datetime.utcnow()
        logger.info(f"Starting joiner workflow for employee {hr_event.employee_id}")

        try:
            # Get access profile for the new employee
            access_profile = self.policy_mapper.get_access_profile_from_event(hr_event)

            # Create user identity
            identity = self._get_user_identity(hr_event)

            # Execute provisioning steps
            self._execute_provisioning_steps(hr_event, access_profile)

            # Update state with new entitlements
            entitlements = self._profile_to_entitlements(access_profile, hr_event.employee_id)
            self.state_manager.update_entitlements(hr_event.employee_id, entitlements)

            # Mark workflow as completed
            self.completed_at = datetime.utcnow()

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

            logger.info(f"Completed joiner workflow for {hr_event.employee_id}: {len(self.steps)} steps, {len(self.errors)} errors")
            return result

        except Exception as e:
            logger.error(f"Joiner workflow failed for {hr_event.employee_id}: {e}")
            self.completed_at = datetime.utcnow()
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

    def _execute_provisioning_steps(self, hr_event: HREvent, access_profile: Any):
        """
        Execute all provisioning steps for the new employee.

        Args:
            hr_event: The HR event
            access_profile: Access profile for the employee
        """
        # Create user accounts in each system
        self._create_user_accounts(hr_event)

        # Assign roles and group memberships
        self._assign_access_entitlements(hr_event, access_profile)

    def _create_user_accounts(self, hr_event: HREvent):
        """Create user accounts in all target systems."""
        systems_to_create = ['aws', 'azure', 'github', 'google', 'slack']

        for system in systems_to_create:
            step = WorkflowStep(
                system=system,
                operation='create_user',
                resource='user_account',
                parameters={
                    'user': hr_event,  # Pass the full HR event as user data
                    'user_id': hr_event.employee_id
                }
            )

            self.steps.append(step)
            success = self._execute_step(step)

            # Log audit event
            self._log_audit_event(
                employee_id=hr_event.employee_id,
                event_type="provision",
                system=system,
                action="create_user",
                resource="user_account",
                success=success,
                error=step.error if not success else None
            )

    def _assign_access_entitlements(self, hr_event: HREvent, access_profile: Any):
        """
        Assign access entitlements based on the employee's profile.

        Args:
            hr_event: The HR event
            access_profile: Access profile containing entitlements
        """
        # AWS IAM roles
        for role in access_profile.aws_roles:
            step = WorkflowStep(
                system='aws',
                operation='grant_role',
                resource=role,
                parameters={
                    'user_id': hr_event.employee_id,
                    'role_name': role
                }
            )
            self.steps.append(step)
            success = self._execute_step(step)

            self._log_audit_event(
                employee_id=hr_event.employee_id,
                event_type="provision",
                system="aws",
                action="grant_role",
                resource=role,
                success=success,
                error=step.error if not success else None
            )

        # Azure groups
        for group in access_profile.azure_groups:
            step = WorkflowStep(
                system='azure',
                operation='add_to_group',
                resource=group,
                parameters={
                    'user_id': hr_event.employee_id,
                    'group_name': group
                }
            )
            self.steps.append(step)
            success = self._execute_step(step)

            self._log_audit_event(
                employee_id=hr_event.employee_id,
                event_type="provision",
                system="azure",
                action="add_to_group",
                resource=group,
                success=success,
                error=step.error if not success else None
            )

        # GitHub teams
        for team in access_profile.github_teams:
            step = WorkflowStep(
                system='github',
                operation='add_to_group',
                resource=team,
                parameters={
                    'user_id': hr_event.employee_id,  # This should be GitHub username
                    'group_name': team
                }
            )
            self.steps.append(step)
            success = self._execute_step(step)

            self._log_audit_event(
                employee_id=hr_event.employee_id,
                event_type="provision",
                system="github",
                action="add_to_team",
                resource=team,
                success=success,
                error=step.error if not success else None
            )

        # Google Workspace groups
        for group in access_profile.google_groups:
            step = WorkflowStep(
                system='google',
                operation='add_to_group',
                resource=group,
                parameters={
                    'user_id': hr_event.email,  # Use email for Google
                    'group_name': group
                }
            )
            self.steps.append(step)
            success = self._execute_step(step)

            self._log_audit_event(
                employee_id=hr_event.employee_id,
                event_type="provision",
                system="google",
                action="add_to_group",
                resource=group,
                success=success,
                error=step.error if not success else None
            )

        # Slack channels
        for channel in access_profile.slack_channels:
            step = WorkflowStep(
                system='slack',
                operation='add_to_group',
                resource=channel,
                parameters={
                    'user_id': hr_event.email,  # Use email for Slack
                    'group_name': channel
                }
            )
            self.steps.append(step)
            success = self._execute_step(step)

            self._log_audit_event(
                employee_id=hr_event.employee_id,
                event_type="provision",
                system="slack",
                action="add_to_channel",
                resource=channel,
                success=success,
                error=step.error if not success else None
            )
