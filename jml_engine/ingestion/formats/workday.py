"""
Workday HR event format parser.

Parses Workday JSON webhook payloads and converts them to normalized HREvent objects.
Workday typically sends events in JSON format with specific field mappings.
"""

import logging
from typing import Any, Dict, List, Optional

from ...models import HREvent
from .base import HRFormatParser

logger = logging.getLogger(__name__)


class WorkdayParser(HRFormatParser):
    """Parser for Workday HR event webhooks."""

    def can_parse(self, data: Any) -> bool:
        """Check if data appears to be from Workday."""
        if not isinstance(data, dict):
            return False

        # Check for Workday-specific fields
        workday_indicators = [
            "Worker_ID",
            "Employee_ID",
            "Business_Process_Type",
            "Event_Type",
            "Worker",
            "Employment_Data",
        ]

        return any(indicator in data for indicator in workday_indicators)

    def parse(self, data: Dict[str, Any]) -> List[HREvent]:
        """
        Parse Workday JSON payload into HREvent objects.

        Workday sends events like:
        {
            "Worker_ID": "12345",
            "Employee_ID": "EMP001",
            "Business_Process_Type": "Employee_Hire",
            "Event_Type": "Hire",
            "Worker": {
                "Legal_Name": "John Smith",
                "Email": "john.smith@company.com"
            },
            "Employment_Data": {
                "Position": {
                    "Job_Title": "Software Engineer",
                    "Department": "Engineering"
                },
                "Start_Date": "2024-01-15",
                "Manager": "jane.manager@company.com"
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
            logger.error(f"Failed to parse Workday data: {e}")
            raise

        return events

    def _parse_single_event(self, data: Dict[str, Any]) -> Optional[HREvent]:
        """Parse a single Workday event."""
        try:
            # Extract core employee information
            employee_id = (
                data.get("Employee_ID") or
                data.get("Worker_ID") or
                str(data.get("id", ""))
            )

            if not employee_id:
                logger.warning("No employee ID found in Workday event")
                return None

            # Extract worker information
            worker_data = data.get("Worker", {})
            legal_name = worker_data.get("Legal_Name", "")
            email = worker_data.get("Email", "")

            # Extract employment data
            employment_data = data.get("Employment_Data", {})
            position_data = employment_data.get("Position", {})

            # Determine event type
            event_type_raw = (
                data.get("Event_Type") or
                data.get("Business_Process_Type") or
                "Hire"
            )
            event_type = self._normalize_event_type(event_type_raw)

            # Extract additional fields
            department = position_data.get("Department", "")
            title = position_data.get("Job_Title", "")
            manager_email = employment_data.get("Manager")
            start_date_str = employment_data.get("Start_Date")
            end_date_str = employment_data.get("End_Date")
            location = employment_data.get("Location")

            # Parse dates
            start_date = None
            if start_date_str:
                start_date = self._parse_date(start_date_str)

            end_date = None
            if end_date_str:
                end_date = self._parse_date(end_date_str)

            # Contract type (Workday specific)
            contract_type = employment_data.get("Employment_Type", "PERMANENT")

            return HREvent(
                event=event_type,
                employee_id=employee_id,
                name=legal_name,
                email=email,
                department=department,
                title=title,
                manager_email=manager_email,
                start_date=start_date,
                end_date=end_date,
                location=location,
                contract_type=contract_type,
                source_system="Workday",
                raw_data=data
            )

        except Exception as e:
            logger.error(f"Failed to parse single Workday event: {e}")
            return None
