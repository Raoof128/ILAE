"""
Connectors Package for the JML Engine.

This package provides integrations with various IAM systems including
AWS, Azure, GitHub, Google Workspace, and Slack.
"""

from .base_connector import BaseConnector, ConnectorResult, MockConnector


# Lazy imports to avoid SDK dependencies during testing
def _get_connector_class(system: str, mock: bool = False):
    """Get connector class for a system, with fallback to mock."""
    if mock:
        return MockConnector

    # Try to import real connector, fallback to mock
    try:
        if system == "aws":
            from .aws_connector import AWSConnector

            return AWSConnector
        elif system == "azure":
            from .azure_connector import AzureConnector

            return AzureConnector
        elif system == "github":
            from .github_connector import GitHubConnector

            return GitHubConnector
        elif system == "google":
            from .google_connector import GoogleConnector

            return GoogleConnector
        elif system == "slack":
            from .slack_connector import SlackConnector

            return SlackConnector
    except ImportError:
        pass

    # Fallback to mock connector
    return MockConnector


# For backward compatibility - these will be None if SDKs not available
AWSConnector = None
AzureConnector = None
GitHubConnector = None
GoogleConnector = None
SlackConnector = None

__all__ = [
    "BaseConnector",
    "MockConnector",
    "ConnectorResult",
    "AWSConnector",
    "AWSMockConnector",
    "AzureConnector",
    "AzureMockConnector",
    "GitHubConnector",
    "GitHubMockConnector",
    "GoogleConnector",
    "GoogleMockConnector",
    "SlackConnector",
    "SlackMockConnector",
]
