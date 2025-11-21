"""
Google Workspace Connector for the JML Engine.

Provides integration with Google Workspace (formerly G Suite)
for user account management, group memberships, and organizational units.
"""

import logging
from typing import Any, Dict, List, Optional

from ..models import UserIdentity
from .base_connector import BaseConnector, ConnectorResult, MockConnector

# Optional imports for Google API SDK
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_SDK_AVAILABLE = True
except ImportError:
    GOOGLE_SDK_AVAILABLE = False
    build = None
    HttpError = Exception
    service_account = None

logger = logging.getLogger(__name__)


class GoogleConnector(BaseConnector):
    """Google Workspace connector for managing users and groups."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, mock_mode: bool = False):
        # Force mock mode if Google SDK is not available
        if not GOOGLE_SDK_AVAILABLE:
            mock_mode = True
            logger.warning("Google SDK not available, using mock mode")

        super().__init__(config, mock_mode)

        if not mock_mode and GOOGLE_SDK_AVAILABLE:
            # Initialize Google API clients
            credentials_path = config.get('credentials_path') or config.get('service_account_file')
            if not credentials_path:
                raise ValueError("Google service account credentials path is required")

            credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=[
                    'https://www.googleapis.com/auth/admin.directory.user',
                    'https://www.googleapis.com/auth/admin.directory.group',
                    'https://www.googleapis.com/auth/admin.directory.group.member'
                ]
            )

            # Impersonate domain admin
            domain_admin = config.get('domain_admin')
            if domain_admin:
                credentials = credentials.with_subject(domain_admin)

            self.directory_service = build('admin', 'directory_v1', credentials=credentials)
            self.domain = config.get('domain')
            if not self.domain:
                raise ValueError("Google Workspace domain is required")
        else:
            self.directory_service = None
            self.domain = config.get('domain', 'mock-domain.com') if config else 'mock-domain.com'

    def create_user(self, user: UserIdentity) -> ConnectorResult:
        """Create user in Google Workspace."""
        if self.mock_mode:
            return GoogleMockConnector(self.config).create_user(user)

        try:
            user_body = {
                'primaryEmail': user.email,
                'name': {
                    'givenName': user.name.split()[0] if user.name else '',
                    'familyName': ' '.join(user.name.split()[1:]) if user.name and len(user.name.split()) > 1 else ''
                },
                'password': self._generate_temp_password(),
                'changePasswordAtNextLogin': True,
                'orgUnitPath': self._get_org_unit_path(user.department)
            }

            result = self.directory_service.users().insert(body=user_body).execute()

            logger.info(f"Created Google Workspace user: {user.email}")
            return ConnectorResult(True, f"Created Google Workspace user {user.email}",
                                 {"user_id": result.get('id')})

        except HttpError as e:
            error_msg = f"Failed to create Google Workspace user {user.email}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def delete_user(self, user_id: str) -> ConnectorResult:
        """Suspend user in Google Workspace."""
        if self.mock_mode:
            return GoogleMockConnector(self.config).delete_user(user_id)

        try:
            # Suspend user instead of deleting (Google recommends suspension)
            user_body = {'suspended': True}
            self.directory_service.users().update(userKey=user_id, body=user_body).execute()

            logger.info(f"Suspended Google Workspace user: {user_id}")
            return ConnectorResult(True, f"Suspended Google Workspace user {user_id}")

        except HttpError as e:
            error_msg = f"Failed to suspend Google Workspace user {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def add_to_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Add user to Google Group."""
        if self.mock_mode:
            return GoogleMockConnector(self.config).add_to_group(user_id, group_name)

        try:
            # Ensure group exists
            group_email = self._ensure_group_exists(group_name)

            # Add member to group
            member_body = {
                'email': user_id if '@' in user_id else f"{user_id}@{self.domain}",
                'role': 'MEMBER'
            }

            self.directory_service.members().insert(
                groupKey=group_email,
                body=member_body
            ).execute()

            logger.info(f"Added {user_id} to Google Group {group_name}")
            return ConnectorResult(True, f"Added {user_id} to Google Group {group_name}")

        except HttpError as e:
            error_msg = f"Failed to add {user_id} to Google Group {group_name}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def remove_from_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Remove user from Google Group."""
        if self.mock_mode:
            return GoogleMockConnector(self.config).remove_from_group(user_id, group_name)

        try:
            group_email = f"{group_name}@{self.domain}"

            member_email = user_id if '@' in user_id else f"{user_id}@{self.domain}"

            self.directory_service.members().delete(
                groupKey=group_email,
                memberKey=member_email
            ).execute()

            logger.info(f"Removed {user_id} from Google Group {group_name}")
            return ConnectorResult(True, f"Removed {user_id} from Google Group {group_name}")

        except HttpError as e:
            error_msg = f"Failed to remove {user_id} from Google Group {group_name}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def grant_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Grant role/permission (mapped to group membership for Google)."""
        return self.add_to_group(user_id, role_name)

    def revoke_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Revoke role/permission (mapped to group removal for Google)."""
        return self.remove_from_group(user_id, role_name)

    def get_user(self, user_id: str) -> ConnectorResult:
        """Get Google Workspace user information."""
        if self.mock_mode:
            return GoogleMockConnector(self.config).get_user(user_id)

        try:
            result = self.directory_service.users().get(userKey=user_id).execute()

            user_data = {
                "id": result.get("id"),
                "primaryEmail": result.get("primaryEmail"),
                "name": result.get("name", {}),
                "suspended": result.get("suspended", False),
                "orgUnitPath": result.get("orgUnitPath")
            }

            return ConnectorResult(True, f"Found Google Workspace user {user_id}", user_data)

        except HttpError as e:
            if e.resp.status == 404:
                return ConnectorResult(False, f"Google Workspace user {user_id} not found")
            error_msg = f"Failed to get Google Workspace user {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def list_user_permissions(self, user_id: str) -> ConnectorResult:
        """List user's group memberships in Google Workspace."""
        if self.mock_mode:
            return GoogleMockConnector(self.config).list_user_permissions(user_id)

        try:
            member_email = user_id if '@' in user_id else f"{user_id}@{self.domain}"

            # Get all groups for the user
            result = self.directory_service.groups().list(userKey=member_email).execute()

            groups = []
            for group in result.get('groups', []):
                groups.append({
                    "email": group.get("email"),
                    "name": group.get("name"),
                    "description": group.get("description")
                })

            permissions = {
                "groups": groups,
                "org_unit": None  # Would need separate API call
            }

            return ConnectorResult(True, f"Permissions for {user_id}", permissions)

        except HttpError as e:
            error_msg = f"Failed to list permissions for {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def _ensure_group_exists(self, group_name: str) -> str:
        """Ensure Google Group exists, create if necessary."""
        group_email = f"{group_name}@{self.domain}"

        try:
            # Try to get the group
            self.directory_service.groups().get(groupKey=group_email).execute()
            return group_email
        except HttpError as e:
            if e.resp.status == 404:
                # Create the group
                group_body = {
                    'email': group_email,
                    'name': group_name,
                    'description': f"Auto-created group for {group_name}"
                }
                self.directory_service.groups().insert(body=group_body).execute()
                logger.info(f"Created Google Group: {group_email}")
                return group_email
            else:
                raise

    def _get_org_unit_path(self, department: str) -> str:
        """Get organizational unit path for department."""
        # This is a simple mapping - in practice, you'd have a more sophisticated lookup
        if department:
            return f"/{department}"
        return "/"

    def _generate_temp_password(self) -> str:
        """Generate a temporary password for new users."""
        # In production, you'd want a more secure password generation
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for i in range(12))


class GoogleMockConnector(MockConnector):
    """Mock implementation of Google Workspace connector for testing."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        # Google-specific mock state
        self.groups: Dict[str, List[str]] = {}  # group_name -> list of user_ids
        self.org_units: Dict[str, str] = {}     # user_id -> org_unit_path
