"""
Slack Connector for the JML Engine.

Provides integration with Slack for workspace membership,
channel access, and user management.
"""

import logging
from typing import Dict, List, Optional, Any

from .base_connector import BaseConnector, MockConnector, ConnectorResult
from ..models import UserIdentity

# Optional imports for Slack SDK
try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_SDK_AVAILABLE = True
except ImportError:
    SLACK_SDK_AVAILABLE = False
    WebClient = None
    SlackApiError = Exception

logger = logging.getLogger(__name__)


class SlackConnector(BaseConnector):
    """Slack connector for managing workspace members and channels."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, mock_mode: bool = False):
        # Force mock mode if Slack SDK is not available
        if not SLACK_SDK_AVAILABLE:
            mock_mode = True
            logger.warning("Slack SDK not available, using mock mode")

        super().__init__(config, mock_mode)

        if not mock_mode and SLACK_SDK_AVAILABLE:
            token = config.get('slack_token') or config.get('token')
            if not token:
                raise ValueError("Slack token is required for real mode")

            self.client = WebClient(token=token)
            self.workspace_id = config.get('workspace_id')
        else:
            self.client = None
            self.workspace_id = config.get('workspace_id', 'mock-workspace') if config else 'mock-workspace'

    def create_user(self, user: UserIdentity) -> ConnectorResult:
        """Invite user to Slack workspace."""
        if self.mock_mode:
            return SlackMockConnector(self.config).create_user(user)

        try:
            # Send invitation to workspace
            response = self.client.admin_users_invite(
                email=user.email,
                channels=self._get_default_channels(),
                real_name=user.name,
                resend=True
            )

            if response["ok"]:
                logger.info(f"Sent Slack invitation to {user.email}")
                return ConnectorResult(True, f"Invited {user.email} to Slack workspace")
            else:
                error_msg = f"Failed to invite {user.email} to Slack: {response.get('error')}"
                logger.error(error_msg)
                return ConnectorResult(False, error_msg)

        except SlackApiError as e:
            error_msg = f"Failed to invite {user.email} to Slack: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def delete_user(self, user_id: str) -> ConnectorResult:
        """Deactivate user in Slack workspace."""
        if self.mock_mode:
            return SlackMockConnector(self.config).delete_user(user_id)

        try:
            # Deactivate the user
            response = self.client.admin_users_deactivate(user=user_id)

            if response["ok"]:
                logger.info(f"Deactivated Slack user: {user_id}")
                return ConnectorResult(True, f"Deactivated Slack user {user_id}")
            else:
                error_msg = f"Failed to deactivate Slack user {user_id}: {response.get('error')}"
                logger.error(error_msg)
                return ConnectorResult(False, error_msg)

        except SlackApiError as e:
            error_msg = f"Failed to deactivate Slack user {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def add_to_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Add user to Slack channel."""
        if self.mock_mode:
            return SlackMockConnector(self.config).add_to_group(user_id, group_name)

        try:
            # Invite user to channel
            channel_id = self._get_channel_id(group_name)
            if not channel_id:
                # Try to create channel if it doesn't exist
                channel_id = self._create_channel(group_name)
                if not channel_id:
                    return ConnectorResult(False, f"Could not find or create channel {group_name}")

            response = self.client.conversations_invite(
                channel=channel_id,
                users=[user_id]
            )

            if response["ok"]:
                logger.info(f"Added {user_id} to Slack channel {group_name}")
                return ConnectorResult(True, f"Added {user_id} to channel {group_name}")
            else:
                error_msg = f"Failed to add {user_id} to channel {group_name}: {response.get('error')}"
                logger.error(error_msg)
                return ConnectorResult(False, error_msg)

        except SlackApiError as e:
            error_msg = f"Failed to add {user_id} to channel {group_name}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def remove_from_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Remove user from Slack channel."""
        if self.mock_mode:
            return SlackMockConnector(self.config).remove_from_group(user_id, group_name)

        try:
            channel_id = self._get_channel_id(group_name)
            if not channel_id:
                return ConnectorResult(False, f"Channel {group_name} not found")

            response = self.client.conversations_kick(
                channel=channel_id,
                user=user_id
            )

            if response["ok"]:
                logger.info(f"Removed {user_id} from Slack channel {group_name}")
                return ConnectorResult(True, f"Removed {user_id} from channel {group_name}")
            else:
                error_msg = f"Failed to remove {user_id} from channel {group_name}: {response.get('error')}"
                logger.error(error_msg)
                return ConnectorResult(False, error_msg)

        except SlackApiError as e:
            error_msg = f"Failed to remove {user_id} from channel {group_name}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def grant_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Grant role/permission (mapped to channel access for Slack)."""
        return self.add_to_group(user_id, role_name)

    def revoke_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Revoke role/permission (mapped to channel removal for Slack)."""
        return self.remove_from_group(user_id, role_name)

    def get_user(self, user_id: str) -> ConnectorResult:
        """Get Slack user information."""
        if self.mock_mode:
            return SlackMockConnector(self.config).get_user(user_id)

        try:
            response = self.client.users_info(user=user_id)

            if response["ok"]:
                user_data = response["user"]
                return ConnectorResult(True, f"Found Slack user {user_id}", user_data)
            else:
                return ConnectorResult(False, f"Slack user {user_id} not found: {response.get('error')}")

        except SlackApiError as e:
            if e.response["error"]["error"] == "user_not_found":
                return ConnectorResult(False, f"Slack user {user_id} not found")
            error_msg = f"Failed to get Slack user {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def list_user_permissions(self, user_id: str) -> ConnectorResult:
        """List user's channels and permissions in Slack."""
        if self.mock_mode:
            return SlackMockConnector(self.config).list_user_permissions(user_id)

        try:
            # Get user's channel memberships
            response = self.client.users_conversations(
                user=user_id,
                types="public_channel,private_channel"
            )

            if response["ok"]:
                channels = []
                for channel in response.get("channels", []):
                    channels.append({
                        "id": channel["id"],
                        "name": channel["name"],
                        "is_private": channel.get("is_private", False),
                        "is_member": True
                    })

                permissions = {
                    "channels": channels,
                    "workspace_member": True
                }

                return ConnectorResult(True, f"Permissions for {user_id}", permissions)
            else:
                error_msg = f"Failed to list channels for {user_id}: {response.get('error')}"
                logger.error(error_msg)
                return ConnectorResult(False, error_msg)

        except SlackApiError as e:
            error_msg = f"Failed to list permissions for {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def _get_channel_id(self, channel_name: str) -> Optional[str]:
        """Get channel ID by name."""
        try:
            # Remove # prefix if present
            if channel_name.startswith('#'):
                channel_name = channel_name[1:]

            response = self.client.conversations_list(
                types="public_channel,private_channel"
            )

            if response["ok"]:
                for channel in response.get("channels", []):
                    if channel["name"] == channel_name:
                        return channel["id"]

            return None

        except SlackApiError:
            return None

    def _create_channel(self, channel_name: str) -> Optional[str]:
        """Create a new channel and return its ID."""
        try:
            # Remove # prefix if present
            if channel_name.startswith('#'):
                channel_name = channel_name[1:]

            response = self.client.conversations_create(
                name=channel_name,
                is_private=False
            )

            if response["ok"]:
                channel_id = response["channel"]["id"]
                logger.info(f"Created Slack channel: {channel_name}")
                return channel_id

            return None

        except SlackApiError as e:
            logger.warning(f"Failed to create Slack channel {channel_name}: {e}")
            return None

    def _get_default_channels(self) -> str:
        """Get default channels for new users."""
        # This could be configured, but for now return general channel
        return "general"


class SlackMockConnector(MockConnector):
    """Mock implementation of Slack connector for testing."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        # Slack-specific mock state
        self.channels: Dict[str, List[str]] = {}  # channel_name -> list of user_ids
        self.pending_invitations: List[str] = []  # list of invited emails
