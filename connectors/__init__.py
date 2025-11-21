"""
Connectors Package for the JML Engine.

This package provides integrations with various IAM systems including
AWS, Azure, GitHub, Google Workspace, and Slack.
"""

from .base_connector import BaseConnector, MockConnector, ConnectorResult
from .aws_connector import AWSConnector, AWSMockConnector
from .azure_connector import AzureConnector, AzureMockConnector
from .github_connector import GitHubConnector, GitHubMockConnector
from .google_connector import GoogleConnector, GoogleMockConnector
from .slack_connector import SlackConnector, SlackMockConnector

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
