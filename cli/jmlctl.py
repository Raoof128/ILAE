#!/usr/bin/env python3
"""
JML Control CLI - Command Line Interface for the JML Engine.

Provides commands for managing HR events, testing workflows, viewing audit logs,
and administering the JML Engine system.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import sys

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Confirm, Prompt

from ..models import HREvent, LifecycleEvent
from ..ingestion import HREventListener
from ..workflows import JoinerWorkflow, MoverWorkflow, LeaverWorkflow, validate_hr_event
from ..engine import PolicyMapper, StateManager
from ..audit import AuditLogger, EvidenceStore
from ..connectors import AWSConnector, AzureConnector, GitHubConnector, GoogleConnector, SlackConnector

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Rich console for pretty output
console = Console()


class JMLController:
    """Main controller for JML Engine operations."""

    def __init__(self, config_path: Optional[str] = None, mock_mode: bool = True):
        """Initialize the JML controller."""
        self.config_path = Path(config_path) if config_path else None
        self.mock_mode = mock_mode

        # Load configuration
        self.config = self._load_config()

        # Initialize components
        self.hr_listener = HREventListener()
        self.policy_mapper = PolicyMapper()
        self.state_manager = StateManager(self.config.get('state_file'))
        self.audit_logger = AuditLogger(self.config.get('audit_dir', 'audit'))
        self.evidence_store = EvidenceStore()

        console.print(f"[green]JML Engine initialized (mock_mode={mock_mode})[/green]")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or use defaults."""
        config = {
            "mock_mode": self.mock_mode,
            "connectors": {
                "aws": {},
                "azure": {},
                "github": {},
                "google": {},
                "slack": {}
            }
        }

        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    file_config = json.load(f)
                    config.update(file_config)
                console.print(f"[blue]Loaded configuration from {self.config_path}[/blue]")
            except Exception as e:
                console.print(f"[red]Error loading config: {e}[/red]")

        return config


@click.group()
@click.option('--config', '-c', help='Path to configuration file')
@click.option('--mock/--real', default=True, help='Use mock mode (default) or real API connections')
@click.pass_context
def cli(ctx, config, mock):
    """JML Engine Control CLI - Enterprise IAM Lifecycle Automation"""
    ctx.ensure_object(dict)
    ctx.obj['controller'] = JMLController(config, mock)


@cli.command()
@click.argument('event_file', type=click.Path(exists=True))
@click.pass_context
def process_event(ctx, event_file):
    """Process an HR event from a JSON file."""
    controller = ctx.obj['controller']

    try:
        # Load event from file
        with open(event_file, 'r') as f:
            event_data = json.load(f)

        # Convert to HREvent
        hr_event = HREvent(**event_data)

        # Validate event
        validation_errors = validate_hr_event(hr_event)
        if validation_errors:
            console.print("[red]Event validation failed:[/red]")
            for error in validation_errors:
                console.print(f"  - {error}")
            return

        # Determine workflow type
        from ..workflows.helpers import determine_workflow_type
        workflow_type = determine_workflow_type(hr_event)

        console.print(f"[blue]Processing {workflow_type} workflow for {hr_event.employee_id}[/blue]")

        # Execute workflow
        if workflow_type == "joiner":
            workflow = JoinerWorkflow(controller.config)
        elif workflow_type == "mover":
            workflow = MoverWorkflow(controller.config)
        elif workflow_type == "leaver":
            workflow = LeaverWorkflow(controller.config)
        else:
            console.print("[red]Unknown workflow type[/red]")
            return

        result = workflow.execute(hr_event)

        # Display results
        if result.success:
            console.print(f"[green]✓ Workflow completed successfully[/green]")
        else:
            console.print(f"[red]✗ Workflow failed with {len(result.errors)} errors[/red]")

        # Show summary
        table = Table(title="Workflow Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")

        table.add_row("Workflow ID", result.workflow_id)
        table.add_row("Employee ID", result.employee_id)
        table.add_row("Event Type", result.event_type)
        table.add_row("Total Steps", str(len(result.actions_taken)))
        table.add_row("Successful Steps", str(sum(1 for a in result.actions_taken if a.get('success', False))))
        table.add_row("Failed Steps", str(sum(1 for a in result.actions_taken if not a.get('success', False))))

        console.print(table)

        if result.errors:
            console.print("[red]Errors:[/red]")
            for error in result.errors:
                console.print(f"  - {error}")

    except Exception as e:
        console.print(f"[red]Error processing event: {e}[/red]")
        logger.exception("Event processing failed")


