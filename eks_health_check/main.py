#!/usr/bin/env python3
"""
eks_health_check/main.py — EKS cluster health reporter CLI
Checks node readiness, deployment availability, OOM events,
HPA capacity, container restart counts, and pending pods.

Usage:
    python -m eks_health_check.main --namespace finance --output text
    python -m eks_health_check.main --namespace finance --output json
    python -m eks_health_check.main --namespace finance --restart-threshold 3

Exit codes:
    0 — HEALTHY
    1 — DEGRADED (unhealthy nodes, OOM events, HPA at max, or restarts above threshold)
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from eks_health_check.checker import EKSHealthChecker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [eks_health_check] %(message)s"
)
log = logging.getLogger(__name__)


def load_kube_config():
    """Load kubeconfig — in-cluster first, then local kubeconfig."""
    try:
        config.load_incluster_config()
        log.info("Loaded in-cluster kubeconfig")
    except config.ConfigException:
        config.load_kube_config()
        log.info("Loaded local kubeconfig")


def build_report(checker: EKSHealthChecker, namespace: str,
                 restart_threshold: int, lookback_minutes: int) -> dict:
    """Run all checks and assemble health report."""
    log.info(f"Running health checks for namespace={namespace}")

    nodes = checker.check_nodes()
    deployments = checker.check_deployments(namespace)
    oom_events = checker.check_oom_events(namespace, lookback_minutes)
    hpa_status = checker.check_hpa(namespace)
    restart_alerts = checker.check_restart_counts(namespace, restart_threshold)
    pending_pods = checker.check_pending_pods(namespace)

    unhealthy_nodes = len([n for n in nodes if not n["ready"]])
    unhealthy_deployments = len([d for d in deployments if not d["healthy"]])
    hpas_at_max = len([h for h in hpa_status if h["at_max_capacity"]])

    overall = "HEALTHY"
    if any([unhealthy_nodes, unhealthy_deployments, oom_events,
            hpas_at_max, restart_alerts, pending_pods]):
        overall = "DEGRADED"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "namespace": namespace,
        "nodes": nodes,
        "deployments": deployments,
        "oom_events": oom_events,
        "hpa_status": hpa_status,
        "restart_alerts": restart_alerts,
        "pending_pods": pending_pods,
        "summary": {
            "total_nodes": len(nodes),
            "unhealthy_nodes": unhealthy_nodes,
            "total_deployments": len(deployments),
            "unhealthy_deployments": unhealthy_deployments,
            "oom_events_count": len(oom_events),
            "hpas_at_max": hpas_at_max,
            "restart_alerts_count": len(restart_alerts),
            "pending_pods_count": len(pending_pods),
            "overall_status": overall,
        },
    }


def print_text_report(report: dict):
    """Print human-readable health report."""
    s = report["summary"]
    print(f"\n{'='*55}")
    print(f"  EKS Health Report — {report['timestamp']}")
    print(f"{'='*55}")
    print(f"  Namespace          : {report['namespace']}")
    print(f"  Nodes              : {s['total_nodes']} total, "
          f"{s['unhealthy_nodes']} unhealthy")
    print(f"  Deployments        : {s['total_deployments']} total, "
          f"{s['unhealthy_deployments']} unhealthy")
    print(f"  OOM Events (last hr): {s['oom_events_count']}")
    print(f"  HPAs at max        : {s['hpas_at_max']}")
    print(f"  Restart alerts     : {s['restart_alerts_count']}")
    print(f"  Pending pods       : {s['pending_pods_count']}")
    print(f"  Overall status     : {s['overall_status']}")
    print(f"{'='*55}\n")

    if report["restart_alerts"]:
        print("  Restart Alerts:")
        for r in report["restart_alerts"]:
            print(f"    - {r['pod']}/{r['container']}: "
                  f"{r['restart_count']} restarts "
                  f"(last: {r['last_termination_reason']})")

    if report["oom_events"]:
        print("\n  OOM Events:")
        for e in report["oom_events"]:
            print(f"    - {e['pod']}: count={e['count']} — {e['message']}")

    if report["hpa_status"]:
        print("\n  HPA Status:")
        for h in report["hpa_status"]:
            flag = " ⚠ AT MAX" if h["at_max_capacity"] else ""
            print(f"    - {h['name']}: "
                  f"{h['current_replicas']}/{h['max_replicas']}{flag}")


def main():
    parser = argparse.ArgumentParser(
        description="EKS Cluster Health Reporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--namespace", default="finance",
                        help="Kubernetes namespace to check (default: finance)")
    parser.add_argument("--output", default="text", choices=["text", "json"],
                        help="Output format (default: text)")
    parser.add_argument("--restart-threshold", type=int, default=5,
                        help="Flag containers with restarts above this count (default: 5)")
    parser.add_argument("--lookback-minutes", type=int, default=60,
                        help="OOM event lookback window in minutes (default: 60)")
    parser.add_argument("--kubeconfig", default=None,
                        help="Path to kubeconfig file (default: auto-detect)")
    args = parser.parse_args()

    try:
        load_kube_config()
    except Exception as e:
        log.error(f"Failed to load kubeconfig: {e}")
        sys.exit(1)

    checker = EKSHealthChecker(
        core_v1=client.CoreV1Api(),
        apps_v1=client.AppsV1Api(),
        autoscaling_v2=client.AutoscalingV2Api(),
        policy_v1=client.PolicyV1Api(),
    )

    try:
        report = build_report(
            checker, args.namespace,
            args.restart_threshold, args.lookback_minutes
        )
    except ApiException as e:
        log.error(f"Kubernetes API error: {e}")
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        print_text_report(report)

    if report["summary"]["overall_status"] == "DEGRADED":
        sys.exit(1)


if __name__ == "__main__":
    main()
