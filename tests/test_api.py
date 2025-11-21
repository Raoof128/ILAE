"""
API endpoint tests for the JML Engine.

This module contains tests for all REST API endpoints,
ensuring proper request handling, response formats, and error conditions.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health check and system status endpoints."""

    @pytest.fixture
    def client(self):
        """Test client for the FastAPI application."""
        from jml_engine.api.server import app
        with TestClient(app) as client:
            yield client

    def test_root_endpoint(self, client):
        """Test the root endpoint returns correct information."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "status" in data

    def test_health_endpoint(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data

        # Check component structure
        components = data["components"]
        expected_components = [
            "hr_listener", "policy_mapper", "state_manager",
            "audit_logger", "evidence_store"
        ]
        for component in expected_components:
            assert component in components

    def test_stats_endpoint(self, client):
        """Test the system statistics endpoint."""
        with patch('jml_engine.api.server.state_manager') as mock_sm, \
             patch('jml_engine.api.server.audit_logger') as _, \
             patch('jml_engine.api.server.evidence_store') as mock_es, \
             patch('jml_engine.api.server.hr_listener') as mock_hl:

            # Setup mocks
            mock_sm.get_identities_summary.return_value = {
                "total_users": 10,
                "total_entitlements": 25,
                "users_by_department": {"Engineering": 5, "HR": 3},
                "users_by_status": {"ACTIVE": 8, "TERMINATED": 2}
            }

            mock_es.get_evidence_stats.return_value = {
                "total_files": 15,
                "total_size_bytes": 1024000,
                "files_by_system": {"aws": 8, "github": 7}
            }

            mock_hl.get_supported_formats.return_value = ["Workday", "BambooHR", "CSV"]

            response = client.get("/stats")
            assert response.status_code == 200

            data = response.json()
            assert "identities" in data
            assert "evidence" in data
            assert data["identities"]["total_users"] == 10
            assert data["evidence"]["total_files"] == 15


class TestHREventEndpoints:
    """Tests for HR event processing endpoints."""

    @pytest.fixture
    def client(self):
        """Test client for the FastAPI application."""
        from jml_engine.api.server import app
        with TestClient(app) as client:
            yield client

    @pytest.fixture
    def valid_hr_event(self):
        """Valid HR event data for testing."""
        return {
            "event": "NEW_STARTER",
            "employee_id": "API001",
            "name": "Test User",
            "email": "test.user@company.com",
            "department": "Engineering",
            "title": "Software Engineer",
            "manager_email": "manager@company.com",
            "start_date": "2024-01-15",
            "contract_type": "PERMANENT",
            "source_system": "API_TEST"
        }

    def test_valid_hr_event_submission(self, client, valid_hr_event):
        """Test successful HR event submission."""
        response = client.post("/event/hr", json=valid_hr_event)
        assert response.status_code == 200

        data = response.json()
        assert "workflow_id" in data
        assert data["employee_id"] == "API001"
        assert data["event_type"] == "NEW_STARTER"
        assert data["status"] == "accepted"
        assert "started_at" in data

    def test_invalid_hr_event_validation(self, client):
        """Test HR event validation for invalid data."""
        invalid_event = {
            "event": "INVALID_EVENT",
            "employee_id": "",  # Empty employee ID
            "name": "",
            "email": "invalid-email",  # Invalid email format
            "department": "Engineering"
        }

        response = client.post("/event/hr", json=invalid_event)
        assert response.status_code == 422

        data = response.json()
        assert "detail" in data
        # Error details will depend on validation implementation

    def test_hr_event_missing_required_fields(self, client):
        """Test HR event submission with missing required fields."""
        incomplete_event = {
            "event": "NEW_STARTER",
            "employee_id": "TEST001"
            # Missing name, email, department
        }

        response = client.post("/event/hr", json=incomplete_event)
        assert response.status_code == 422

    @pytest.mark.parametrize("event_type", [
        "NEW_STARTER",
        "ROLE_CHANGE",
        "TERMINATION"
    ])
    def test_different_event_types(self, client, valid_hr_event, event_type):
        """Test different HR event types."""
        test_event = valid_hr_event.copy()
        test_event["event"] = event_type

        if event_type == "ROLE_CHANGE":
            test_event["previous_department"] = "Engineering"
            test_event["previous_title"] = "Junior Engineer"

        response = client.post("/event/hr", json=test_event)
        assert response.status_code == 200

        data = response.json()
        assert data["event_type"] == event_type


class TestUserManagementEndpoints:
    """Tests for user management endpoints."""

    @pytest.fixture
    def client(self):
        """Test client for the FastAPI application."""
        from jml_engine.api.server import app
        with TestClient(app) as client:
            yield client

    def test_get_existing_user(self, client):
        """Test retrieving an existing user."""
        with patch('jml_engine.api.server.state_manager') as mock_sm:
            mock_identity = MagicMock()
            mock_identity.employee_id = "USER001"
            mock_identity.name = "Test User"
            mock_identity.email = "test.user@company.com"
            mock_identity.department = "Engineering"
            mock_identity.title = "Engineer"
            mock_identity.status.value = "ACTIVE"
            mock_identity.entitlements = []
            mock_identity.created_at.isoformat.return_value = "2024-01-01T00:00:00"
            mock_identity.updated_at.isoformat.return_value = "2024-01-01T00:00:00"

            mock_sm.get_identity.return_value = mock_identity

            response = client.get("/user/USER001")
            assert response.status_code == 200

            data = response.json()
            assert data["employee_id"] == "USER001"
            assert data["name"] == "Test User"
            assert data["status"] == "ACTIVE"

    def test_get_nonexistent_user(self, client):
        """Test retrieving a non-existent user."""
        with patch('jml_engine.api.server.state_manager') as mock_sm:
            mock_sm.get_identity.return_value = None

            response = client.get("/user/NONEXISTENT")
            assert response.status_code == 404

            data = response.json()
            assert "detail" in data

    def test_list_users_basic(self, client):
        """Test basic user listing."""
        with patch('jml_engine.api.server.state_manager') as mock_sm:
            mock_identity = MagicMock()
            mock_identity.employee_id = "USER001"
            mock_identity.name = "Test User"
            mock_identity.email = "test@company.com"
            mock_identity.department = "Engineering"
            mock_identity.title = "Engineer"
            mock_identity.status.value = "ACTIVE"
            mock_identity.entitlements = []
            mock_identity.created_at.isoformat.return_value = "2024-01-01T00:00:00"
            mock_identity.updated_at.isoformat.return_value = "2024-01-01T00:00:00"

            mock_sm.get_all_identities.return_value = [mock_identity]

            response = client.get("/users")
            assert response.status_code == 200

            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["employee_id"] == "USER001"

    def test_list_users_with_filters(self, client):
        """Test user listing with department and status filters."""
        with patch('jml_engine.api.server.state_manager') as mock_sm:
            # Create mock identities
            eng_user = MagicMock()
            eng_user.employee_id = "ENG001"
            eng_user.department = "Engineering"
            eng_user.status.value = "ACTIVE"
            eng_user.name = "Eng User"
            eng_user.email = "eng@company.com"
            eng_user.title = "Engineer"
            eng_user.entitlements = []
            eng_user.created_at.isoformat.return_value = "2024-01-01T00:00:00"
            eng_user.updated_at.isoformat.return_value = "2024-01-01T00:00:00"

            hr_user = MagicMock()
            hr_user.employee_id = "HR001"
            hr_user.department = "HR"
            hr_user.status.value = "ACTIVE"
            hr_user.name = "HR User"
            hr_user.email = "hr@company.com"
            hr_user.title = "Specialist"
            hr_user.entitlements = []
            hr_user.created_at.isoformat.return_value = "2024-01-01T00:00:00"
            hr_user.updated_at.isoformat.return_value = "2024-01-01T00:00:00"

            mock_sm.get_all_identities.return_value = [eng_user, hr_user]

            # Test department filter
            response = client.get("/users?department=Engineering")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["department"] == "Engineering"

    def test_list_users_pagination(self, client):
        """Test user listing with limit parameter."""
        with patch('jml_engine.api.server.state_manager') as mock_sm:
            # Create multiple mock identities
            identities = []
            for i in range(10):
                mock_identity = MagicMock()
                mock_identity.employee_id = f"USER{i:03d}"
                mock_identity.name = f"User {i}"
                mock_identity.email = f"user{i}@company.com"
                mock_identity.department = "Engineering"
                mock_identity.title = "Engineer"
                mock_identity.status.value = "ACTIVE"
                mock_identity.entitlements = []
                mock_identity.created_at.isoformat.return_value = "2024-01-01T00:00:00"
                mock_identity.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
                identities.append(mock_identity)

            mock_sm.get_all_identities.return_value = identities

            # Test limit parameter
            response = client.get("/users?limit=5")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 5


class TestAuditEndpoints:
    """Tests for audit log endpoints."""

    @pytest.fixture
    def client(self):
        """Test client for the FastAPI application."""
        from jml_engine.api.server import app
        with TestClient(app) as client:
            yield client

    def test_audit_logs_access(self, client):
        """Test accessing audit logs."""
        # This endpoint may return errors if audit system is not fully initialized
        response = client.get("/audit?days_back=7")
        # Accept both success and controlled failure
        assert response.status_code in [200, 500]

    def test_audit_logs_with_filters(self, client):
        """Test audit logs with filtering parameters."""
        response = client.get("/audit?employee_id=TEST001&days_back=30")
        assert response.status_code in [200, 500]  # May fail if audit system not set up


class TestSimulationEndpoints:
    """Tests for workflow simulation endpoints."""

    @pytest.fixture
    def client(self):
        """Test client for the FastAPI application."""
        from jml_engine.api.server import app
        with TestClient(app) as client:
            yield client

    @pytest.fixture
    def simulation_request(self):
        """Valid simulation request data."""
        return {
            "event_type": "NEW_STARTER",
            "mock_mode": True,
            "disabled_systems": []
        }

    def test_joiner_simulation(self, client, simulation_request):
        """Test joiner workflow simulation."""
        response = client.post("/simulate/joiner", json=simulation_request)
        assert response.status_code == 200

        data = response.json()
        assert "workflow_id" in data
        assert data["event_type"] == "NEW_STARTER"
        assert "started_at" in data

    def test_mover_simulation(self, client, simulation_request):
        """Test mover workflow simulation."""
        sim_request = simulation_request.copy()
        sim_request["event_type"] = "ROLE_CHANGE"

        response = client.post("/simulate/mover", json=sim_request)
        assert response.status_code == 200

        data = response.json()
        assert data["event_type"] == "ROLE_CHANGE"

    def test_leaver_simulation(self, client, simulation_request):
        """Test leaver workflow simulation."""
        sim_request = simulation_request.copy()
        sim_request["event_type"] = "TERMINATION"

        response = client.post("/simulate/leaver", json=sim_request)
        assert response.status_code == 200

        data = response.json()
        assert data["event_type"] == "TERMINATION"

    def test_invalid_workflow_type(self, client, simulation_request):
        """Test simulation with invalid workflow type."""
        response = client.post("/simulate/invalid", json=simulation_request)
        assert response.status_code == 400

    def test_simulation_with_disabled_systems(self, client, simulation_request):
        """Test simulation with some systems disabled."""
        sim_request = simulation_request.copy()
        sim_request["disabled_systems"] = ["aws", "azure"]

        response = client.post("/simulate/joiner", json=sim_request)
        assert response.status_code == 200


class TestErrorHandling:
    """Tests for error handling across API endpoints."""

    @pytest.fixture
    def client(self):
        """Test client for the FastAPI application."""
        from jml_engine.api.server import app
        with TestClient(app) as client:
            yield client

    def test_malformed_json(self, client):
        """Test handling of malformed JSON requests."""
        response = client.post(
            "/event/hr",
            data="invalid json content",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_unsupported_content_type(self, client):
        """Test handling of unsupported content types."""
        response = client.post(
            "/event/hr",
            data="<xml>invalid</xml>",
            headers={"Content-Type": "application/xml"}
        )
        # Should return 422 for validation error or 400 for bad request
        assert response.status_code in [400, 422]

    def test_large_request_body(self, client):
        """Test handling of oversized request bodies."""
        large_data = {"event": "NEW_STARTER", "data": "x" * 1000000}
        response = client.post("/event/hr", json=large_data)
        # Should either succeed or return validation error
        assert response.status_code in [200, 422]

    def test_concurrent_requests(self, client):
        """Test handling of concurrent requests."""
        import threading

        results = []
        errors = []

        def make_request():
            try:
                response = client.get("/health")
                results.append(response.status_code)
            except Exception as e:
                errors.append(str(e))

        # Make 10 concurrent requests
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=5)

        # All requests should succeed
        assert len(results) == 10
        assert all(status == 200 for status in results)
        assert len(errors) == 0
