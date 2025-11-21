"""
Core data models for the JML Engine.

This module defines the Pydantic models used throughout the system
for HR events, user identities, access entitlements, and audit records.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, EmailStr


class LifecycleEvent(str, Enum):
    """HR lifecycle events that trigger IAM workflows."""
    NEW_STARTER = "NEW_STARTER"
    ROLE_CHANGE = "ROLE_CHANGE"
    DEPARTMENT_CHANGE = "DEPARTMENT_CHANGE"
    TERMINATION = "TERMINATION"
    CONTRACTOR_OFFBOARDING = "CONTRACTOR_OFFBOARDING"
    LEAVE_OF_ABSENCE = "LEAVE_OF_ABSENCE"
    RETURN_FROM_LEAVE = "RETURN_FROM_LEAVE"


class UserStatus(str, Enum):
    """Current status of a user identity."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    ON_LEAVE = "ON_LEAVE"


class HREvent(BaseModel):
    """Normalized HR event from various sources (Workday, BambooHR, CSV, etc.)."""
    event: LifecycleEvent
    employee_id: str = Field(..., description="Unique employee identifier")
    name: str = Field(..., description="Full name of the employee")
    email: EmailStr = Field(..., description="Primary email address")
    department: str = Field(..., description="Department or business unit")
    title: str = Field(..., description="Job title or role")
    manager_email: Optional[EmailStr] = Field(None, description="Manager's email")
    start_date: Optional[datetime] = Field(None, description="Employment start date")
    end_date: Optional[datetime] = Field(None, description="Employment end date")
    location: Optional[str] = Field(None, description="Office location")
    contract_type: Optional[str] = Field("PERMANENT", description="PERMANENT/CONTRACTOR/etc.")
    previous_department: Optional[str] = Field(None, description="Previous department for mover events")
    previous_title: Optional[str] = Field(None, description="Previous title for mover events")
    event_timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_system: str = Field(..., description="Source of the event (Workday, BambooHR, etc.)")
    raw_data: Optional[Dict[str, Any]] = Field(None, description="Original raw event data")


class AccessEntitlement(BaseModel):
    """Represents an access entitlement for a specific system."""
    system: str = Field(..., description="Target system (aws, azure, github, etc.)")
    resource_type: str = Field(..., description="Type of resource (role, group, team, etc.)")
    resource_name: str = Field(..., description="Name of the specific resource")
    permission_level: Optional[str] = Field(None, description="Permission level (read, write, admin, etc.)")
    granted_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None, description="Expiration date if applicable")


class UserIdentity(BaseModel):
    """Complete user identity with all access entitlements."""
    employee_id: str
    name: str
    email: EmailStr
    department: str
    title: str
    status: UserStatus = UserStatus.ACTIVE
    entitlements: List[AccessEntitlement] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_hr_event: Optional[HREvent] = None


class AuditRecord(BaseModel):
    """Audit record for compliance and reporting."""
    id: str = Field(..., description="Unique audit record ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(..., description="Type of event (provision, revoke, update, etc.)")
    employee_id: str
    user_email: EmailStr
    system: str = Field(..., description="Target system affected")
    action: str = Field(..., description="Specific action taken")
    resource: str = Field(..., description="Resource affected")
    success: bool = Field(..., description="Whether the action succeeded")
    error_message: Optional[str] = Field(None, description="Error details if failed")
    evidence_path: Optional[str] = Field(None, description="Path to evidence file")
    workflow_id: Optional[str] = Field(None, description="ID of the workflow that triggered this")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowResult(BaseModel):
    """Result of a complete workflow execution."""
    workflow_id: str
    employee_id: str
    event_type: LifecycleEvent
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = True
    actions_taken: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    audit_records: List[AuditRecord] = Field(default_factory=list)


class AccessProfile(BaseModel):
    """Access profile defining entitlements for a department/title combination."""
    department: str
    title: Optional[str] = None
    aws_roles: List[str] = Field(default_factory=list)
    azure_groups: List[str] = Field(default_factory=list)
    github_teams: List[str] = Field(default_factory=list)
    google_groups: List[str] = Field(default_factory=list)
    slack_channels: List[str] = Field(default_factory=list)
    description: Optional[str] = Field(None, description="Human-readable description")


class SystemCredentials(BaseModel):
    """Credentials for connecting to various systems."""
    system: str
    credentials: Dict[str, Any]  # Contains API keys, tokens, etc.
    mock_mode: bool = Field(False, description="Whether to use mock/simulated backend")


# Type aliases for convenience
HREvents = List[HREvent]
UserIdentities = List[UserIdentity]
AuditRecords = List[AuditRecord]
