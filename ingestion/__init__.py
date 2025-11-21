"""
HR Event Ingestion Package.

This package provides components for ingesting and parsing HR events
from various sources including Workday, BambooHR, CSV files, and JSON webhooks.
"""

from .hr_event_listener import HREventListener
from .formats.base import HRFormatParser
from .formats.workday import WorkdayParser
from .formats.bamboo import BambooHRParser
from .formats.csv_loader import CSVParser

__all__ = [
    "HREventListener",
    "HRFormatParser",
    "WorkdayParser",
    "BambooHRParser",
    "CSVParser",
]
