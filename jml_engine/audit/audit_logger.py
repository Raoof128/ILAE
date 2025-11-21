"""
Audit Logging Module.

This module provides functionality for secure logging of all IAM actions
and compliance events.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import AuditRecord

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Secure logger for audit events.

    Persists audit records to a secure location (local file system for now,
    could be S3/Splunk in production) and ensures immutability.
    """

    def __init__(self, audit_dir: str = "audit_logs"):
        """
        Initialize the audit logger.

        Args:
            audit_dir: Directory to store audit logs
        """
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def log_event(self, record: AuditRecord) -> str:
        """
        Log an audit event.

        Args:
            record: The audit record to log

        Returns:
            The record ID
        """
        try:
            # Create daily log file
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_file = self.audit_dir / f"audit_{date_str}.jsonl"

            # Append to log file
            with open(log_file, "a", encoding="utf-8") as f:
                # Convert to dict and handle datetime serialization
                data = record.model_dump(mode="json")
                f.write(json.dumps(data) + "\n")

            logger.info(f"Logged audit event {record.id} for {record.employee_id}")
            return record.id

        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            # In a real system, we might raise here or write to a fallback
            raise

    def get_events(
        self,
        employee_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditRecord]:
        """
        Retrieve audit events with filtering.

        Args:
            employee_id: Filter by employee ID
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of records to return

        Returns:
            List of matching AuditRecords
        """
        results = []

        # Iterate through log files (most recent first)
        log_files = sorted(self.audit_dir.glob("audit_*.jsonl"), reverse=True)

        for log_file in log_files:
            if len(results) >= limit:
                break

            try:
                with open(log_file, encoding="utf-8") as f:
                    # Read lines in reverse order for most recent first
                    lines = f.readlines()
                    for line in reversed(lines):
                        if len(results) >= limit:
                            break

                        try:
                            data = json.loads(line)
                            record = AuditRecord(**data)

                            # Apply filters
                            if employee_id and record.employee_id != employee_id:
                                continue

                            if start_date and record.timestamp < start_date:
                                continue

                            if end_date and record.timestamp > end_date:
                                continue

                            results.append(record)

                        except Exception as e:
                            logger.warning(f"Failed to parse audit record: {e}")
                            continue

            except Exception as e:
                logger.error(f"Failed to read log file {log_file}: {e}")
                continue

        return results

    def generate_compliance_report(
        self, start_date: datetime, end_date: datetime, standards: List[str]
    ) -> Dict[str, Any]:
        """
        Generate a compliance report for a given period.

        Args:
            start_date: Start of the reporting period
            end_date: End of the reporting period
            standards: List of compliance standards (e.g., ISO_27001)

        Returns:
            Dictionary containing the compliance report
        """
        events = self.get_events(start_date=start_date, end_date=end_date, limit=10000)

        total_events = len(events)
        successful = len([e for e in events if e.success])
        failed = total_events - successful

        report = {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "standards": standards,
            "summary": {
                "total_events": total_events,
                "successful_operations": successful,
                "failed_operations": failed,
                "compliance_score": (successful / total_events * 100) if total_events > 0 else 100,
            },
            "events": [e.model_dump(mode="json") for e in events],
            "recommendations": [],
        }

        if failed > 0:
            report["recommendations"].append("Investigate failed IAM operations")

        return report
