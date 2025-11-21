"""
JML Engine Dashboard - Streamlit Web Interface

Provides a web-based interface for managing identities, viewing audit logs,
and monitoring JML Engine operations.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="JML Engine Dashboard",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API configuration
API_BASE_URL = st.secrets.get("API_BASE_URL", "http://localhost:8000")

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 0.25rem solid #1f77b4;
    }
    .status-active {
        color: #28a745;
        font-weight: bold;
    }
    .status-inactive {
        color: #dc3545;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


def make_api_request(endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Optional[Dict]:
    """Make API request with error handling."""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data)
        else:
            st.error(f"Unsupported HTTP method: {method}")
            return None

        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API request failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        st.error(f"API connection error: {e}")
        return None


def display_identity(identity: Dict) -> None:
    """Display user identity information."""
    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown(f"### {identity['name']}")
        st.markdown(f"**Email:** {identity['email']}")
        status_class = "status-active" if identity['status'] == "ACTIVE" else "status-inactive"
        st.markdown(f"**Status:** <span class='{status_class}'>{identity['status']}</span>",
                   unsafe_allow_html=True)

    with col2:
        st.markdown(f"**Department:** {identity['department']}")
        st.markdown(f"**Title:** {identity['title']}")
        st.markdown(f"**Employee ID:** {identity['employee_id']}")
        st.markdown(f"**Entitlements:** {identity['entitlements_count']}")

        created = datetime.fromisoformat(identity['created_at'].replace('Z', '+00:00'))
        updated = datetime.fromisoformat(identity['updated_at'].replace('Z', '+00:00'))
        st.markdown(f"**Created:** {created.strftime('%Y-%m-%d %H:%M:%S')}")
        st.markdown(f"**Updated:** {updated.strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    """Main dashboard application."""
    st.markdown('<h1 class="main-header">🔐 JML Engine Dashboard</h1>', unsafe_allow_html=True)
    st.markdown("*IAM Lifecycle Automation for Joiner-Mover-Leaver Workflows*")

    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select Page",
        ["Overview", "Identities", "Audit Logs", "Workflow Simulation", "Compliance", "Settings"]
    )

    # Health check
    health_data = make_api_request("/health")
    if health_data:
        if health_data.get("status") == "healthy":
            st.sidebar.success("✅ System Healthy")
        else:
            st.sidebar.error("❌ System Issues")

    # Page content
    if page == "Overview":
        show_overview_page()
    elif page == "Identities":
        show_identities_page()
    elif page == "Audit Logs":
        show_audit_page()
    elif page == "Workflow Simulation":
        show_simulation_page()
    elif page == "Compliance":
        show_compliance_page()
    elif page == "Settings":
        show_settings_page()


def show_overview_page():
    """Display system overview dashboard."""
    st.header("System Overview")

    # Get system statistics
    stats_data = make_api_request("/stats")

    if stats_data:
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Users", stats_data['identities']['total_users'])

        with col2:
            st.metric("Total Entitlements", stats_data['identities']['total_entitlements'])

        with col3:
            st.metric("Evidence Files", stats_data['evidence']['total_files'])

        with col4:
            evidence_size_mb = stats_data['evidence']['total_size_bytes'] / (1024 * 1024)
            st.metric("Evidence Size", f"{evidence_size_mb:.1f} MB")

        # Charts
        col1, col2 = st.columns(2)

        with col1:
            # Users by department
            dept_data = stats_data['identities']['users_by_department']
            if dept_data:
                fig = px.bar(
                    x=list(dept_data.keys()),
                    y=list(dept_data.values()),
                    title="Users by Department",
                    labels={'x': 'Department', 'y': 'Count'}
                )
                st.plotly_chart(fig)

        with col2:
            # Users by status
            status_data = stats_data['identities']['users_by_status']
            if status_data:
                fig = px.pie(
                    values=list(status_data.values()),
                    names=list(status_data.keys()),
                    title="Users by Status"
                )
                st.plotly_chart(fig)

        # Evidence by system
        evidence_by_system = stats_data['evidence']['files_by_system']
        if evidence_by_system:
            st.subheader("Audit Evidence by System")
            fig = px.bar(
                x=list(evidence_by_system.keys()),
                y=list(evidence_by_system.values()),
                title="Evidence Files by System",
                labels={'x': 'System', 'y': 'Files'}
            )
            st.plotly_chart(fig)


def show_identities_page():
    """Display identities management page."""
    st.header("Identity Management")

    # Search and filters
    col1, col2, col3 = st.columns(3)

    with col1:
        search_term = st.text_input("Search by name or email")

    with col2:
        dept_filter = st.selectbox("Department", ["All"] + ["Engineering", "HR", "Finance", "Marketing", "Sales"])

    with col3:
        status_filter = st.selectbox("Status", ["All", "ACTIVE", "INACTIVE", "TERMINATED", "ON_LEAVE"])

    # Get users
    params = {}
    if dept_filter != "All":
        params["department"] = dept_filter
    if status_filter != "All":
        params["status"] = status_filter

    # For demo, get all users (in real implementation, use query parameters)
    users_data = make_api_request("/users")

    if users_data:
        # Filter locally for demo
        filtered_users = users_data
        if search_term:
            filtered_users = [
                u for u in filtered_users
                if search_term.lower() in u['name'].lower() or search_term.lower() in u['email'].lower()
            ]

        if dept_filter != "All":
            filtered_users = [u for u in filtered_users if u['department'] == dept_filter]

        if status_filter != "All":
            filtered_users = [u for u in filtered_users if u['status'] == status_filter]

        # Display users
        if filtered_users:
            for user in filtered_users:
                with st.expander(f"{user['name']} ({user['employee_id']})"):
                    display_identity(user)
        else:
            st.info("No users found matching the criteria")

        # Summary
        st.markdown(f"**Total users shown:** {len(filtered_users)}")


def show_audit_page():
    """Display audit logs page."""
    st.header("Audit Logs")

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        _employee_filter = st.text_input("Employee ID")

    with col2:
        _system_filter = st.selectbox("System", ["All", "aws", "azure", "github", "google", "slack"])

    with col3:
        days_back = st.slider("Days back", 1, 365, 30)

    # Get audit logs (simplified - in real implementation, use proper filtering)
    audit_data = make_api_request(f"/audit?days_back={days_back}")

    if audit_data:
        if audit_data:
            # Convert to DataFrame for display
            df = pd.DataFrame(audit_data)
            st.dataframe(df)

            # Summary statistics
            total_logs = len(audit_data)
            successful_ops = len([log for log in audit_data if log.get('success', False)])
            failed_ops = total_logs - successful_ops

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Operations", total_logs)
            col2.metric("Successful", successful_ops)
            col3.metric("Failed", failed_ops)
        else:
            st.info("No audit logs found for the specified criteria")
    else:
        st.error("Failed to retrieve audit logs")


def show_simulation_page():
    """Display workflow simulation page."""
    st.header("Workflow Simulation")

    st.markdown("""
    Test JML Engine workflows without affecting real systems.
    This page allows you to simulate Joiner, Mover, and Leaver events.
    """)

    # Simulation form
    with st.form("simulation_form"):
        col1, col2 = st.columns(2)

        with col1:
            event_type = st.selectbox(
                "Event Type",
                ["NEW_STARTER", "ROLE_CHANGE", "TERMINATION"],
                help="Type of HR event to simulate"
            )

            _employee_id = st.text_input("Employee ID", value="SIM001")
            _name = st.text_input("Full Name", value="John Doe")
            _email = st.text_input("Email", value="john.doe@company.com")

        with col2:
            _department = st.selectbox("Department", ["Engineering", "HR", "Finance", "Marketing", "Sales"])
            _title = st.text_input("Job Title", value="Software Engineer")

            # Additional fields for mover events
            if event_type == "ROLE_CHANGE":
                st.subheader("Previous Information")
                prev_dept = st.selectbox("Previous Department", ["Engineering", "HR", "Finance", "Marketing", "Sales"])
                prev_title = st.text_input("Previous Title", value="Junior Engineer")

        submitted = st.form_submit_button("Run Simulation")

        if submitted:
            # Prepare simulation data
            sim_data = {
                "event_type": event_type,
                "mock_mode": True,
                "disabled_systems": []
            }

            # Add event-specific data
            if event_type == "ROLE_CHANGE":
                sim_data.update({
                    "previous_department": prev_dept,
                    "previous_title": prev_title
                })

            # Run simulation
            with st.spinner("Running simulation..."):
                result = make_api_request(f"/simulate/{event_type.lower()}", "POST", sim_data)

            if result:
                st.success("Simulation completed!")

                # Display results
                col1, col2 = st.columns(2)
                col1.metric("Workflow ID", result.get("workflow_id", "N/A"))
                col2.metric("Status", result.get("status", "Unknown"))

                if result.get("errors"):
                    st.error("Simulation errors:")
                    for error in result["errors"]:
                        st.write(f"- {error}")
                else:
                    st.info("Simulation completed without errors")
            else:
                st.error("Simulation failed")


def show_compliance_page():
    """Display compliance reporting page."""
    st.header("Compliance Reporting")

    st.markdown("""
    Generate compliance reports for various regulatory frameworks
    including ISO 27001, SOC2, APRA CPS 234, and Essential 8.
    """)

    # Report configuration
    col1, col2, col3 = st.columns(3)

    with col1:
        _start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))

    with col2:
        _end_date = st.date_input("End Date", datetime.now())

    with col3:
        _frameworks = st.multiselect(
            "Frameworks",
            ["ISO_27001", "SOC2", "APRA_CPS_234", "Essential_8"],
            default=["ISO_27001", "SOC2"]
        )

    if st.button("Generate Report"):
        # In a real implementation, this would call the compliance API
        st.info("Compliance reporting feature coming soon!")
        st.markdown("This would generate detailed compliance reports based on audit data.")


def show_settings_page():
    """Display settings and configuration page."""
    st.header("Settings")

    st.markdown("System configuration and settings management.")

    # API Configuration
    st.subheader("API Configuration")
    _api_url = st.text_input("API Base URL", value=API_BASE_URL)
    if st.button("Update API URL"):
        st.success("API URL updated (would persist in real implementation)")

    # System Health
    st.subheader("System Health")
    if st.button("Run Health Check"):
        health = make_api_request("/health")
        if health:
            st.json(health)
        else:
            st.error("Health check failed")


if __name__ == "__main__":
    main()
