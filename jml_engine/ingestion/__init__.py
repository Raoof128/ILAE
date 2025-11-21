"""
HR Event Ingestion Package.

This package provides components for ingesting and parsing HR events
from various sources including Workday, BambooHR, CSV files, and JSON webhooks.
"""

from .formats.bamboo import BambooHRParser
from .formats.base import HRFormatParser
from .formats.csv_loader import CSVParser
from .formats.workday import WorkdayParser
from .hr_event_listener import HREventListener

__all__ = [
    "HREventListener",
    "HRFormatParser",
    "WorkdayParser",
    "BambooHRParser",
    "CSVParser",
]
