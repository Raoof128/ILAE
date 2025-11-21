"""
GitHub Connector for the JML Engine.

Provides integration with GitHub for organization membership,
team management, and repository access control.
"""

import logging
from typing import Any, Dict, List, Optional

from ..models import UserIdentity
from .base_connector import BaseConnector, ConnectorResult, MockConnector

# Optional imports for GitHub SDK
try:
    from github import Github, GithubException
    from github.NamedUser import NamedUser
    from github.Organization import Organization
    from github.Team import Team
    GITHUB_SDK_AVAILABLE = True
except ImportError:
    GITHUB_SDK_AVAILABLE = False
    Github = None
    GithubException = Exception
    Organization = None
    Team = None
    NamedUser = None

logger = logging.getLogger(__name__)


class GitHubConnector(BaseConnector):
    """GitHub connector for managing organization members and teams."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, mock_mode: bool = False):
        # Force mock mode if GitHub SDK is not available
        if not GITHUB_SDK_AVAILABLE:
            mock_mode = True
            logger.warning("GitHub SDK not available, using mock mode")

        super().__init__(config, mock_mode)

        if not mock_mode and GITHUB_SDK_AVAILABLE:
            token = config.get('github_token') or config.get('token')
            if not token:
                raise ValueError("GitHub token is required for real mode")

            self.github = Github(token)
            self.org_name = config.get('organization') or config.get('org')
            if not self.org_name:
                raise ValueError("GitHub organization name is required")

            try:
                self.org = self.github.get_organization(self.org_name)
            except GithubException as e:
                raise ValueError(f"Failed to access GitHub organization {self.org_name}: {e}") from e
        else:
            self.github = None
            self.org = None
            self.org_name = config.get('organization', 'mock-org') if config else 'mock-org'

    def create_user(self, user: UserIdentity) -> ConnectorResult:
        """Invite user to GitHub organization."""
        if self.mock_mode:
            return GitHubMockConnector(self.config).create_user(user)

        try:
            # Send invitation to organization
            invitation = self.org.invite_user(
                email=user.email,
                role='member'  # Can be 'member' or 'admin'
            )

            logger.info(f"Sent GitHub invitation to {user.email} for org {self.org_name}")
            return ConnectorResult(True, f"Invited {user.email} to GitHub organization",
                                 {"invitation_id": invitation.id if hasattr(invitation, 'id') else None})

        except GithubException as e:
            error_msg = f"Failed to invite {user.email} to GitHub: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def delete_user(self, user_id: str) -> ConnectorResult:
        """Remove user from GitHub organization."""
        if self.mock_mode:
            return GitHubMockConnector(self.config).delete_user(user_id)

        try:
            # Get user object (user_id should be GitHub username)
            user = self.github.get_user(user_id)

            # Remove from organization
            self.org.remove_from_membership(user)

            logger.info(f"Removed {user_id} from GitHub organization {self.org_name}")
            return ConnectorResult(True, f"Removed {user_id} from GitHub organization")

        except GithubException as e:
            error_msg = f"Failed to remove {user_id} from GitHub: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def add_to_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Add user to GitHub team."""
        if self.mock_mode:
            return GitHubMockConnector(self.config).add_to_group(user_id, group_name)

        try:
            # Get or create team
            team = self._get_or_create_team(group_name)

            # Get user object
            user = self.github.get_user(user_id)

            # Add user to team
            team.add_membership(user, role='member')

            logger.info(f"Added {user_id} to GitHub team {group_name}")
            return ConnectorResult(True, f"Added {user_id} to team {group_name}")

        except GithubException as e:
            error_msg = f"Failed to add {user_id} to team {group_name}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def remove_from_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Remove user from GitHub team."""
        if self.mock_mode:
            return GitHubMockConnector(self.config).remove_from_group(user_id, group_name)

        try:
            # Get team
            team = self._get_team(group_name)
            if not team:
                return ConnectorResult(False, f"Team {group_name} not found")

            # Get user object
            user = self.github.get_user(user_id)

            # Remove user from team
            team.remove_membership(user)

            logger.info(f"Removed {user_id} from GitHub team {group_name}")
            return ConnectorResult(True, f"Removed {user_id} from team {group_name}")

        except GithubException as e:
            error_msg = f"Failed to remove {user_id} from team {group_name}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def grant_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Grant role/permission (mapped to team membership for GitHub)."""
        # For GitHub, roles are typically handled through teams
        # This maps role names to team names
        return self.add_to_group(user_id, role_name)

    def revoke_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Revoke role/permission (mapped to team removal for GitHub)."""
        return self.remove_from_group(user_id, role_name)

    def get_user(self, user_id: str) -> ConnectorResult:
        """Get GitHub user information."""
        if self.mock_mode:
            return GitHubMockConnector(self.config).get_user(user_id)

        try:
            user = self.github.get_user(user_id)

            user_data = {
                "id": user.id,
                "login": user.login,
                "name": user.name,
                "email": user.email,
                "company": user.company,
                "location": user.location,
                "bio": user.bio
            }

            return ConnectorResult(True, f"Found GitHub user {user_id}", user_data)

        except GithubException as e:
            if e.status == 404:
                return ConnectorResult(False, f"GitHub user {user_id} not found")
            error_msg = f"Failed to get GitHub user {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def list_user_permissions(self, user_id: str) -> ConnectorResult:
        """List user's teams and permissions in the organization."""
        if self.mock_mode:
            return GitHubMockConnector(self.config).list_user_permissions(user_id)

        try:
            # Get user object
            user = self.github.get_user(user_id)

            # Check if user is a member of the org
            try:
                membership = self.org.get_membership(user)
                is_member = membership is not None
            except GithubException:
                is_member = False

            if not is_member:
                return ConnectorResult(False, f"User {user_id} is not a member of {self.org_name}")

            # Get all teams user belongs to
            teams = []
            for team in self.org.get_teams():
                try:
                    if team.has_in_members(user):
                        teams.append({
                            "name": team.name,
                            "slug": team.slug,
                            "role": "maintainer" if team.has_in_members(user, "maintainer") else "member"
                        })
                except GithubException:
                    continue

            permissions = {
                "is_member": is_member,
                "teams": teams,
                "organization_role": membership.role if membership else None
            }

            return ConnectorResult(True, f"Permissions for {user_id}", permissions)

        except GithubException as e:
            error_msg = f"Failed to list permissions for {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def _get_or_create_team(self, team_name: str) -> Team:
        """Get existing team or create new one."""
        try:
            return self._get_team(team_name)
        except GithubException:
            # Create new team
            team = self.org.create_team(
                name=team_name,
                privacy='closed'  # Can be 'closed' or 'secret'
            )
            logger.info(f"Created GitHub team: {team_name}")
            return team

    def _get_team(self, team_name: str) -> Optional[Team]:
        """Get team by name."""
        for team in self.org.get_teams():
            if team.name == team_name or team.slug == team_name:
                return team
        return None


class GitHubMockConnector(MockConnector):
    """Mock implementation of GitHub connector for testing."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        # GitHub-specific mock state
        self.teams: Dict[str, List[str]] = {}  # team_name -> list of user_ids
        self.pending_invitations: List[str] = []  # list of invited emails
