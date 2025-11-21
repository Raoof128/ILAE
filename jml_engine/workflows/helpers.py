"""
Workflow Helper Functions for the JML Engine.

Utility functions and helpers for workflow processing,
including validation, transformation, and common operations.
"""

import logging
from typing import Any, Dict, List

from ..models import HREvent, LifecycleEvent

logger = logging.getLogger(__name__)


def validate_hr_event(hr_event: HREvent) -> List[str]:
    """
    Validate an HR event for completeness and correctness.

    Args:
        hr_event: The HR event to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Required fields
    if not hr_event.employee_id or not hr_event.employee_id.strip():
        errors.append("Employee ID is required")

    if not hr_event.name or not hr_event.name.strip():
        errors.append("Employee name is required")

    if not hr_event.email or not hr_event.email.strip():
        errors.append("Employee email is required")

    if not hr_event.department or not hr_event.department.strip():
        errors.append("Department is required")

    # Email format validation
    if hr_event.email and '@' not in hr_event.email:
        errors.append("Invalid email format")

    # Event-specific validations
    if hr_event.event in [LifecycleEvent.ROLE_CHANGE, LifecycleEvent.DEPARTMENT_CHANGE]:
        if not hr_event.previous_department and not hr_event.previous_title:
            errors.append("Previous department or title required for mover events")

    return errors


def determine_workflow_type(hr_event: HREvent) -> str:
    """
    Determine which workflow should process the HR event.

    Args:
        hr_event: The HR event

    Returns:
        Workflow type name ('joiner', 'mover', 'leaver')
    """
    if hr_event.event == LifecycleEvent.NEW_STARTER:
        return 'joiner'
    elif hr_event.event in [LifecycleEvent.ROLE_CHANGE, LifecycleEvent.DEPARTMENT_CHANGE]:
        return 'mover'
    elif hr_event.event in [LifecycleEvent.TERMINATION, LifecycleEvent.CONTRACTOR_OFFBOARDING]:
        return 'leaver'
    else:
        raise ValueError(f"No workflow available for event type: {hr_event.event}")


def generate_system_username(employee_id: str, email: str) -> str:
    """
    Generate a system username from employee ID and email.

    Args:
        employee_id: Employee ID
        email: Employee email

    Returns:
        Generated username suitable for most systems
    """
    # Use email prefix, fallback to employee ID
    if email and '@' in email:
        base_username = email.split('@')[0]
    else:
        base_username = employee_id

    # Clean up username (remove special characters, limit length)
    username = ''.join(c for c in base_username if c.isalnum() or c in ['_', '-', '.'])

    # Ensure minimum length and no leading/trailing special chars
    username = username.strip('_-.')

    if len(username) < 1:
        username = f"user_{employee_id}"

    # Limit length for systems with restrictions
    if len(username) > 32:
        username = username[:32]

    return username


def calculate_access_profile_changes(old_profile: Any, new_profile: Any) -> Dict[str, Any]:
    """
    Calculate the changes between two access profiles.

    Args:
        old_profile: Old access profile
        new_profile: New access profile

    Returns:
        Dictionary with added/removed entitlements by system
    """
    changes = {
        'aws': {'added': [], 'removed': []},
        'azure': {'added': [], 'removed': []},
        'github': {'added': [], 'removed': []},
        'google': {'added': [], 'removed': []},
        'slack': {'added': [], 'removed': []}
    }

    # Calculate AWS changes
    old_aws = set(old_profile.aws_roles)
    new_aws = set(new_profile.aws_roles)
    changes['aws']['added'] = list(new_aws - old_aws)
    changes['aws']['removed'] = list(old_aws - new_aws)

    # Calculate Azure changes
    old_azure = set(old_profile.azure_groups)
    new_azure = set(new_profile.azure_groups)
    changes['azure']['added'] = list(new_azure - old_azure)
    changes['azure']['removed'] = list(old_azure - new_azure)

    # Calculate GitHub changes
    old_github = set(old_profile.github_teams)
    new_github = set(new_profile.github_teams)
    changes['github']['added'] = list(new_github - old_github)
    changes['github']['removed'] = list(old_github - new_github)

    # Calculate Google changes
    old_google = set(old_profile.google_groups)
    new_google = set(new_profile.google_groups)
    changes['google']['added'] = list(new_google - old_google)
    changes['google']['removed'] = list(old_google - new_google)

    # Calculate Slack changes
    old_slack = set(old_profile.slack_channels)
    new_slack = set(new_profile.slack_channels)
    changes['slack']['added'] = list(new_slack - old_slack)
    changes['slack']['removed'] = list(old_slack - new_slack)

    return changes


def should_skip_system(system: str, config: Dict[str, Any]) -> bool:
    """
    Determine if a system should be skipped during workflow execution.

    Args:
        system: System name (aws, azure, github, etc.)
        config: Workflow configuration

    Returns:
        True if the system should be skipped
    """
    disabled_systems = config.get('disabled_systems', [])
    enabled_systems = config.get('enabled_systems')

    # If specific systems are enabled, only process those
    if enabled_systems and system not in enabled_systems:
        return True

    # If system is explicitly disabled
    if system in disabled_systems:
        return True

    return False


def create_audit_summary(workflow_result: Any) -> Dict[str, Any]:
    """
    Create a summary of workflow execution for auditing.

    Args:
        workflow_result: WorkflowResult object

    Returns:
        Dictionary with audit summary
    """
    successful_actions = len([a for a in workflow_result.actions_taken if a.get('success', False)])
    total_actions = len(workflow_result.actions_taken)

    return {
        'workflow_id': workflow_result.workflow_id,
        'employee_id': workflow_result.employee_id,
        'event_type': workflow_result.event_type.value,
        'started_at': workflow_result.started_at.isoformat() if workflow_result.started_at else None,
        'completed_at': workflow_result.completed_at.isoformat() if workflow_result.completed_at else None,
        'success': workflow_result.success,
        'total_actions': total_actions,
        'successful_actions': successful_actions,
        'failed_actions': total_actions - successful_actions,
        'error_count': len(workflow_result.errors),
        'errors': workflow_result.errors
    }


def retry_failed_actions(workflow_result: Any, max_retries: int = 3) -> List[Dict[str, Any]]:
    """
    Identify failed actions that could be retried.

    Args:
        workflow_result: WorkflowResult object
        max_retries: Maximum number of retries allowed

    Returns:
        List of retryable failed actions
    """
    retryable_actions = []

    for action in workflow_result.actions_taken:
        if not action.get('success', False):
            error = action.get('error', '')

            # Define which errors are retryable
            retryable_errors = [
                'timeout',
                'temporary failure',
                'rate limit',
                'service unavailable',
                'network error'
            ]

            if any(retry_error.lower() in error.lower() for retry_error in retryable_errors):
                action_copy = action.copy()
                action_copy['retry_count'] = action_copy.get('retry_count', 0) + 1

                if action_copy['retry_count'] <= max_retries:
                    retryable_actions.append(action_copy)

    return retryable_actions
