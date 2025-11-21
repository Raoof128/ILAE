"""
FastAPI Server for the JML Engine.

Provides REST API endpoints for HR event processing, user management,
audit retrieval, and system administration.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..audit import AuditLogger, EvidenceStore
from ..engine import PolicyMapper, StateManager
from ..ingestion import HREventListener
from ..models import HREvent
from ..workflows import (
    JoinerWorkflow,
    LeaverWorkflow,
    MoverWorkflow,
    determine_workflow_type,
    validate_hr_event,
)

logger = logging.getLogger(__name__)


# Pydantic models for API requests/responses
class HREventRequest(BaseModel):
    """HR Event submission request."""
    event: str = Field(..., description="Event type (NEW_STARTER, ROLE_CHANGE, TERMINATION, etc.)")
    employee_id: str = Field(..., description="Unique employee identifier")
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Work email address")
    department: str = Field(..., description="Department name")
    title: str = Field(..., description="Job title")
    manager_email: Optional[str] = Field(None, description="Manager's email")
    start_date: Optional[str] = Field(None, description="Employment start date (ISO format)")
    end_date: Optional[str] = Field(None, description="Employment end date (ISO format)")
    location: Optional[str] = Field(None, description="Office location")
    contract_type: Optional[str] = Field("PERMANENT", description="Contract type")
    previous_department: Optional[str] = Field(None, description="Previous department (for movers)")
    previous_title: Optional[str] = Field(None, description="Previous title (for movers)")
    source_system: Optional[str] = Field("API", description="Source system name")


class WorkflowResponse(BaseModel):
    """Workflow execution response."""
    workflow_id: str
    employee_id: str
    event_type: str
    status: str
    started_at: str
    completed_at: Optional[str]
    success: bool
    total_steps: int
    successful_steps: int
    failed_steps: int
    errors: List[str]


class UserResponse(BaseModel):
    """User identity response."""
    employee_id: str
    name: str
    email: str
    department: str
    title: str
    status: str
    entitlements_count: int
    created_at: str
    updated_at: str


class AuditResponse(BaseModel):
    """Audit record response."""
    id: str
    timestamp: str
    employee_id: str
    event_type: str
    system: str
    action: str
    resource: str
    success: bool
    error_message: Optional[str]
    workflow_id: Optional[str]
    evidence_path: Optional[str]


class SimulationRequest(BaseModel):
    """Workflow simulation request."""
    event_type: str = Field(..., description="Type of event to simulate")
    mock_mode: bool = Field(True, description="Use mock connectors")
    disabled_systems: Optional[List[str]] = Field(None, description="Systems to skip")


# Global components (initialized on startup)
hr_listener: Optional[HREventListener] = None
policy_mapper: Optional[PolicyMapper] = None
state_manager: Optional[StateManager] = None
audit_logger: Optional[AuditLogger] = None
evidence_store: Optional[EvidenceStore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global hr_listener, policy_mapper, state_manager, audit_logger, evidence_store

    # Initialize components on startup
    logger.info("Initializing JML Engine API server components")

    hr_listener = HREventListener()
    policy_mapper = PolicyMapper()
    state_manager = StateManager()
    audit_logger = AuditLogger()
    evidence_store = EvidenceStore()

    logger.info("JML Engine API server components initialized")

    yield

    # Cleanup on shutdown
    logger.info("Shutting down JML Engine API server")


# Create FastAPI app
app = FastAPI(
    title="JML Engine API",
    description="IAM Lifecycle Automation Engine - REST API for Joiner-Mover-Leaver workflows",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "JML Engine API", "version": "1.0.0", "status": "running"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "hr_listener": hr_listener is not None,
            "policy_mapper": policy_mapper is not None,
            "state_manager": state_manager is not None,
            "audit_logger": audit_logger is not None,
            "evidence_store": evidence_store is not None
        }
    }


@app.post("/event/hr", response_model=WorkflowResponse)
async def process_hr_event(event_request: HREventRequest, background_tasks: BackgroundTasks):
    """
    Process an HR event and execute the appropriate workflow.

    This endpoint accepts HR events and automatically determines which
    workflow (Joiner/Mover/Leaver) should handle the event.
    """
    try:
        # Convert request to HREvent
        hr_event = HREvent(
            event=event_request.event,
            employee_id=event_request.employee_id,
            name=event_request.name,
            email=event_request.email,
            department=event_request.department,
            title=event_request.title,
            manager_email=event_request.manager_email,
            start_date=datetime.fromisoformat(event_request.start_date) if event_request.start_date else None,
            end_date=datetime.fromisoformat(event_request.end_date) if event_request.end_date else None,
            location=event_request.location,
            contract_type=event_request.contract_type or "PERMANENT",
            previous_department=event_request.previous_department,
            previous_title=event_request.previous_title,
            source_system=event_request.source_system or "API"
        )

        # Validate the event
        validation_errors = validate_hr_event(hr_event)
        if validation_errors:
            raise HTTPException(status_code=400, detail=f"Invalid HR event: {', '.join(validation_errors)}")

        # Determine workflow type
        workflow_type = determine_workflow_type(hr_event)

        # Execute workflow in background
        background_tasks.add_task(execute_workflow_async, hr_event, workflow_type)

        return WorkflowResponse(
            workflow_id=f"temp_{hr_event.employee_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            employee_id=hr_event.employee_id,
            event_type=hr_event.event,
            status="accepted",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
            success=True,
            total_steps=0,
            successful_steps=0,
            failed_steps=0,
            errors=[]
        )

    except Exception as e:
        logger.error(f"Error processing HR event: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/user/{employee_id}", response_model=UserResponse)
async def get_user(employee_id: str):
    """Get user identity information."""
    if not state_manager:
        raise HTTPException(status_code=503, detail="State manager not available")

    identity = state_manager.get_identity(employee_id)
    if not identity:
        raise HTTPException(status_code=404, detail=f"User {employee_id} not found")

    return UserResponse(
        employee_id=identity.employee_id,
        name=identity.name,
        email=identity.email,
        department=identity.department,
        title=identity.title,
        status=identity.status.value,
        entitlements_count=len(identity.entitlements),
        created_at=identity.created_at.isoformat(),
        updated_at=identity.updated_at.isoformat()
    )


@app.get("/users", response_model=List[UserResponse])
async def list_users(
    department: Optional[str] = Query(None, description="Filter by department"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, description="Maximum number of results")
):
    """List user identities with optional filtering."""
    if not state_manager:
        raise HTTPException(status_code=503, detail="State manager not available")

    identities = state_manager.get_all_identities()

    # Apply filters
    if department:
        identities = [i for i in identities if i.department == department]

    if status:
        identities = [i for i in identities if i.status.value == status]

    # Convert to response format
    users = [
        UserResponse(
            employee_id=i.employee_id,
            name=i.name,
            email=i.email,
            department=i.department,
            title=i.title,
            status=i.status.value,
            entitlements_count=len(i.entitlements),
            created_at=i.created_at.isoformat(),
            updated_at=i.updated_at.isoformat()
        )
        for i in identities[:limit]
    ]

    return users


@app.get("/audit", response_model=List[AuditResponse])
async def get_audit_logs(
    employee_id: Optional[str] = Query(None, description="Filter by employee ID"),
    system: Optional[str] = Query(None, description="Filter by system"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    days_back: int = Query(30, description="Number of days to look back"),
    limit: int = Query(100, description="Maximum number of results")
):
    """Get audit logs with optional filtering."""
    if not audit_logger:
        raise HTTPException(status_code=503, detail="Audit logger not available")

    # This is a simplified implementation - in practice, you'd want more sophisticated filtering
    # For now, just return recent logs
    logs = []

    # In a real implementation, you'd query the audit logs with filters
    # For this demo, return empty list
    return logs


@app.post("/simulate/{workflow_type}", response_model=WorkflowResponse)
async def simulate_workflow(
    workflow_type: str,
    request: SimulationRequest,
    background_tasks: BackgroundTasks
):
    """
    Simulate a workflow execution for testing purposes.

    This endpoint allows testing workflows without affecting real systems.
    """
    if workflow_type not in ["joiner", "mover", "leaver"]:
        raise HTTPException(status_code=400, detail="Invalid workflow type. Must be: joiner, mover, leaver")

    try:
        # Create a sample HR event based on workflow type
        hr_event = create_sample_hr_event(request.event_type)

        # Execute workflow in background with mock mode
        config = {
            "mock_mode": True,
            "disabled_systems": request.disabled_systems or []
        }

        background_tasks.add_task(execute_workflow_async, hr_event, workflow_type, config)

        return WorkflowResponse(
            workflow_id=f"sim_{workflow_type}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            employee_id=hr_event.employee_id,
            event_type=hr_event.event,
            status="simulation_started",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
            success=True,
            total_steps=0,
            successful_steps=0,
            failed_steps=0,
            errors=[]
        )

    except Exception as e:
        logger.error(f"Error starting workflow simulation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/stats")
async def get_system_stats():
    """Get system statistics and health metrics."""
    if not state_manager or not audit_logger or not evidence_store:
        raise HTTPException(status_code=503, detail="System components not available")

    try:
        identity_stats = state_manager.get_identities_summary()
        evidence_stats = evidence_store.get_evidence_stats()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "identities": identity_stats,
            "evidence": evidence_stats,
            "supported_formats": hr_listener.get_supported_formats() if hr_listener else []
        }

    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


async def execute_workflow_async(hr_event: HREvent, workflow_type: str, config: Optional[Dict[str, Any]] = None):
    """Execute workflow asynchronously."""
    try:
        config = config or {"mock_mode": True}

        if workflow_type == "joiner":
            workflow = JoinerWorkflow(config)
        elif workflow_type == "mover":
            workflow = MoverWorkflow(config)
        elif workflow_type == "leaver":
            workflow = LeaverWorkflow(config)
        else:
            logger.error(f"Unknown workflow type: {workflow_type}")
            return

        result = workflow.execute(hr_event)

        logger.info(f"Workflow {workflow_type} completed for {hr_event.employee_id}: "
                   f"success={result.success}, steps={len(result.actions_taken)}")

    except Exception as e:
        logger.error(f"Error executing workflow {workflow_type} for {hr_event.employee_id}: {e}")


def create_sample_hr_event(event_type: str) -> HREvent:
    """Create a sample HR event for simulation."""
    base_event = {
        "employee_id": f"SAMPLE_{datetime.now(timezone.utc).strftime('%H%M%S')}",
        "name": "Sample User",
        "email": f"sample.{datetime.now(timezone.utc).strftime('%H%M%S')}@company.com",
        "department": "Engineering",
        "title": "Software Engineer",
        "source_system": "API_SIMULATION"
    }

    if event_type == "NEW_STARTER":
        return HREvent(event="NEW_STARTER", **base_event)
    elif event_type == "ROLE_CHANGE":
        return HREvent(
            event="ROLE_CHANGE",
            previous_department="Engineering",
            previous_title="Junior Engineer",
            **base_event
        )
    elif event_type == "TERMINATION":
        return HREvent(event="TERMINATION", **base_event)
    else:
        raise ValueError(f"Unsupported event type for simulation: {event_type}")


def start_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Start the FastAPI server."""
    uvicorn.run(
        "jml_engine.api.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


if __name__ == "__main__":
    start_server()
