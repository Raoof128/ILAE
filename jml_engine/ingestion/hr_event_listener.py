"""
HR Event Listener for the JML Engine.

This module provides the main interface for ingesting HR events from various sources
and normalizing them into a standard format for processing by the workflow engines.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..models import HREvent
from .formats.bamboo import BambooHRParser
from .formats.base import HRFormatParser
from .formats.csv_loader import CSVParser
from .formats.workday import WorkdayParser

logger = logging.getLogger(__name__)


class HREventListener:
    """
    Main HR event ingestion coordinator.

    Automatically detects the format of incoming HR data and parses it
    into normalized HREvent objects using the appropriate parser.
    """

    def __init__(self):
        """Initialize the HR event listener with all available parsers."""
        self.parsers: List[HRFormatParser] = [
            WorkdayParser(),
            BambooHRParser(),
            CSVParser(),
        ]

        logger.info(f"Initialized HR Event Listener with {len(self.parsers)} parsers")

    def ingest_event(self, data: Union[str, Dict[str, Any], Path]) -> List[HREvent]:
        """
        Ingest and parse HR event data from various sources.

        Args:
            data: HR event data in various formats:
                  - Dict: JSON webhook payload
                  - str: CSV content or JSON string
                  - Path: Path to CSV file

        Returns:
            List of normalized HREvent objects

        Raises:
            ValueError: If no suitable parser is found for the data
        """
        logger.info(f"Ingesting HR event data of type: {type(data)}")

        # Handle file paths
        if isinstance(data, Path):
            if data.suffix.lower() == ".csv":
                with open(data, encoding="utf-8") as f:
                    content = f.read()
                return self._parse_with_auto_detection(content)
            else:
                raise ValueError(f"Unsupported file type: {data.suffix}")

        # Handle string data (CSV or JSON)
        if isinstance(data, str):
            return self._parse_with_auto_detection(data)

        # Handle dict data (JSON)
        if isinstance(data, dict):
            return self._parse_with_auto_detection(data)

        raise ValueError(f"Unsupported data type: {type(data)}")

    def ingest_csv_file(
        self, file_path: Union[str, Path], column_mappings: Optional[Dict[str, List[str]]] = None
    ) -> List[HREvent]:
        """
        Specifically ingest HR events from a CSV file.

        Args:
            file_path: Path to the CSV file
            column_mappings: Optional custom column mappings

        Returns:
            List of HREvent objects
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {file_path}")

        parser = CSVParser(column_mappings)
        with open(path, encoding="utf-8") as f:
            return parser.parse(f)

    def ingest_json_webhook(self, payload: Dict[str, Any]) -> List[HREvent]:
        """
        Ingest HR event from a JSON webhook payload.

        Args:
            payload: JSON webhook payload

        Returns:
            List of HREvent objects
        """
        return self._parse_with_auto_detection(payload)

    def _parse_with_auto_detection(self, data: Any) -> List[HREvent]:
        """
        Automatically detect the format and parse the data.

        Args:
            data: Raw data to parse

        Returns:
            List of HREvent objects

        Raises:
            ValueError: If no parser can handle the data
        """
        for parser in self.parsers:
            try:
                if parser.can_parse(data):
                    logger.info(f"Using parser: {parser.__class__.__name__}")
                    events = parser.parse(data)

                    if events:
                        logger.info(f"Successfully parsed {len(events)} HR events")
                        return events
                    else:
                        logger.warning(f"Parser {parser.__class__.__name__} returned no events")

            except Exception as e:
                logger.warning(f"Parser {parser.__class__.__name__} failed: {e}")
                continue

        # If no parser worked, try a fallback approach
        logger.warning("No parser could handle the data, attempting fallback parsing")
        return self._fallback_parse(data)

    def _fallback_parse(self, data: Any) -> List[HREvent]:
        """
        Fallback parsing for unrecognized formats.

        This is a basic implementation that tries to extract common fields.
        In production, you might want to make this more sophisticated or
        require explicit format specification.

        Args:
            data: Raw data to parse

        Returns:
            List of HREvent objects (may be empty if parsing fails)
        """
        events = []

        try:
            if isinstance(data, dict):
                # Try to extract fields with common patterns
                event = self._extract_common_fields(data)
                if event:
                    events.append(event)
            elif isinstance(data, str):
                # Try parsing as JSON first
                import json

                try:
                    json_data = json.loads(data)
                    events.extend(self._fallback_parse(json_data))
                except json.JSONDecodeError:
                    # Try as CSV
                    csv_parser = CSVParser()
                    if csv_parser.can_parse(data):
                        events.extend(csv_parser.parse(data))

        except Exception as e:
            logger.error(f"Fallback parsing failed: {e}")

        if not events:
            logger.error("Could not parse HR event data with any available method")
            raise ValueError("Unable to parse HR event data - no suitable parser found")

        return events

    def _extract_common_fields(self, data: Dict[str, Any]) -> Optional[HREvent]:
        """
        Extract common HR fields from a dictionary using various possible keys.

        Args:
            data: Dictionary containing potential HR fields

        Returns:
            HREvent if required fields are found, None otherwise
        """
        # Common field patterns
        employee_id = (
            data.get("employee_id")
            or data.get("id")
            or data.get("employeeId")
            or data.get("Employee_ID")
        )

        name = (
            data.get("name")
            or data.get("full_name")
            or data.get("employee_name")
            or data.get("Name")
        )

        email = data.get("email") or data.get("work_email") or data.get("Email")

        if not all([employee_id, name, email]):
            return None

        # Optional fields with fallbacks
        department = data.get("department") or data.get("dept") or ""
        title = data.get("title") or data.get("job_title") or data.get("position") or ""
        event_type = data.get("event") or data.get("event_type") or "NEW_STARTER"

        try:
            # Use the first available parser for normalization logic
            parser = self.parsers[0]
            event_enum = parser._normalize_event_type(event_type)

            return HREvent(
                event=event_enum,
                employee_id=str(employee_id),
                name=str(name),
                email=str(email),
                department=str(department),
                title=str(title),
                source_system="Unknown",
                raw_data=data,
            )
        except Exception:
            return None

    def get_supported_formats(self) -> List[str]:
        """
        Get list of supported HR data formats.

        Returns:
            List of format names
        """
        return ["Workday JSON", "BambooHR JSON", "CSV files", "Generic JSON (fallback)"]
