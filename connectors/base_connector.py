"""
Base Connector Classes for the JML Engine.

This module provides the foundation for all system connectors (AWS, Azure, GitHub, etc.)
with both real API implementations and mock/simulated backends.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import logging

from ..models import UserIdentity, AuditRecord

logger = logging.getLogger(__name__)


class ConnectorResult:
    """Result of a connector operation."""

    def __init__(self, success: bool, message: str = "", data: Optional[Any] = None,
                 error: Optional[str] = None):
        self.success = success
        self.message = message
        self.data = data
        self.error = error

    def __bool__(self):
        return self.success

    def __str__(self):
        return f"{'✓' if self.success else '✗'} {self.message}"


class BaseConnector(ABC):
    """
    Abstract base class for all system connectors.

    Each connector implements the standard IAM operations for a specific platform.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, mock_mode: bool = False):
        """
        Initialize the connector.

        Args:
            config: Configuration dictionary with API credentials, endpoints, etc.
            mock_mode: If True, use mock/simulated backend instead of real APIs
        """
        self.config = config or {}
        self.mock_mode = mock_mode
        self.system_name = self.__class__.__name__.replace('Connector', '').lower()

        logger.info(f"Initialized {self.__class__.__name__} (mock_mode={mock_mode})")

    @abstractmethod
    def create_user(self, user: UserIdentity) -> ConnectorResult:
        """
        Create a new user account.

        Args:
            user: User identity information

        Returns:
            ConnectorResult with success status and any relevant data
        """
        pass

    @abstractmethod
    def delete_user(self, user_id: str) -> ConnectorResult:
        """
        Delete or deactivate a user account.

        Args:
            user_id: Unique identifier for the user in this system

        Returns:
            ConnectorResult with success status
        """
        pass

    @abstractmethod
    def add_to_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """
        Add user to a security group or team.

        Args:
            user_id: User identifier in this system
            group_name: Name of the group/team to add to

        Returns:
            ConnectorResult with success status
        """
        pass

    @abstractmethod
    def remove_from_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """
        Remove user from a security group or team.

        Args:
            user_id: User identifier in this system
            group_name: Name of the group/team to remove from

        Returns:
            ConnectorResult with success status
        """
        pass

    @abstractmethod
    def grant_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """
        Grant a role or permission to a user.

        Args:
            user_id: User identifier in this system
            role_name: Name of the role/permission to grant

        Returns:
            ConnectorResult with success status
        """
        pass

    @abstractmethod
    def revoke_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """
        Revoke a role or permission from a user.

        Args:
            user_id: User identifier in this system
            role_name: Name of the role/permission to revoke

        Returns:
            ConnectorResult with success status
        """
        pass

    @abstractmethod
    def get_user(self, user_id: str) -> ConnectorResult:
        """
        Get user information from the system.

        Args:
            user_id: User identifier in this system

        Returns:
            ConnectorResult with user data if found
        """
        pass

    @abstractmethod
    def list_user_permissions(self, user_id: str) -> ConnectorResult:
        """
        List all permissions/roles/groups for a user.

        Args:
            user_id: User identifier in this system

        Returns:
            ConnectorResult with list of permissions
        """
        pass

    def validate_config(self) -> bool:
        """
        Validate that the connector has all required configuration.

        Returns:
            True if configuration is valid, False otherwise
        """
        return True

    def get_system_name(self) -> str:
        """Get the name of the system this connector manages."""
        return self.system_name

    def is_mock_mode(self) -> bool:
        """Check if this connector is running in mock mode."""
        return self.mock_mode


class MockConnector(BaseConnector):
    """
    Base class for mock/simulated connectors.

    Provides in-memory state management for testing and development
    without requiring real API access.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config, mock_mode=True)

        # In-memory state for mock operations
        self.users: Dict[str, Dict[str, Any]] = {}
        self.groups: Dict[str, List[str]] = {}  # group_name -> list of user_ids
        self.roles: Dict[str, List[str]] = {}   # role_name -> list of user_ids

    def create_user(self, user: UserIdentity) -> ConnectorResult:
        """Mock user creation."""
        user_id = user.employee_id
        if user_id in self.users:
            return ConnectorResult(False, f"User {user_id} already exists")

        self.users[user_id] = {
            "name": user.name,
            "email": user.email,
            "active": True,
            "created_at": datetime.utcnow(),
            "groups": [],
            "roles": []
        }

        logger.info(f"Mock created user: {user_id}")
        return ConnectorResult(True, f"Created user {user_id}")

    def delete_user(self, user_id: str) -> ConnectorResult:
        """Mock user deletion."""
        if user_id not in self.users:
            return ConnectorResult(False, f"User {user_id} not found")

        self.users[user_id]["active"] = False
        logger.info(f"Mock deactivated user: {user_id}")
        return ConnectorResult(True, f"Deactivated user {user_id}")

    def add_to_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Mock add to group."""
        if user_id not in self.users:
            return ConnectorResult(False, f"User {user_id} not found")

        if group_name not in self.groups:
            self.groups[group_name] = []

        if user_id not in self.groups[group_name]:
            self.groups[group_name].append(user_id)
            self.users[user_id]["groups"].append(group_name)

        logger.info(f"Mock added {user_id} to group {group_name}")
        return ConnectorResult(True, f"Added {user_id} to {group_name}")

    def remove_from_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Mock remove from group."""
        if user_id not in self.users:
            return ConnectorResult(False, f"User {user_id} not found")

        if group_name in self.groups and user_id in self.groups[group_name]:
            self.groups[group_name].remove(user_id)
            if group_name in self.users[user_id]["groups"]:
                self.users[user_id]["groups"].remove(group_name)

        logger.info(f"Mock removed {user_id} from group {group_name}")
        return ConnectorResult(True, f"Removed {user_id} from {group_name}")

    def grant_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Mock role granting."""
        if user_id not in self.users:
            return ConnectorResult(False, f"User {user_id} not found")

        if role_name not in self.roles:
            self.roles[role_name] = []

        if user_id not in self.roles[role_name]:
            self.roles[role_name].append(user_id)
            self.users[user_id]["roles"].append(role_name)

        logger.info(f"Mock granted role {role_name} to {user_id}")
        return ConnectorResult(True, f"Granted {role_name} to {user_id}")

    def revoke_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Mock role revocation."""
        if user_id not in self.users:
            return ConnectorResult(False, f"User {user_id} not found")

        if role_name in self.roles and user_id in self.roles[role_name]:
            self.roles[role_name].remove(user_id)
            if role_name in self.users[user_id]["roles"]:
                self.users[user_id]["roles"].remove(role_name)

        logger.info(f"Mock revoked role {role_name} from {user_id}")
        return ConnectorResult(True, f"Revoked {role_name} from {user_id}")

    def get_user(self, user_id: str) -> ConnectorResult:
        """Mock get user."""
        if user_id not in self.users:
            return ConnectorResult(False, f"User {user_id} not found")

        return ConnectorResult(True, f"Found user {user_id}", self.users[user_id])

    def list_user_permissions(self, user_id: str) -> ConnectorResult:
        """Mock list user permissions."""
        if user_id not in self.users:
            return ConnectorResult(False, f"User {user_id} not found")

        user_data = self.users[user_id]
        permissions = {
            "groups": user_data["groups"],
            "roles": user_data["roles"]
        }

        return ConnectorResult(True, f"Permissions for {user_id}", permissions)

    def get_mock_state(self) -> Dict[str, Any]:
        """Get current mock state for inspection."""
        return {
            "users": self.users,
            "groups": self.groups,
            "roles": self.roles
        }