@cli.command()
@click.option('--event-type', type=click.Choice(['NEW_STARTER', 'ROLE_CHANGE', 'TERMINATION']), default='NEW_STARTER')
@click.option('--employee-id', prompt='Employee ID')
@click.option('--name', prompt='Full Name')
@click.option('--email', prompt='Email Address')
@click.option('--department', prompt='Department')
@click.option('--title', prompt='Job Title')
@click.pass_context
def simulate(ctx, event_type, employee_id, name, email, department, title):
    """Simulate an HR event for testing."""
    controller = ctx.obj['controller']

    try:
        # Create HR event
        hr_event = HREvent(
            event=event_type,
            employee_id=employee_id,
            name=name,
            email=email,
            department=department,
            title=title,
            source_system="CLI_SIMULATION"
        )

        # Add additional fields for mover events
        if event_type == "ROLE_CHANGE":
            hr_event.previous_department = click.prompt("Previous Department")
            hr_event.previous_title = click.prompt("Previous Title")

        console.print(f"[blue]Simulating {event_type} event for {employee_id}[/blue]")

        # Execute appropriate workflow
        from ..workflows.helpers import determine_workflow_type
        workflow_type = determine_workflow_type(hr_event)

        if workflow_type == "joiner":
            workflow = JoinerWorkflow(controller.config)
        elif workflow_type == "mover":
            workflow = MoverWorkflow(controller.config)
        elif workflow_type == "leaver":
            workflow = LeaverWorkflow(controller.config)

        result = workflow.execute(hr_event)

        # Display results
        display_workflow_results(result)

    except Exception as e:
        console.print(f"[red]Simulation failed: {e}[/red]")
        logger.exception("Simulation failed")


