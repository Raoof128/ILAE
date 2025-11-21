"""
AWS IAM Connector for the JML Engine.

Provides integration with AWS Identity and Access Management (IAM) for
user account management, role assignments, and access key management.
"""

import logging
from typing import Any, Dict, List, Optional

from ..models import UserIdentity
from .base_connector import BaseConnector, ConnectorResult, MockConnector

# Optional imports for AWS SDK
try:
    import boto3  # noqa: F401
    from botocore.exceptions import ClientError  # noqa: F401

    AWS_SDK_AVAILABLE = True
except ImportError:
    AWS_SDK_AVAILABLE = False
    boto3 = None
    ClientError = Exception

logger = logging.getLogger(__name__)


class AWSConnector(BaseConnector):
    """AWS IAM connector for managing users, roles, and policies."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, mock_mode: bool = False):
        # Force mock mode if AWS SDK is not available
        if not AWS_SDK_AVAILABLE:
            mock_mode = True
            logger.warning("AWS SDK not available, using mock mode")

        super().__init__(config, mock_mode)

        if not mock_mode and AWS_SDK_AVAILABLE:
            # Initialize AWS clients
            self.iam_client = boto3.client(
                "iam",
                aws_access_key_id=config.get("aws_access_key_id"),
                aws_secret_access_key=config.get("aws_secret_access_key"),
                region_name=config.get("region", "us-east-1"),
            )
            self.sts_client = boto3.client(
                "sts",
                aws_access_key_id=config.get("aws_access_key_id"),
                aws_secret_access_key=config.get("aws_secret_access_key"),
                region_name=config.get("region", "us-east-1"),
            )
        else:
            self.iam_client = None
            self.sts_client = None

    def create_user(self, user: UserIdentity) -> ConnectorResult:
        """Create an IAM user account."""
        if self.mock_mode:
            return AWSMockConnector(self.config).create_user(user)

        try:
            username = self._generate_username(user)

            # Create the user
            response = self.iam_client.create_user(
                UserName=username,
                Tags=[
                    {"Key": "EmployeeID", "Value": user.employee_id},
                    {"Key": "Email", "Value": user.email},
                    {"Key": "Department", "Value": user.department},
                    {"Key": "ManagedBy", "Value": "JML-Engine"},
                ],
            )

            user_id = response["User"]["UserId"]
            logger.info(f"Created AWS IAM user: {username} (ID: {user_id})")
            return ConnectorResult(
                True, f"Created IAM user {username}", {"user_id": user_id, "username": username}
            )

        except ClientError as e:
            error_msg = f"Failed to create IAM user: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def delete_user(self, user_id: str) -> ConnectorResult:
        """Delete/deactivate an IAM user."""
        if self.mock_mode:
            return AWSMockConnector(self.config).delete_user(user_id)

        try:
            # First, list and remove all access keys
            access_keys = self.iam_client.list_access_keys(UserName=user_id)
            for key in access_keys.get("AccessKeyMetadata", []):
                self.iam_client.delete_access_key(UserName=user_id, AccessKeyId=key["AccessKeyId"])

            # Remove user from all groups
            groups = self.iam_client.list_groups_for_user(UserName=user_id)
            for group in groups.get("Groups", []):
                self.iam_client.remove_user_from_group(
                    UserName=user_id, GroupName=group["GroupName"]
                )

            # Detach all managed policies
            policies = self.iam_client.list_attached_user_policies(UserName=user_id)
            for policy in policies.get("AttachedPolicies", []):
                self.iam_client.detach_user_policy(UserName=user_id, PolicyArn=policy["PolicyArn"])

            # Delete inline policies
            inline_policies = self.iam_client.list_user_policies(UserName=user_id)
            for policy_name in inline_policies.get("PolicyNames", []):
                self.iam_client.delete_user_policy(UserName=user_id, PolicyName=policy_name)

            # Finally, delete the user
            self.iam_client.delete_user(UserName=user_id)

            logger.info(f"Deleted AWS IAM user: {user_id}")
            return ConnectorResult(True, f"Deleted IAM user {user_id}")

        except ClientError as e:
            error_msg = f"Failed to delete IAM user {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def add_to_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Add user to IAM group."""
        if self.mock_mode:
            return AWSMockConnector(self.config).add_to_group(user_id, group_name)

        try:
            # Ensure group exists
            try:
                self.iam_client.get_group(GroupName=group_name)
            except ClientError:
                # Create group if it doesn't exist
                self.iam_client.create_group(GroupName=group_name)
                logger.info(f"Created IAM group: {group_name}")

            # Add user to group
            self.iam_client.add_user_to_group(UserName=user_id, GroupName=group_name)

            logger.info(f"Added {user_id} to IAM group {group_name}")
            return ConnectorResult(True, f"Added {user_id} to group {group_name}")

        except ClientError as e:
            error_msg = f"Failed to add {user_id} to group {group_name}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def remove_from_group(self, user_id: str, group_name: str) -> ConnectorResult:
        """Remove user from IAM group."""
        if self.mock_mode:
            return AWSMockConnector(self.config).remove_from_group(user_id, group_name)

        try:
            self.iam_client.remove_user_from_group(UserName=user_id, GroupName=group_name)

            logger.info(f"Removed {user_id} from IAM group {group_name}")
            return ConnectorResult(True, f"Removed {user_id} from group {group_name}")

        except ClientError as e:
            error_msg = f"Failed to remove {user_id} from group {group_name}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def grant_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Attach IAM managed policy to user."""
        if self.mock_mode:
            return AWSMockConnector(self.config).grant_role(user_id, role_name)

        try:
            # Convert role name to policy ARN if it's a standard AWS policy
            policy_arn = self._get_policy_arn(role_name)

            self.iam_client.attach_user_policy(UserName=user_id, PolicyArn=policy_arn)

            logger.info(f"Attached policy {policy_arn} to user {user_id}")
            return ConnectorResult(True, f"Granted role {role_name} to {user_id}")

        except ClientError as e:
            error_msg = f"Failed to grant role {role_name} to {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def revoke_role(self, user_id: str, role_name: str) -> ConnectorResult:
        """Detach IAM managed policy from user."""
        if self.mock_mode:
            return AWSMockConnector(self.config).revoke_role(user_id, role_name)

        try:
            policy_arn = self._get_policy_arn(role_name)

            self.iam_client.detach_user_policy(UserName=user_id, PolicyArn=policy_arn)

            logger.info(f"Detached policy {policy_arn} from user {user_id}")
            return ConnectorResult(True, f"Revoked role {role_name} from {user_id}")

        except ClientError as e:
            error_msg = f"Failed to revoke role {role_name} from {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def get_user(self, user_id: str) -> ConnectorResult:
        """Get IAM user information."""
        if self.mock_mode:
            return AWSMockConnector(self.config).get_user(user_id)

        try:
            response = self.iam_client.get_user(UserName=user_id)
            user_data = response["User"]
            logger.debug(f"Retrieved IAM user: {user_id}")
            return ConnectorResult(True, f"Found user {user_id}", user_data)

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                return ConnectorResult(False, f"User {user_id} not found")
            error_msg = f"Failed to get user {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def list_user_permissions(self, user_id: str) -> ConnectorResult:
        """List all permissions for an IAM user."""
        if self.mock_mode:
            return AWSMockConnector(self.config).list_user_permissions(user_id)

        try:
            permissions = {"groups": [], "policies": [], "inline_policies": []}

            # Get groups
            groups_response = self.iam_client.list_groups_for_user(UserName=user_id)
            permissions["groups"] = [g["GroupName"] for g in groups_response.get("Groups", [])]

            # Get attached managed policies
            policies_response = self.iam_client.list_attached_user_policies(UserName=user_id)
            permissions["policies"] = [
                p["PolicyName"] for p in policies_response.get("AttachedPolicies", [])
            ]

            # Get inline policies
            inline_response = self.iam_client.list_user_policies(UserName=user_id)
            permissions["inline_policies"] = inline_response.get("PolicyNames", [])

            return ConnectorResult(True, f"Permissions for {user_id}", permissions)

        except ClientError as e:
            error_msg = f"Failed to list permissions for {user_id}: {e}"
            logger.error(error_msg)
            return ConnectorResult(False, error_msg, error=str(e))

    def _generate_username(self, user: UserIdentity) -> str:
        """Generate AWS IAM username from user identity."""
        # Use email prefix or employee ID
        base = user.email.split("@")[0] if "@" in user.email else user.employee_id

        # Clean up username (IAM usernames have restrictions)
        username = "".join(c for c in base if c.isalnum() or c in ["_", "-", "."])

        # Ensure length constraints
        if len(username) > 64:
            username = username[:64]
        if len(username) < 1:
            username = f"user_{user.employee_id}"

        return username

    def _get_policy_arn(self, role_name: str) -> str:
        """Convert role name to AWS policy ARN."""
        # Handle common AWS managed policies
        aws_policies = {
            "ReadOnlyAccess": "arn:aws:iam::aws:policy/ReadOnlyAccess",
            "AdministratorAccess": "arn:aws:iam::aws:policy/AdministratorAccess",
            "PowerUserAccess": "arn:aws:iam::aws:policy/PowerUserAccess",
            "SecurityAudit": "arn:aws:iam::aws:policy/SecurityAudit",
            "IAMReadOnly": "arn:aws:iam::aws:policy/IAMReadOnlyAccess",
            "EC2ReadOnly": "arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess",
            "S3ReadOnly": "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess",
            "CloudWatchReadOnly": "arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess",
            "EC2FullAccess": "arn:aws:iam::aws:policy/AmazonEC2FullAccess",
            "RDSFullAccess": "arn:aws:iam::aws:policy/AmazonRDSFullAccess",
            "LambdaFullAccess": "arn:aws:iam::aws:policy/AWSLambda_FullAccess",
            "AthenaFullAccess": "arn:aws:iam::aws:policy/AmazonAthenaFullAccess",
            "GlueFullAccess": "arn:aws:iam::aws:policy/AWSGlueConsoleFullAccess",
            "SESFullAccess": "arn:aws:iam::aws:policy/AmazonSESFullAccess",
            "DeviceFarmFullAccess": "arn:aws:iam::aws:policy/AWSDeviceFarmFullAccess",
            "CodePipelineFullAccess": "arn:aws:iam::aws:policy/AWSCodePipeline_FullAccess",
            "CodeBuildFullAccess": "arn:aws:iam::aws:policy/AWSCodeBuildAdminAccess",
            "CodeDeployFullAccess": "arn:aws:iam::aws:policy/AWSCodeDeployFullAccess",
            "ConfigFullAccess": "arn:aws:iam::aws:policy/AWSConfigUserAccess",
            "MacieFullAccess": "arn:aws:iam::aws:policy/AmazonMacieFullAccess",
            "EMRFullAccess": "arn:aws:iam::aws:policy/AmazonEMRFullAccess",
            "KinesisFullAccess": "arn:aws:iam::aws:policy/AmazonKinesisFullAccess",
            "DevOpsRole": "arn:aws:iam::aws:policy/ReadOnlyAccess",  # Placeholder
        }

        return aws_policies.get(role_name, f"arn:aws:iam::aws:policy/{role_name}")


class AWSMockConnector(MockConnector):
    """Mock implementation of AWS IAM connector for testing."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        # AWS-specific mock state
        self.policies: Dict[str, List[str]] = {}  # policy_name -> list of user_ids
