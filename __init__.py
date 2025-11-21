"""
IAM Lifecycle Automation Engine (JML Engine)

Enterprise-grade IAM automation for Joiner-Mover-Leaver workflows
across AWS, Azure, GitHub, Google Workspace, and Slack.

This engine provides automated account provisioning, access management,
and deprovisioning to ensure security compliance and operational efficiency.
"""

__version__ = "1.0.0"
__author__ = "JML Engine Team"
__email__ = "team@example.com"

from .engine.policy_mapper import PolicyMapper
from .engine.state_manager import StateManager
from .workflows.joiner import JoinerWorkflow
from .workflows.mover import MoverWorkflow
from .workflows.leaver import LeaverWorkflow

__all__ = [
    "PolicyMapper",
    "StateManager",
    "JoinerWorkflow",
    "MoverWorkflow",
    "LeaverWorkflow",
]
