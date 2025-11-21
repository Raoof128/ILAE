"""
Mover Workflow for the JML Engine.

Handles employee transfers and role changes, updating access entitlements
by removing old permissions and adding new ones across all systems.
"""

import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime

from .base_workflow import BaseWorkflow, WorkflowStep
from ..models import HREvent, WorkflowResult, LifecycleEvent, AccessEntitlement

logger = logging.getLogger(__name__)


class MoverWorkflow(BaseWorkflow):
    """
    Workflow for processing employee move/transfer events.

    Compares old and new access profiles, removes outdated entitlements,
    and grants new ones across all integrated systems.
    """

    def execute(self, hr_event: HREvent) -> WorkflowResult:
        """
        Execute the mover workflow for an employee change.

        Args:
            hr_event: HR event for the employee move

        Returns:
            WorkflowResult with execution details
        """
        if hr_event.event not in [LifecycleEvent.ROLE_CHANGE, LifecycleEvent.DEPARTMENT_CHANGE]:
            raise ValueError(f"Mover workflow can only process ROLE_CHANGE/DEPARTMENT_CHANGE events, got {hr_event.event}")

        self.started_at = datetime.utcnow()
        logger.info(f"Starting mover workflow for employee {hr_event.employee_id}")

        try:
            # Get current identity and entitlements
            current_identity = self.state_manager.get_identity(hr_event.employee_id)
            if not current_identity:
                raise ValueError(f"No identity found for employee {hr_event.employee_id}")

            # Determine old access profile (from previous department/title)
            old_profile = self._get_old_access_profile(hr_event)

            # Determine new access profile
            new_profile = self.policy_mapper.get_access_profile_from_event(hr_event)

            # Calculate entitlement changes
            entitlements_to_remove, entitlements_to_add = self._calculate_entitlement_changes(
                current_identity.entitlements, old_profile, new_profile, hr_event.employee_id
            )

            # Execute removal steps
            self._execute_removal_steps(hr_event, entitlements_to_remove)

            # Execute addition steps
            self._execute_addition_steps(hr_event, entitlements_to_add)

            # Update state with new entitlements
            updated_entitlements = [ent for ent in current_identity.entitlements if ent not in entitlements_to_remove]
            updated_entitlements.extend(entitlements_to_add)
            self.state_manager.update_entitlements(hr_event.employee_id, updated_entitlements)

            # Update identity information
            current_identity.department = hr_event.department
            current_identity.title = hr_event.title
            current_identity.last_hr_event = hr_event
            current_identity.updated_at = datetime.utcnow()

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

            logger.info(f"Completed mover workflow for {hr_event.employee_id}: {len(self.steps)} steps, {len(self.errors)} errors")
            return result

        except Exception as e:
            logger.error(f"Mover workflow failed for {hr_event.employee_id}: {e}")
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

    def _get_old_access_profile(self, hr_event: HREvent) -> Any:
        """
        Determine the old access profile before the change.

        Args:
            hr_event: HR event containing previous information

        Returns:
            AccessProfile for the old role/department
        """
        old_department = hr_event.previous_department or hr_event.department
        old_title = hr_event.previous_title or hr_event.title

        return self.policy_mapper.get_access_profile(
            department=old_department,
            title=old_title
        )

    def _calculate_entitlement_changes(self, current_entitlements: List[AccessEntitlement],
                                    old_profile: Any, new_profile: Any, employee_id: str) -> tuple:
        """
        Calculate which entitlements to remove and add.

        Args:
            current_entitlements: Current entitlements for the user
            old_profile: Old access profile
            new_profile: New access profile
            employee_id: Employee ID

        Returns:
            Tuple of (entitlements_to_remove, entitlements_to_add)
        """
        # Convert profiles to entitlement sets for comparison
        old_entitlements = set(self._profile_to_entitlements(old_profile, employee_id))
        new_entitlements = set(self._profile_to_entitlements(new_profile, employee_id))
        current_entitlements_set = set(current_entitlements)

        # Entitlements to remove: in current but not in new
        entitlements_to_remove = current_entitlements_set - new_entitlements

        # Entitlements to add: in new but not in current
        entitlements_to_add = new_entitlements - current_entitlements_set

        logger.debug(f"Entitlement changes for {employee_id}: remove {len(entitlements_to_remove)}, add {len(entitlements_to_add)}")

        return list(entitlements_to_remove), list(entitlements_to_add)

    def _execute_removal_steps(self, hr_event: HREvent, entitlements_to_remove: List[AccessEntitlement]):
        """
        Execute steps to remove old entitlements.

        Args:
            hr_event: The HR event
            entitlements_to_remove: List of entitlements to revoke
        """
        for entitlement in entitlements_to_remove:
            operation = self._get_removal_operation(entitlement.resource_type)

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
                event_type="revoke",
                system=entitlement.system,
                action=operation,
                resource=entitlement.resource_name,
                success=success,
                error=step.error if not success else None
            )

    def _execute_addition_steps(self, hr_event: HREvent, entitlements_to_add: List[AccessEntitlement]):
        """
        Execute steps to add new entitlements.

        Args:
            hr_event: The HR event
            entitlements_to_add: List of entitlements to grant
        """
        for entitlement in entitlements_to_add:
            operation = self._get_addition_operation(entitlement.resource_type)

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
                event_type="grant",
                system=entitlement.system,
                action=operation,
                resource=entitlement.resource_name,
                success=success,
                error=step.error if not success else None
            )

    def _get_removal_operation(self, resource_type: str) -> str:
        """
        Get the operation name for removing a resource type.

        Args:
            resource_type: Type of resource (role, group, team, etc.)

        Returns:
            Operation name for removal
        """
        operation_map = {
            'role': 'revoke_role',
            'group': 'remove_from_group',
            'team': 'remove_from_group',  # Teams are treated as groups
            'channel': 'remove_from_group'  # Channels are treated as groups
        }
        return operation_map.get(resource_type, 'revoke_role')

    def _get_addition_operation(self, resource_type: str) -> str:
        """
        Get the operation name for adding a resource type.

        Args:
            resource_type: Type of resource (role, group, team, etc.)

        Returns:
            Operation name for addition
        """
        operation_map = {
            'role': 'grant_role',
            'group': 'add_to_group',
            'team': 'add_to_group',  # Teams are treated as groups
            'channel': 'add_to_group'  # Channels are treated as groups
        }
        return operation_map.get(resource_type, 'grant_role')
