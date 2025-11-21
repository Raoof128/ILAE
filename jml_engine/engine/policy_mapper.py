"""
Policy Mapper for the JML Engine.

This module reads the access matrix and role mappings configuration files
and provides methods to resolve user entitlements based on department and title.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Union

import yaml

from ..models import AccessProfile, HREvent

logger = logging.getLogger(__name__)


class PolicyMapper:
    """
    Maps HR roles to technical access entitlements.

    Reads configuration from access_matrix.yaml and role_mappings.yaml
    to determine what access a user should have based on their department and title.
    """

    def __init__(self, config_dir: Optional[Union[str, Path]] = None):
        """
        Initialize the policy mapper.

        Args:
            config_dir: Directory containing access_matrix.yaml and role_mappings.yaml
                       Defaults to the engine directory
        """
        if config_dir is None:
            config_dir = Path(__file__).parent
        else:
            config_dir = Path(config_dir)

        self.config_dir = config_dir
        self.access_matrix = {}
        self.role_mappings = {}

        self._load_configurations()

    def _load_configurations(self):
        """Load access matrix and role mappings from YAML files."""
        try:
            # Load access matrix
            matrix_file = self.config_dir / "access_matrix.yaml"
            if matrix_file.exists():
                with open(matrix_file, encoding='utf-8') as f:
                    self.access_matrix = yaml.safe_load(f)
                logger.info(f"Loaded access matrix from {matrix_file}")
            else:
                logger.warning(f"Access matrix file not found: {matrix_file}")

            # Load role mappings
            mappings_file = self.config_dir / "role_mappings.yaml"
            if mappings_file.exists():
                with open(mappings_file, encoding='utf-8') as f:
                    self.role_mappings = yaml.safe_load(f)
                logger.info(f"Loaded role mappings from {mappings_file}")
            else:
                logger.warning(f"Role mappings file not found: {mappings_file}")

        except Exception as e:
            logger.error(f"Failed to load policy configurations: {e}")
            raise

    def get_access_profile(self, department: str, title: Optional[str] = None,
                          contract_type: str = "PERMANENT") -> AccessProfile:
        """
        Get the access profile for a given department and title combination.

        Args:
            department: User's department
            title: User's job title (optional)
            contract_type: Type of employment contract

        Returns:
            AccessProfile with entitlements for the user
        """
        logger.debug(f"Resolving access profile for dept='{department}', title='{title}', contract='{contract_type}'")

        # Start with default access
        profile = self._get_default_access()

        # Apply department-specific access
        dept_access = self._get_department_access(department)
        if dept_access:
            profile = self._merge_profiles(profile, dept_access)

        # Apply contract type overrides (contractors, interns, etc.)
        contract_override = self._get_contract_override(contract_type)
        if contract_override:
            profile = contract_override  # Complete override for contractors

        # Apply title-specific mappings
        if title:
            title_access = self._get_title_access(title, department)
            if title_access:
                profile = self._merge_profiles(profile, title_access)

        # Set final metadata
        profile.department = department
        profile.title = title
        profile.description = f"Access profile for {title or 'Employee'} in {department}"

        logger.debug(f"Resolved profile with {len(profile.aws_roles)} AWS roles, "
                    f"{len(profile.azure_groups)} Azure groups, "
                    f"{len(profile.github_teams)} GitHub teams")

        return profile

    def get_access_profile_from_event(self, event: HREvent) -> AccessProfile:
        """
        Get access profile directly from an HR event.

        Args:
            event: HREvent containing user information

        Returns:
            AccessProfile for the user
        """
        return self.get_access_profile(
            department=event.department,
            title=event.title,
            contract_type=event.contract_type
        )

    def _get_default_access(self) -> AccessProfile:
        """Get the default access profile for all employees."""
        default_config = self.access_matrix.get("default_access", {})

        return AccessProfile(
            department="Default",
            aws_roles=default_config.get("aws_roles", []),
            azure_groups=default_config.get("azure_groups", []),
            github_teams=default_config.get("github_teams", []),
            google_groups=default_config.get("google_groups", []),
            slack_channels=default_config.get("slack_channels", []),
            description="Default employee access"
        )

    def _get_department_access(self, department: str) -> Optional[AccessProfile]:
        """Get department-specific access configuration."""
        dept_config = self.access_matrix.get("departments", {}).get(department)

        if not dept_config:
            logger.warning(f"No department configuration found for: {department}")
            return None

        return AccessProfile(
            department=department,
            aws_roles=dept_config.get("aws_roles", []),
            azure_groups=dept_config.get("azure_groups", []),
            github_teams=dept_config.get("github_teams", []),
            google_groups=dept_config.get("google_groups", []),
            slack_channels=dept_config.get("slack_channels", []),
            description=dept_config.get("description", f"{department} department access")
        )

    def _get_contract_override(self, contract_type: str) -> Optional[AccessProfile]:
        """Get contract type specific access (contractors, interns, etc.)."""
        if contract_type.upper() == "CONTRACTOR":
            contractor_config = self.access_matrix.get("contractor_access", {})
            return AccessProfile(
                department="Contractor",
                aws_roles=contractor_config.get("aws_roles", []),
                azure_groups=contractor_config.get("azure_groups", []),
                github_teams=contractor_config.get("github_teams", []),
                google_groups=contractor_config.get("google_groups", []),
                slack_channels=contractor_config.get("slack_channels", []),
                description="Contractor access profile"
            )

        # Check for intern access (inferred from title usually, but can be contract type)
        if "INTERN" in contract_type.upper() or "TEMP" in contract_type.upper():
            intern_config = self.access_matrix.get("intern_access", {})
            return AccessProfile(
                department="Intern",
                aws_roles=intern_config.get("aws_roles", []),
                azure_groups=intern_config.get("azure_groups", []),
                github_teams=intern_config.get("github_teams", []),
                google_groups=intern_config.get("google_groups", []),
                slack_channels=intern_config.get("slack_channels", []),
                description="Intern access profile"
            )

        return None

    def _get_title_access(self, title: str, department: str) -> Optional[AccessProfile]:
        """Get title-specific access modifications."""
        # Check title mappings
        title_mappings = self.role_mappings.get("title_mappings", [])

        for mapping in title_mappings:
            pattern = mapping.get("pattern", "")
            if re.search(pattern, title, re.IGNORECASE):
                logger.debug(f"Title '{title}' matched pattern '{pattern}'")

                # Check for access override
                override_key = mapping.get("access_override")
                if override_key:
                    override_config = self.access_matrix.get(override_key)
                    if override_config:
                        return AccessProfile(
                            department=mapping.get("department", department),
                            aws_roles=override_config.get("aws_roles", []),
                            azure_groups=override_config.get("azure_groups", []),
                            github_teams=override_config.get("github_teams", []),
                            google_groups=override_config.get("google_groups", []),
                            slack_channels=override_config.get("slack_channels", []),
                            description=f"Override profile for {title}"
                        )

                # Build additional access
                additional_access = AccessProfile(
                    department=mapping.get("department_override") or department,
                    aws_roles=mapping.get("additional_aws_roles", []),
                    azure_groups=mapping.get("additional_azure_groups", []),
                    github_teams=mapping.get("additional_github_teams", []),
                    google_groups=mapping.get("additional_google_groups", []),
                    slack_channels=mapping.get("additional_slack_channels", []),
                    description=f"Additional access for {title}"
                )

                return additional_access

        # Check custom mappings
        custom_mappings = self.role_mappings.get("custom_mappings", {})
        if title in custom_mappings:
            custom_config = custom_mappings[title]
            return AccessProfile(
                department=custom_config.get("department", department),
                aws_roles=custom_config.get("additional_aws_roles", []),
                azure_groups=custom_config.get("additional_azure_groups", []),
                github_teams=custom_config.get("additional_github_teams", []),
                google_groups=custom_config.get("additional_google_groups", []),
                slack_channels=custom_config.get("additional_slack_channels", []),
                description=f"Custom profile for {title}"
            )

        return None

    def _merge_profiles(self, base: AccessProfile, additional: AccessProfile) -> AccessProfile:
        """
        Merge two access profiles, combining their entitlements.

        Args:
            base: Base access profile
            additional: Additional entitlements to merge

        Returns:
            Combined access profile
        """
        return AccessProfile(
            department=additional.department or base.department,
            title=additional.title or base.title,
            aws_roles=list(set(base.aws_roles + additional.aws_roles)),
            azure_groups=list(set(base.azure_groups + additional.azure_groups)),
            github_teams=list(set(base.github_teams + additional.github_teams)),
            google_groups=list(set(base.google_groups + additional.google_groups)),
            slack_channels=list(set(base.slack_channels + additional.slack_channels)),
            description=f"{base.description} + {additional.description}"
        )

    def get_all_departments(self) -> List[str]:
        """Get list of all configured departments."""
        return list(self.access_matrix.get("departments", {}).keys())

    def get_department_titles(self, department: str) -> List[str]:
        """Get example titles for a department (from mappings)."""
        titles = set()

        # Check title mappings for this department
        for mapping in self.role_mappings.get("title_mappings", []):
            if mapping.get("department") == department:
                pattern = mapping.get("pattern", "")
                # Add the pattern as an example title
                titles.add(pattern)

        # Check custom mappings
        for title, config in self.role_mappings.get("custom_mappings", {}).items():
            if config.get("department") == department:
                titles.add(title)

        return sorted(titles)

    def reload_config(self):
        """Reload configuration files (useful for dynamic updates)."""
        logger.info("Reloading policy configuration")
        self._load_configurations()
