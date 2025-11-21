"""
Base classes for HR event format parsers.

This module provides the foundation for parsing HR events from various
sources like Workday, BambooHR, CSV files, and JSON webhooks.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, List

from ...models import HREvent, LifecycleEvent

logger = logging.getLogger(__name__)


class HRFormatParser(ABC):
    """Abstract base class for HR event format parsers."""

    @abstractmethod
    def parse(self, data: Any) -> List[HREvent]:
        """
        Parse raw data into normalized HREvent objects.

        Args:
            data: Raw data in the format expected by this parser

        Returns:
            List of normalized HREvent objects
        """
        pass

    @abstractmethod
    def can_parse(self, data: Any) -> bool:
        """
        Check if this parser can handle the given data format.

        Args:
            data: Raw data to check

        Returns:
            True if this parser can handle the data, False otherwise
        """
        pass

    def _normalize_event_type(self, raw_event_type: str) -> LifecycleEvent:
        """
        Normalize various event type strings to LifecycleEvent enum values.

        Args:
            raw_event_type: Raw event type string from source system

        Returns:
            Normalized LifecycleEvent enum value
        """
        event_mapping = {
            # Workday style
            "Hire": LifecycleEvent.NEW_STARTER,
            "New Hire": LifecycleEvent.NEW_STARTER,
            "Employee Hire": LifecycleEvent.NEW_STARTER,
            "Start": LifecycleEvent.NEW_STARTER,

            # Termination events
            "Terminate": LifecycleEvent.TERMINATION,
            "Termination": LifecycleEvent.TERMINATION,
            "Employee Termination": LifecycleEvent.TERMINATION,
            "End Employment": LifecycleEvent.TERMINATION,

            # Transfer/Promotion
            "Transfer": LifecycleEvent.DEPARTMENT_CHANGE,
            "Department Change": LifecycleEvent.DEPARTMENT_CHANGE,
            "Promotion": LifecycleEvent.ROLE_CHANGE,
            "Job Change": LifecycleEvent.ROLE_CHANGE,
            "Role Change": LifecycleEvent.ROLE_CHANGE,

            # Leave events
            "Leave of Absence": LifecycleEvent.LEAVE_OF_ABSENCE,
            "LOA": LifecycleEvent.LEAVE_OF_ABSENCE,
            "Return from Leave": LifecycleEvent.RETURN_FROM_LEAVE,

            # Contractor events
            "Contractor Offboarding": LifecycleEvent.CONTRACTOR_OFFBOARDING,
            "Contract End": LifecycleEvent.CONTRACTOR_OFFBOARDING,
        }

        # Case-insensitive matching
        normalized = event_mapping.get(raw_event_type, raw_event_type.upper().replace(" ", "_"))
        try:
            return LifecycleEvent(normalized)
        except ValueError:
            logger.warning(f"Unknown event type: {raw_event_type}, defaulting to NEW_STARTER")
            return LifecycleEvent.NEW_STARTER

    def _parse_date(self, date_str: str) -> datetime:
        """
        Parse date string into datetime object.

        Args:
            date_str: Date string in various formats

        Returns:
            Parsed datetime object
        """
        if not date_str:
            return datetime.now(timezone.utc)

        # Try common date formats
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}, using current time")
        return datetime.now(timezone.utc)