@cli.command()
@click.argument('employee_id')
@click.pass_context
def show_user(ctx, employee_id):
    """Show user identity and entitlements."""
    controller = ctx.obj['controller']

    identity = controller.state_manager.get_identity(employee_id)
    if not identity:
        console.print(f"[red]User {employee_id} not found[/red]")
        return

    # Display user info
    console.print(Panel.fit(f"[bold blue]{identity.name}[/bold blue]\n{identity.email}"))
    console.print(f"Department: {identity.department}")
    console.print(f"Title: {identity.title}")
    console.print(f"Status: {identity.status.value}")
    console.print(f"Created: {identity.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"Updated: {identity.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")

    # Display entitlements
    if identity.entitlements:
        console.print(f"\n[bold]Access Entitlements ({len(identity.entitlements)})[/bold]")

        table = Table()
        table.add_column("System", style="cyan")
        table.add_column("Resource Type", style="green")
        table.add_column("Resource Name", style="yellow")
        table.add_column("Permission", style="magenta")

        for ent in identity.entitlements:
            table.add_row(
                ent.system,
                ent.resource_type,
                ent.resource_name,
                ent.permission_level or "N/A"
            )

        console.print(table)
    else:
        console.print("[yellow]No access entitlements found[/yellow]")


@cli.command()
@click.option('--department', help='Filter by department')
@click.option('--status', help='Filter by status')
@click.option('--limit', default=50, help='Maximum number of users to show')
@click.pass_context
def list_users(ctx, department, status, limit):
    """List user identities."""
    controller = ctx.obj['controller']

    identities = controller.state_manager.get_all_identities()

    # Apply filters
    if department:
        identities = [i for i in identities if i.department == department]
    if status:
        identities = [i for i in identities if i.status.value == status]

    identities = identities[:limit]

    if not identities:
        console.print("[yellow]No users found[/yellow]")
        return

    table = Table(title=f"Users ({len(identities)})")
    table.add_column("Employee ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Email", style="blue")
    table.add_column("Department", style="yellow")
    table.add_column("Title", style="magenta")
    table.add_column("Status", style="red")

    for identity in identities:
        table.add_row(
            identity.employee_id,
            identity.name,
            identity.email,
            identity.department,
            identity.title,
            identity.status.value
        )

    console.print(table)


@cli.command()
@click.argument('employee_id')
@click.option('--days', default=90, help='Number of days to look back')
@click.pass_context
def audit_trail(ctx, employee_id, days):
    """Show audit trail for a user."""
    controller = ctx.obj['controller']

    try:
        audit_records = controller.audit_logger.get_audit_trail(employee_id, days)

        if not audit_records:
            console.print(f"[yellow]No audit records found for {employee_id}[/yellow]")
            return

        table = Table(title=f"Audit Trail for {employee_id}")
        table.add_column("Timestamp", style="cyan")
        table.add_column("Event Type", style="green")
        table.add_column("System", style="yellow")
        table.add_column("Action", style="magenta")
        table.add_column("Resource", style="blue")
        table.add_column("Success", style="red")

        for record in audit_records:
            success_icon = "✓" if record.success else "✗"
            table.add_row(
                record.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                record.event_type,
                record.system,
                record.action,
                record.resource,
                success_icon
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error retrieving audit trail: {e}[/red]")


@cli.command()
@click.pass_context
def stats(ctx):
    """Show system statistics."""
    controller = ctx.obj['controller']

    try:
        identity_stats = controller.state_manager.get_identities_summary()
        evidence_stats = controller.evidence_store.get_evidence_stats()

        # Display identity stats
        console.print("[bold blue]Identity Statistics[/bold blue]")
        console.print(f"Total Users: {identity_stats['total_users']}")
        console.print(f"Total Entitlements: {identity_stats['total_entitlements']}")

        if identity_stats['users_by_department']:
            console.print("\nUsers by Department:")
            for dept, count in identity_stats['users_by_department'].items():
                console.print(f"  {dept}: {count}")

        if identity_stats['users_by_status']:
            console.print("\nUsers by Status:")
            for status, count in identity_stats['users_by_status'].items():
                console.print(f"  {status}: {count}")

        # Display evidence stats
        console.print(f"\n[bold blue]Evidence Statistics[/bold blue]")
        console.print(f"Total Evidence Files: {evidence_stats['total_files']}")
        console.print(f"Total Size: {evidence_stats['total_size_bytes']:,} bytes")

        if evidence_stats['files_by_system']:
            console.print("\nEvidence by System:")
            for system, count in evidence_stats['files_by_system'].items():
                console.print(f"  {system}: {count}")

    except Exception as e:
        console.print(f"[red]Error retrieving statistics: {e}[/red]")


@cli.command()
@click.option('--start-date', help='Start date (YYYY-MM-DD)')
@click.option('--end-date', help='End date (YYYY-MM-DD)')
@click.option('--frameworks', help='Compliance frameworks (comma-separated)')
@click.pass_context
def compliance_report(ctx, start_date, end_date, frameworks):
    """Generate compliance report."""
    controller = ctx.obj['controller']

    from datetime import datetime, timedelta

    # Default date range
    if not end_date:
        end_date = datetime.utcnow()
    else:
        end_date = datetime.fromisoformat(end_date)

    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.fromisoformat(start_date)

    # Default frameworks
    if not frameworks:
        frameworks = ["ISO_27001", "SOC2", "APRA_CPS_234", "Essential_8"]
    else:
        frameworks = [f.strip() for f in frameworks.split(',')]

    try:
        report = controller.audit_logger.generate_compliance_report(
            start_date, end_date, frameworks
        )

        console.print(f"[bold blue]Compliance Report[/bold blue]")
        console.print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        console.print(f"Frameworks: {', '.join(frameworks)}")

        console.print("
[bold]Summary[/bold]"        console.print(f"Total Events: {report['summary']['total_events']}")
        console.print(f"Successful Operations: {report['summary']['successful_operations']}")
        console.print(f"Failed Operations: {report['summary']['failed_operations']}")
        console.print(f"Critical Failures: {report['summary']['critical_failures']}")

        if report['findings']:
            console.print(f"\n[bold]Findings ({len(report['findings'])})[/bold]")
            for finding in report['findings'][:10]:  # Show first 10
                console.print(f"• [{finding['severity']}] {finding['framework']}: {finding['finding']}")

        if report['recommendations']:
            console.print(f"\n[bold]Recommendations[/bold]")
            for rec in report['recommendations']:
                console.print(f"• {rec}")

    except Exception as e:
        console.print(f"[red]Error generating compliance report: {e}[/red]")


@cli.command()
@click.option('--port', default=8000, help='Port to run the API server on')
@click.option('--host', default='127.0.0.1', help='Host to bind the API server to')
@click.pass_context
def serve(ctx, port, host):
    """Start the JML Engine API server."""
    from ..api.server import start_server

    console.print(f"[green]Starting JML Engine API server on {host}:{port}[/green]")
    console.print("[blue]Press Ctrl+C to stop[/blue]")

    try:
        start_server(host=host, port=port, reload=False)
    except KeyboardInterrupt:
        console.print("[yellow]Server stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Server error: {e}[/red]")


def display_workflow_results(result):
    """Display workflow execution results."""
    if result.success:
        console.print(f"[green]✓ Workflow completed successfully[/green]")
    else:
        console.print(f"[red]✗ Workflow failed with {len(result.errors)} errors[/red]")

    # Show summary table
    table = Table(title="Workflow Execution Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")

    table.add_row("Workflow ID", result.workflow_id)
    table.add_row("Employee ID", result.employee_id)
    table.add_row("Event Type", result.event_type)
    table.add_row("Started", result.started_at.strftime("%Y-%m-%d %H:%M:%S") if result.started_at else "N/A")
    table.add_row("Completed", result.completed_at.strftime("%Y-%m-%d %H:%M:%S") if result.completed_at else "N/A")
    table.add_row("Total Steps", str(len(result.actions_taken)))
    table.add_row("Successful", str(sum(1 for a in result.actions_taken if a.get('success', False))))
    table.add_row("Failed", str(sum(1 for a in result.actions_taken if not a.get('success', False))))

    console.print(table)

    # Show errors if any
    if result.errors:
        console.print("[red]Errors:[/red]")
        for error in result.errors:
            console.print(f"  - {error}")


if __name__ == "__main__":
    cli()
