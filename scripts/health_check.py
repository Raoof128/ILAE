#!/usr/bin/env python3
"""
JML Engine Health Check Script.

This script performs comprehensive health checks on all JML Engine components
and reports system status, performance metrics, and potential issues.
"""

import sys
import time
import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class HealthChecker:
    """Comprehensive health checker for JML Engine."""

    def __init__(self, api_url: str = "http://localhost:8000", dashboard_url: str = "http://localhost:8501"):
        self.api_url = api_url.rstrip('/')
        self.dashboard_url = dashboard_url.rstrip('/')
        self.results = {}

    def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        logger.info("Starting comprehensive health check...")

        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "unknown",
            "checks": {},
            "metrics": {},
            "recommendations": []
        }

        # Run individual checks
        self._check_api_health()
        self._check_dashboard_health()
        self._check_system_stats()
        self._check_audit_system()
        self._check_connectors()
        self._check_performance()

        # Determine overall status
        self._calculate_overall_status()

        # Generate recommendations
        self._generate_recommendations()

        logger.info(f"Health check completed. Overall status: {self.results['overall_status']}")
        return self.results

    def _check_api_health(self):
        """Check API service health."""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            if response.status_code == 200:
                health_data = response.json()
                self.results["checks"]["api"] = {
                    "status": "healthy" if health_data.get("status") == "healthy" else "unhealthy",
                    "response_time": response.elapsed.total_seconds(),
                    "details": health_data
                }
            else:
                self.results["checks"]["api"] = {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}"
                }
        except Exception as e:
            self.results["checks"]["api"] = {
                "status": "unhealthy",
                "error": str(e)
            }

    def _check_dashboard_health(self):
        """Check dashboard service health."""
        try:
            response = requests.get(f"{self.dashboard_url}/health", timeout=10)
            if response.status_code == 200:
                self.results["checks"]["dashboard"] = {
                    "status": "healthy",
                    "response_time": response.elapsed.total_seconds()
                }
            else:
                self.results["checks"]["dashboard"] = {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}"
                }
        except Exception as e:
            self.results["checks"]["dashboard"] = {
                "status": "degraded",  # Dashboard might not have health endpoint
                "error": str(e)
            }

    def _check_system_stats(self):
        """Check system statistics."""
        try:
            response = requests.get(f"{self.api_url}/stats", timeout=15)
            if response.status_code == 200:
                stats = response.json()
                self.results["checks"]["system_stats"] = {
                    "status": "healthy",
                    "data": stats
                }

                # Store metrics
                identities = stats.get("identities", {})
                evidence = stats.get("evidence", {})

                self.results["metrics"].update({
                    "total_users": identities.get("total_users", 0),
                    "total_entitlements": identities.get("total_entitlements", 0),
                    "evidence_files": evidence.get("total_files", 0),
                    "evidence_size_mb": evidence.get("total_size_bytes", 0) / (1024 * 1024)
                })
            else:
                self.results["checks"]["system_stats"] = {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}"
                }
        except Exception as e:
            self.results["checks"]["system_stats"] = {
                "status": "unhealthy",
                "error": str(e)
            }

    def _check_audit_system(self):
        """Check audit system health."""
        try:
            # Try to get recent audit logs
            response = requests.get(f"{self.api_url}/audit?days_back=1", timeout=15)
            if response.status_code == 200:
                audit_data = response.json()
                self.results["checks"]["audit_system"] = {
                    "status": "healthy",
                    "recent_logs": len(audit_data)
                }
            else:
                self.results["checks"]["audit_system"] = {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}"
                }
        except Exception as e:
            self.results["checks"]["audit_system"] = {
                "status": "unhealthy",
                "error": str(e)
            }

    def _check_connectors(self):
        """Check connector configurations."""
        # This is a basic check - in a real implementation,
        # you might test actual connectivity to external systems
        self.results["checks"]["connectors"] = {
            "status": "unknown",
            "note": "Connector health checks require specific credentials and are not run in basic health check"
        }

    def _check_performance(self):
        """Check system performance metrics."""
        # Simulate load test or check response times
        start_time = time.time()

        try:
            # Make multiple requests to check performance
            for i in range(5):
                requests.get(f"{self.api_url}/health", timeout=5)

            end_time = time.time()
            avg_response_time = (end_time - start_time) / 5

            self.results["checks"]["performance"] = {
                "status": "healthy" if avg_response_time < 1.0 else "degraded",
                "avg_response_time": avg_response_time,
                "note": f"Average response time: {avg_response_time:.2f}s"
            }
        except Exception as e:
            self.results["checks"]["performance"] = {
                "status": "unhealthy",
                "error": str(e)
            }

    def _calculate_overall_status(self):
        """Calculate overall system status."""
        statuses = [check.get("status", "unknown") for check in self.results["checks"].values()]

        if all(status == "healthy" for status in statuses):
            self.results["overall_status"] = "healthy"
        elif "unhealthy" in statuses:
            self.results["overall_status"] = "unhealthy"
        elif "degraded" in statuses:
            self.results["overall_status"] = "degraded"
        else:
            self.results["overall_status"] = "warning"

    def _generate_recommendations(self):
        """Generate health recommendations."""
        recommendations = []

        # Check API health
        api_check = self.results["checks"].get("api", {})
        if api_check.get("status") != "healthy":
            recommendations.append("API service is not healthy - check logs and restart if necessary")

        # Check system stats
        metrics = self.results.get("metrics", {})
        if metrics.get("total_users", 0) == 0:
            recommendations.append("No users found in system - verify HR event processing")

        # Check evidence
        if metrics.get("evidence_files", 0) == 0:
            recommendations.append("No audit evidence found - verify audit logging is working")

        # Check performance
        perf_check = self.results["checks"].get("performance", {})
        if perf_check.get("status") == "degraded":
            recommendations.append("API response times are slow - consider scaling or optimization")

        self.results["recommendations"] = recommendations

    def print_report(self):
        """Print formatted health report."""
        print("\n" + "="*60)
        print("🔍 JML ENGINE HEALTH REPORT")
        print("="*60)
        print(f"Timestamp: {self.results['timestamp']}")
        print(f"Overall Status: {self.results['overall_status'].upper()}")
        print()

        # Print checks
        print("📊 COMPONENT STATUS")
        print("-" * 40)
        for component, check in self.results["checks"].items():
            status = check.get("status", "unknown").upper()
            status_icon = {
                "healthy": "✅",
                "degraded": "⚠️",
                "unhealthy": "❌",
                "unknown": "❓"
            }.get(check.get("status"), "❓")

            print(f"{status_icon} {component.replace('_', ' ').title()}: {status}")

            if "error" in check:
                print(f"   Error: {check['error']}")
            if "note" in check:
                print(f"   Note: {check['note']}")

        print()

        # Print metrics
        if self.results.get("metrics"):
            print("📈 SYSTEM METRICS")
            print("-" * 40)
            metrics = self.results["metrics"]
            print(f"Total Users: {metrics.get('total_users', 'N/A')}")
            print(f"Total Entitlements: {metrics.get('total_entitlements', 'N/A')}")
            print(f"Audit Evidence Files: {metrics.get('evidence_files', 'N/A')}")
            print(f"Evidence Size: {metrics.get('evidence_size_mb', 'N/A'):.1f} MB")
            print()

        # Print recommendations
        if self.results.get("recommendations"):
            print("💡 RECOMMENDATIONS")
            print("-" * 40)
            for rec in self.results["recommendations"]:
                print(f"• {rec}")

        print("\n" + "="*60)

    def save_report(self, filename: str):
        """Save health report to JSON file."""
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"Health report saved to: {filename}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="JML Engine Health Check")
    parser.add_argument("--api-url", default="http://localhost:8000",
                       help="JML API base URL")
    parser.add_argument("--dashboard-url", default="http://localhost:8501",
                       help="JML Dashboard base URL")
    parser.add_argument("--save", help="Save report to JSON file")
    parser.add_argument("--quiet", action="store_true",
                       help="Suppress output, only return exit code")

    args = parser.parse_args()

    checker = HealthChecker(args.api_url, args.dashboard_url)
    results = checker.run_all_checks()

    if not args.quiet:
        checker.print_report()

    if args.save:
        checker.save_report(args.save)

    # Exit with appropriate code
    status_codes = {
        "healthy": 0,
        "degraded": 1,
        "unhealthy": 2,
        "warning": 3,
        "unknown": 4
    }

    sys.exit(status_codes.get(results["overall_status"], 4))


if __name__ == "__main__":
    main()
