"""
State Manager for the JML Engine.

Manages the current state of user identities and their access entitlements.
Provides persistence and retrieval of identity information for workflow processing.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..models import AccessEntitlement, HREvent, UserIdentity, UserStatus

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages the state of user identities and their access entitlements.

    Provides in-memory state management with optional JSON file persistence.
    Tracks current access state for comparison during mover/leaver workflows.
    """

    def __init__(self, storage_path: Optional[Union[str, Path]] = None):
        """
        Initialize the state manager.

        Args:
            storage_path: Path to store identity state as JSON.
                         If None, state is kept in memory only.
        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.identities: Dict[str, UserIdentity] = {}

        # Create storage directory if needed
        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_state()

        logger.info(
            f"Initialized StateManager with {'persistent' if self.storage_path else 'in-memory'} storage"
        )

    def get_identity(self, employee_id: str) -> Optional[UserIdentity]:
        """
        Get the current identity for an employee.

        Args:
            employee_id: Employee ID to look up

        Returns:
            UserIdentity if found, None otherwise
        """
        return self.identities.get(employee_id)

    def get_identity_by_email(self, email: str) -> Optional[UserIdentity]:
        """
        Get identity by email address.

        Args:
            email: Email address to search for

        Returns:
            UserIdentity if found, None otherwise
        """
        for identity in self.identities.values():
            if identity.email.lower() == email.lower():
                return identity
        return None

    def create_or_update_identity(
        self, hr_event: HREvent, entitlements: Optional[List[AccessEntitlement]] = None
    ) -> UserIdentity:
        """
        Create or update a user identity based on an HR event.

        Args:
            hr_event: HR event containing user information
            entitlements: Current access entitlements for the user

        Returns:
            Updated UserIdentity
        """
        employee_id = hr_event.employee_id
        existing = self.identities.get(employee_id)

        if existing:
            # Update existing identity
            existing.name = hr_event.name
            existing.email = hr_event.email
            existing.department = hr_event.department
            existing.title = hr_event.title
            existing.updated_at = datetime.now(timezone.utc)
            existing.last_hr_event = hr_event

            # Update status based on event type
            existing.status = self._determine_status_from_event(hr_event)

            # Update entitlements if provided
            if entitlements is not None:
                existing.entitlements = entitlements

            identity = existing
            logger.info(f"Updated identity for employee {employee_id}")
        else:
            # Create new identity
            identity = UserIdentity(
                employee_id=employee_id,
                name=hr_event.name,
                email=hr_event.email,
                department=hr_event.department,
                title=hr_event.title,
                status=self._determine_status_from_event(hr_event),
                entitlements=entitlements or [],
                last_hr_event=hr_event,
            )
            self.identities[employee_id] = identity
            logger.info(f"Created new identity for employee {employee_id}")

        self._save_state()
        return identity

    def update_entitlements(self, employee_id: str, entitlements: List[AccessEntitlement]) -> bool:
        """
        Update the access entitlements for a user.

        Args:
            employee_id: Employee ID to update
            entitlements: New list of access entitlements

        Returns:
            True if update was successful, False if user not found
        """
        identity = self.identities.get(employee_id)
        if not identity:
            logger.warning(f"Cannot update entitlements: employee {employee_id} not found")
            return False

        identity.entitlements = entitlements
        identity.updated_at = datetime.now(timezone.utc)

        self._save_state()
        logger.info(
            f"Updated entitlements for employee {employee_id}: {len(entitlements)} entitlements"
        )
        return True

    def add_entitlement(self, employee_id: str, entitlement: AccessEntitlement) -> bool:
        """
        Add a single entitlement to a user's access.

        Args:
            employee_id: Employee ID
            entitlement: Entitlement to add

        Returns:
            True if added successfully, False if user not found or entitlement already exists
        """
        identity = self.identities.get(employee_id)
        if not identity:
            return False

        # Check if entitlement already exists
        for existing in identity.entitlements:
            if (
                existing.system == entitlement.system
                and existing.resource_type == entitlement.resource_type
                and existing.resource_name == entitlement.resource_name
            ):
                logger.debug(f"Entitlement already exists for {employee_id}: {entitlement}")
                return False

        identity.entitlements.append(entitlement)
        identity.updated_at = datetime.now(timezone.utc)

        self._save_state()
        logger.info(
            f"Added entitlement to {employee_id}: {entitlement.system}/{entitlement.resource_name}"
        )
        return True

    def remove_entitlement(self, employee_id: str, system: str, resource_name: str) -> bool:
        """
        Remove a specific entitlement from a user's access.

        Args:
            employee_id: Employee ID
            system: System name (aws, azure, github, etc.)
            resource_name: Name of the resource to remove

        Returns:
            True if removed successfully, False if not found
        """
        identity = self.identities.get(employee_id)
        if not identity:
            return False

        original_count = len(identity.entitlements)
        identity.entitlements = [
            ent
            for ent in identity.entitlements
            if not (ent.system == system and ent.resource_name == resource_name)
        ]

        if len(identity.entitlements) < original_count:
            identity.updated_at = datetime.now(timezone.utc)
            self._save_state()
            logger.info(f"Removed entitlement from {employee_id}: {system}/{resource_name}")
            return True

        return False

    def deactivate_identity(self, employee_id: str) -> bool:
        """
        Mark a user identity as terminated/inactive.

        Args:
            employee_id: Employee ID to deactivate

        Returns:
            True if deactivated successfully, False if not found
        """
        identity = self.identities.get(employee_id)
        if not identity:
            return False

        identity.status = UserStatus.TERMINATED
        identity.updated_at = datetime.now(timezone.utc)

        self._save_state()
        logger.info(f"Deactivated identity for employee {employee_id}")
        return True

    def get_all_identities(self) -> List[UserIdentity]:
        """Get all user identities."""
        return list(self.identities.values())

    def get_identities_by_department(self, department: str) -> List[UserIdentity]:
        """Get all identities in a specific department."""
        return [
            identity for identity in self.identities.values() if identity.department == department
        ]

    def get_identities_by_status(self, status: UserStatus) -> List[UserIdentity]:
        """Get all identities with a specific status."""
        return [identity for identity in self.identities.values() if identity.status == status]

    def get_entitlements_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current entitlements across all users.

        Returns:
            Dictionary with entitlement statistics
        """
        summary = {
            "total_users": len(self.identities),
            "total_entitlements": 0,
            "entitlements_by_system": {},
            "users_by_department": {},
            "users_by_status": {},
        }

        for identity in self.identities.values():
            # Count entitlements
            summary["total_entitlements"] += len(identity.entitlements)

            # Count by system
            for entitlement in identity.entitlements:
                system = entitlement.system
                if system not in summary["entitlements_by_system"]:
                    summary["entitlements_by_system"][system] = 0
                summary["entitlements_by_system"][system] += 1

            # Count by department
            dept = identity.department
            if dept not in summary["users_by_department"]:
                summary["users_by_department"][dept] = 0
            summary["users_by_department"][dept] += 1

            # Count by status
            status = identity.status.value
            if status not in summary["users_by_status"]:
                summary["users_by_status"][status] = 0
            summary["users_by_status"][status] += 1

        return summary

    def _determine_status_from_event(self, event: HREvent) -> UserStatus:
        """Determine user status based on HR event type."""
        from ..models import LifecycleEvent

        if event.event == LifecycleEvent.TERMINATION:
            return UserStatus.TERMINATED
        elif event.event == LifecycleEvent.CONTRACTOR_OFFBOARDING:
            return UserStatus.TERMINATED
        elif event.event == LifecycleEvent.LEAVE_OF_ABSENCE:
            return UserStatus.ON_LEAVE
        elif event.event == LifecycleEvent.RETURN_FROM_LEAVE:
            return UserStatus.ACTIVE
        else:
            return UserStatus.ACTIVE

    def _save_state(self):
        """Save current state to persistent storage."""
        if not self.storage_path:
            return

        try:
            # Convert identities to dict for JSON serialization
            state_data = {
                "identities": {
                    emp_id: identity.model_dump() for emp_id, identity in self.identities.items()
                },
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Failed to save state to {self.storage_path}: {e}")

    def _load_state(self):
        """Load state from persistent storage."""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, encoding="utf-8") as f:
                state_data = json.load(f)

            identities_data = state_data.get("identities", {})

            for emp_id, identity_data in identities_data.items():
                # Convert back to UserIdentity
                # Handle datetime deserialization
                if "created_at" in identity_data:
                    identity_data["created_at"] = datetime.fromisoformat(
                        identity_data["created_at"]
                    )
                if "updated_at" in identity_data:
                    identity_data["updated_at"] = datetime.fromisoformat(
                        identity_data["updated_at"]
                    )

                # Convert entitlements back to objects
                entitlements = []
                for ent_data in identity_data.get("entitlements", []):
                    if "granted_at" in ent_data:
                        ent_data["granted_at"] = datetime.fromisoformat(ent_data["granted_at"])
                    if "expires_at" in ent_data and ent_data["expires_at"]:
                        ent_data["expires_at"] = datetime.fromisoformat(ent_data["expires_at"])
                    entitlements.append(AccessEntitlement(**ent_data))

                identity_data["entitlements"] = entitlements

                # Convert last_hr_event if present
                if identity_data.get("last_hr_event"):
                    identity_data["last_hr_event"] = HREvent(**identity_data["last_hr_event"])

                self.identities[emp_id] = UserIdentity(**identity_data)

            logger.info(
                f"Loaded state for {len(self.identities)} identities from {self.storage_path}"
            )

        except Exception as e:
            logger.error(f"Failed to load state from {self.storage_path}: {e}")
            # Continue with empty state if load fails
