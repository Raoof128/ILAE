"""
Evidence Store Module.

This module manages the storage and retrieval of compliance evidence files.
"""

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EvidenceStore:
    """
    Secure storage for compliance evidence.
    
    Manages files like screenshots, ticket exports, and approval emails
    that serve as evidence for audit compliance.
    """

    def __init__(self, storage_dir: str = "evidence"):
        """
        Initialize the evidence store.

        Args:
            storage_dir: Directory to store evidence files
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def store_evidence(self, data: Any, employee_id: str = "unknown", audit_id: str = "unknown") -> str:
        """
        Store evidence (file or data).

        Args:
            data: File path (str) or data dict/bytes
            employee_id: Employee ID associated with the evidence
            audit_id: Audit record ID associated with the evidence

        Returns:
            ID or path of the stored evidence
        """
        try:
            # Create structured path: YYYY/MM/employee_id/
            date_path = datetime.now(timezone.utc).strftime("%Y/%m")
            target_dir = self.storage_dir / date_path / employee_id
            target_dir.mkdir(parents=True, exist_ok=True)
            
            if audit_id == "unknown":
                import uuid
                audit_id = str(uuid.uuid4())

            if isinstance(data, str) and Path(data).exists():
                # It's a file path
                source = Path(data)
                extension = source.suffix
                filename = f"{audit_id}{extension}"
                target_path = target_dir / filename
                shutil.copy2(source, target_path)
                logger.info(f"Stored evidence file for {employee_id} at {target_path}")
                return str(target_path)
            
            else:
                # It's raw data, save as JSON
                import json
                filename = f"{audit_id}.json"
                target_path = target_dir / filename
                
                with open(target_path, 'w', encoding='utf-8') as f:
                    if isinstance(data, dict) or isinstance(data, list):
                        json.dump(data, f, indent=2, default=str)
                    else:
                        f.write(str(data))
                        
                logger.info(f"Stored evidence data for {employee_id} at {target_path}")
                return str(target_path)

        except Exception as e:
            logger.error(f"Failed to store evidence: {e}")
            raise

    def retrieve_evidence(self, evidence_id: str) -> Optional[Any]:
        """
        Retrieve stored evidence by ID or path.
        
        Args:
            evidence_id: Path or ID of the evidence
            
        Returns:
            The evidence data or path
        """
        # If it's a full path
        path = Path(evidence_id)
        if path.exists():
            if path.suffix == '.json':
                import json
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return path
            
        # If it's just an ID, we'd need a lookup mechanism (database).
        # For this simple implementation, we assume evidence_id IS the path.
        return None

    def get_evidence_path(self, stored_path: str) -> Optional[Path]:
        """
        Get the absolute path to a stored evidence file.

        Args:
            stored_path: Path returned by store_evidence

        Returns:
            Absolute path if exists, None otherwise
        """
        path = Path(stored_path)
        if path.exists():
            return path.absolute()
        return None
