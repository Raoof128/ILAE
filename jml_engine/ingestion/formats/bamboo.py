"""
BambooHR format parser for HR events.

Parses BambooHR webhook payloads and API responses into normalized HREvent objects.
BambooHR typically sends events as JSON with employee field mappings.
"""

import logging
from typing import Any, Dict, List, Optional

from ...models import HREvent, LifecycleEvent
from .base import HRFormatParser

logger = logging.getLogger(__name__)


class BambooHRParser(HRFormatParser):
    """Parser for BambooHR HR event webhooks."""

    def can_parse(self, data: Any) -> bool:
        """Check if data appears to be from BambooHR."""
        if not isinstance(data, dict):
            return False

        # Check for BambooHR-specific fields
        bamboo_indicators = [
            "employeeId",
            "action",
            "changedFields",
            "employee",
            "webhook",
        ]

        return any(indicator in data for indicator in bamboo_indicators)

    def parse(self, data: Dict[str, Any]) -> List[HREvent]:
        """
        Parse BambooHR JSON payload into HREvent objects.

        BambooHR sends events like:
        {
            "employeeId": "12345",
            "action": "hired",
            "changedFields": ["status", "hireDate"],
            "employee": {
                "id": "12345",
                "firstName": "John",
                "lastName": "Smith",
                "workEmail": "john.smith@company.com",
                "department": "Engineering",
                "jobTitle": "Software Engineer",
                "hireDate": "2024-01-15",
                "terminationDate": null,
                "location": "New York",
                "supervisorEmail": "jane.manager@company.com"
            }
        }
        """
        events = []

        try:
            # Handle both single events and arrays
            if isinstance(data, list):
                for event_data in data:
                    event = self._parse_single_event(event_data)
                    if event:
                        events.append(event)
            else:
                event = self._parse_single_event(data)
                if event:
                    events.append(event)

        except Exception as e:
            logger.error(f"Failed to parse BambooHR data: {e}")
            raise

        return events

    def _parse_single_event(self, data: Dict[str, Any]) -> Optional[HREvent]:
        """Parse a single BambooHR event."""
        try:
            # Extract core employee information
            employee_id = str(data.get("employeeId", ""))

            if not employee_id:
                logger.warning("No employee ID found in BambooHR event")
                return None

            # Extract employee details
            employee_data = data.get("employee", {})

            first_name = employee_data.get("firstName", "")
            last_name = employee_data.get("lastName", "")
            full_name = f"{first_name} {last_name}".strip()

            email = employee_data.get("workEmail", "")

            if not full_name or not email:
                logger.warning("Missing required fields (name/email) in BambooHR event")
                return None

            # Determine event type from action
            action = data.get("action", "").lower()
            event_type = self._normalize_bamboo_action(action)

            # Extract additional fields
            department = employee_data.get("department", "")
            title = employee_data.get("jobTitle", "")
            manager_email = employee_data.get("supervisorEmail")
            location = employee_data.get("location")

            # Parse dates
            start_date = None
            hire_date_str = employee_data.get("hireDate")
            if hire_date_str:
                start_date = self._parse_date(hire_date_str)

            end_date = None
            term_date_str = employee_data.get("terminationDate")
            if term_date_str:
                end_date = self._parse_date(term_date_str)

            # Contract type (inferred from BambooHR data)
            contract_type = "PERMANENT"  # Default
            if employee_data.get("employeeType") == "Contractor":
                contract_type = "CONTRACTOR"

            # Handle mover events (from changedFields)
            previous_department = None
            previous_title = None

            changed_fields = data.get("changedFields", [])
            if "department" in changed_fields and event_type == LifecycleEvent.DEPARTMENT_CHANGE:
                # For mover events, we might need additional context
                # This is a simplified version - in practice, you'd want the previous values
                pass

            return HREvent(
                event=event_type,
                employee_id=employee_id,
                name=full_name,
                email=email,
                department=department,
                title=title,
                manager_email=manager_email,
                start_date=start_date,
                end_date=end_date,
                location=location,
                contract_type=contract_type,
                previous_department=previous_department,
                previous_title=previous_title,
                source_system="BambooHR",
                raw_data=data
            )

        except Exception as e:
            logger.error(f"Failed to parse single BambooHR event: {e}")
            return None

    def _normalize_bamboo_action(self, action: str) -> LifecycleEvent:
        """
        Convert BambooHR action strings to LifecycleEvent enum values.

        Args:
            action: BambooHR action string

        Returns:
            Normalized LifecycleEvent
        """
        action_mapping = {
            "hired": LifecycleEvent.NEW_STARTER,
            "hire": LifecycleEvent.NEW_STARTER,
            "rehired": LifecycleEvent.NEW_STARTER,
            "terminated": LifecycleEvent.TERMINATION,
            "termination": LifecycleEvent.TERMINATION,
            "updated": LifecycleEvent.ROLE_CHANGE,  # Could be various changes
            "changed": LifecycleEvent.ROLE_CHANGE,
            "transfer": LifecycleEvent.DEPARTMENT_CHANGE,
            "promotion": LifecycleEvent.ROLE_CHANGE,
        }

        return action_mapping.get(action, LifecycleEvent.NEW_STARTER)
