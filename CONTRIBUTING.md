# Contributing to JML Engine

Thank you for your interest in contributing to the JML Engine! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

This project adheres to a code of conduct that all contributors are expected to follow. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Git
- Docker (optional, for containerized development)

### Setup

1. **Fork and Clone the Repository**
   ```bash
   git clone https://github.com/your-username/jml-engine.git
   cd jml-engine
   ```

2. **Create a Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"  # Install development dependencies
   ```

4. **Run Tests**
   ```bash
   pytest tests/
   ```

5. **Start Development Environment**
   ```bash
   # API Server
   python -m jml_engine.api.server

   # Dashboard (in another terminal)
   streamlit run jml_engine/dashboard/app.py
   ```

## Development Workflow

### Branching Strategy

- `main`: Production-ready code
- `develop`: Integration branch for features
- `feature/*`: Feature branches
- `bugfix/*`: Bug fix branches
- `hotfix/*`: Critical fixes for production

### Commit Messages

Follow conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New features
- `fix`: Bug fixes
- `docs`: Documentation changes
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Test additions/modifications
- `chore`: Maintenance tasks

Examples:
```
feat(auth): add OAuth2 support for API authentication
fix(connector): resolve AWS IAM policy attachment race condition
docs(api): update endpoint documentation for v2.0
```

## Coding Standards

### Python Standards

- Follow [PEP 8](https://pep8.org/) style guidelines
- Use [Black](https://black.readthedocs.io/) for code formatting
- Include type hints for all function parameters and return values
- Write comprehensive docstrings following Google style

### Code Quality

- **Type Hints**: All functions must include type annotations
- **Docstrings**: Every module, class, and function must have docstrings
- **Error Handling**: Implement proper exception handling and logging
- **Security**: Never hardcode secrets; use environment variables
- **Performance**: Consider performance implications of changes

### File Structure

```
jml_engine/
├── api/           # API server and endpoints
├── audit/         # Audit logging and compliance
├── cli/           # Command-line interface
├── connectors/    # Platform integrations
├── dashboard/     # Web dashboard
├── engine/        # Policy and state management
├── ingestion/     # HR event processing
├── models.py      # Core data models
├── workflows/     # JML workflow engines
└── tests/         # Test suite
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=jml_engine --cov-report=html

# Run specific tests
pytest tests/test_joiner.py

# Run tests in verbose mode
pytest -v
```

### Writing Tests

- Use `pytest` framework
- Place tests in `tests/` directory
- Name test files `test_*.py`
- Use descriptive test function names
- Include docstrings for test functions
- Mock external dependencies appropriately

Example:
```python
def test_joiner_workflow_success():
    """Test successful execution of joiner workflow."""
    # Test implementation
    pass
```

### Test Coverage

Maintain minimum 80% code coverage. Coverage reports are generated automatically in CI/CD.

## Documentation

### Code Documentation

- Use Google-style docstrings
- Document all parameters, return values, and exceptions
- Include usage examples where appropriate

Example:
```python
def create_user(self, user: UserIdentity) -> ConnectorResult:
    """Create a new user account.

    Args:
        user: User identity information containing name, email, etc.

    Returns:
        ConnectorResult with success status and user details.

    Raises:
        ConnectorError: If user creation fails due to API errors.
    """
```

### API Documentation

- API endpoints are automatically documented via FastAPI/OpenAPI
- Update docstrings for any new endpoints
- Include examples in API documentation

### User Documentation

- Keep README.md up to date
- Update usage examples and configuration guides
- Document breaking changes in release notes

## Submitting Changes

### Pull Request Process

1. **Create a Feature Branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```

2. **Make Changes**
   - Write code following the standards above
   - Add/update tests
   - Update documentation
   - Ensure all tests pass

3. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: add amazing feature"
   ```

4. **Push and Create PR**
   ```bash
   git push origin feature/amazing-feature
   # Create pull request on GitHub
   ```

5. **Code Review**
   - Address review comments
   - Ensure CI/CD passes
   - Get approval from maintainers

### PR Requirements

- [ ] Tests pass
- [ ] Code coverage maintained
- [ ] Documentation updated
- [ ] No linting errors
- [ ] Commit messages follow conventions
- [ ] Changes backward compatible (if applicable)

## Reporting Issues

### Bug Reports

When reporting bugs, please include:

- **Description**: Clear description of the issue
- **Steps to Reproduce**: Step-by-step instructions
- **Expected Behavior**: What should happen
- **Actual Behavior**: What actually happens
- **Environment**: Python version, OS, dependencies
- **Logs**: Relevant log output
- **Screenshots**: If applicable

### Feature Requests

For feature requests, please include:

- **Description**: What feature you'd like to see
- **Use Case**: Why this feature is needed
- **Implementation Ideas**: Any thoughts on implementation
- **Alternatives**: Considered alternatives

### Security Issues

For security-related issues:

- **DO NOT** create public GitHub issues
- Email security@jml-engine.dev instead
- Include detailed information about the vulnerability

## Recognition

Contributors will be recognized in the project README and release notes. Significant contributions may result in co-authorship on related publications or conference presentations.

Thank you for contributing to the JML Engine! 🚀
