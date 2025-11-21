# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Complete CI/CD pipeline with GitHub Actions
- Pre-commit hooks for code quality enforcement
- Dev container configuration for consistent development
- Comprehensive security scanning and vulnerability assessment
- API documentation generation
- Container security scanning
- Health check and monitoring scripts
- Enhanced testing with integration tests

### Changed
- Updated dependency management with flexible version ranges
- Improved error handling and logging throughout codebase
- Enhanced type hints and documentation
- Modernized development tooling (ruff, etc.)

### Fixed
- Version management consistency across files
- Dependency conflicts in requirements
- Code formatting and linting issues

## [1.0.0] - 2024-01-15

### Added
- Initial release of JML Engine
- Core IAM lifecycle automation for Joiner-Mover-Leaver workflows
- Multi-platform support: AWS IAM, Azure Entra ID, GitHub, Google Workspace, Slack
- REST API with FastAPI
- Web dashboard with Streamlit
- CLI tool (jmlctl) for management
- Comprehensive audit logging with evidence storage
- Policy-based access control with YAML configuration
- Docker containerization
- Mock implementations for testing
- Basic test suite

### Features
- HR event ingestion from multiple sources (Workday, BambooHR, CSV)
- Automated account provisioning and deprovisioning
- Access entitlement management
- Compliance reporting for ISO 27001, SOC2, APRA CPS 234, Essential 8
- Enterprise-grade security and monitoring

### Documentation
- Complete README with architecture diagrams
- API documentation
- Setup and deployment guides
- Security policy and contributing guidelines
