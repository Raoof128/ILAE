"""
CSV format parser for HR event data.

Parses CSV files exported from HR systems and converts them to normalized HREvent objects.
Supports various CSV formats with flexible column mapping.
"""

import csv
import io
import logging
from typing import Any, Dict, List, Optional

from ...models import HREvent
from .base import HRFormatParser

logger = logging.getLogger(__name__)


class CSVParser(HRFormatParser):
    """Parser for CSV HR event files."""

    # Default column mappings - can be customized
    DEFAULT_MAPPINGS = {
        "employee_id": ["Employee ID", "Employee_ID", "Emp ID", "ID", "employee_id"],
        "name": ["Full Name", "Name", "Employee Name", "name"],
        "email": ["Email", "Email Address", "Work Email", "email"],
        "department": ["Department", "Dept", "Business Unit", "department"],
        "title": ["Job Title", "Title", "Position", "Role", "title"],
        "event_type": ["Event Type", "Event", "Action", "Type", "event"],
        "start_date": ["Start Date", "Hire Date", "Join Date", "start_date"],
        "end_date": ["End Date", "Termination Date", "Leave Date", "end_date"],
        "manager_email": ["Manager Email", "Manager", "Supervisor Email", "manager_email"],
        "location": ["Location", "Office", "Site", "location"],
        "contract_type": ["Contract Type", "Employment Type", "Type", "contract_type"],
        "previous_department": ["Previous Department", "Old Department", "previous_department"],
        "previous_title": ["Previous Title", "Old Title", "previous_title"],
    }

    def __init__(self, column_mappings: Optional[Dict[str, List[str]]] = None):
        """
        Initialize CSV parser with optional custom column mappings.

        Args:
            column_mappings: Custom column name mappings. Keys are field names,
                           values are lists of possible column names in CSV.
        """
        self.column_mappings = column_mappings or self.DEFAULT_MAPPINGS

    def can_parse(self, data: Any) -> bool:
        """Check if data is CSV content."""
        if isinstance(data, str):
            # Check if it looks like CSV (contains commas and newlines)
            return ',' in data and '\n' in data
        elif hasattr(data, 'read'):  # File-like object
            return True
        return False

    def parse(self, data: Any) -> List[HREvent]:
        """
        Parse CSV data into HREvent objects.

        Args:
            data: CSV string or file-like object

        Returns:
            List of HREvent objects
        """
        events = []

        try:
            # Handle different input types
            if isinstance(data, str):
                csv_reader = csv.DictReader(io.StringIO(data))
            elif hasattr(data, 'read'):
                csv_reader = csv.DictReader(data)
            else:
                raise ValueError("Unsupported data type for CSV parsing")

            for row in csv_reader:
                event = self._parse_row(row)
                if event:
                    events.append(event)

        except Exception as e:
            logger.error(f"Failed to parse CSV data: {e}")
            raise

        return events

    def _parse_row(self, row: Dict[str, str]) -> Optional[HREvent]:
        """Parse a single CSV row into an HREvent."""
        try:
            # Map CSV columns to our field names
            mapped_data = self._map_columns(row)

            # Required fields
            employee_id = mapped_data.get("employee_id", "").strip()
            if not employee_id:
                logger.warning(f"No employee ID found in row: {row}")
                return None

            name = mapped_data.get("name", "").strip()
            email = mapped_data.get("email", "").strip()

            if not name or not email:
                logger.warning(f"Missing required fields (name/email) in row: {row}")
                return None

            # Determine event type
            event_type_raw = mapped_data.get("event_type", "NEW_STARTER")
            event_type = self._normalize_event_type(event_type_raw)

            # Optional fields
            department = mapped_data.get("department", "")
            title = mapped_data.get("title", "")
            manager_email = mapped_data.get("manager_email", "")
            location = mapped_data.get("location", "")
            contract_type = mapped_data.get("contract_type", "PERMANENT")

            # Parse dates
            start_date = None
            start_date_str = mapped_data.get("start_date", "")
            if start_date_str:
                start_date = self._parse_date(start_date_str)

            end_date = None
            end_date_str = mapped_data.get("end_date", "")
            if end_date_str:
                end_date = self._parse_date(end_date_str)

            # Mover-specific fields
            previous_department = mapped_data.get("previous_department", "")
            previous_title = mapped_data.get("previous_title", "")

            return HREvent(
                event=event_type,
                employee_id=employee_id,
                name=name,
                email=email,
                department=department,
                title=title,
                manager_email=manager_email if manager_email else None,
                start_date=start_date,
                end_date=end_date,
                location=location if location else None,
                contract_type=contract_type,
                previous_department=previous_department if previous_department else None,
                previous_title=previous_title if previous_title else None,
                source_system="CSV",
                raw_data=row
            )

        except Exception as e:
            logger.error(f"Failed to parse CSV row: {e}, row: {row}")
            return None

    def _map_columns(self, row: Dict[str, str]) -> Dict[str, str]:
        """
        Map CSV column names to our internal field names.

        Args:
            row: CSV row as dict with column names as keys

        Returns:
            Dict with our internal field names as keys
        """
        mapped = {}

        # Normalize column names (case-insensitive)
        normalized_row = {k.lower().strip(): v for k, v in row.items()}

        for field_name, possible_columns in self.column_mappings.items():
            for col_name in possible_columns:
                normalized_col = col_name.lower().strip()
                if normalized_col in normalized_row:
                    mapped[field_name] = normalized_row[normalized_col]
                    break

        return mapped
