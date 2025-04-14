"""
exporter.py — Prometheus metrics HTTP server
Exposes EKS health check results as Prometheus metrics.
Allows Grafana dashboards and Alertmanager rules to consume health data.

Usage:
    python -m eks_health_check.metrics.exporter --namespace finance --port 9090

Metrics exposed:
    eks_nodes_total{status="ready|not_ready"}
    eks_deployments_unhealthy{namespace="finance"}
    eks_oom_events_total{namespace="finance"}
    eks_hpa_at_max{hpa="payment-api-hpa",namespace="finance"}
    eks_container_restarts_total{pod="...",container="...",namespace="finance"}
    eks_health_overall{namespace="finance"} — 0=HEALTHY 1=DEGRADED
"""
import argparse
import logging
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

log = logging.getLogger(__name__)

METRICS_TEMPLATE = """
# HELP eks_nodes_total Total EKS nodes by readiness status
# TYPE eks_nodes_total gauge
eks_nodes_total{{status="ready"}} {ready_nodes}
eks_nodes_total{{status="not_ready"}} {not_ready_nodes}

# HELP eks_deployments_unhealthy Deployments with ready < desired replicas
# TYPE eks_deployments_unhealthy gauge
eks_deployments_unhealthy{{namespace="{namespace}"}} {unhealthy_deployments}

# HELP eks_oom_events_total OOM events in last 60 minutes
# TYPE eks_oom_events_total gauge
eks_oom_events_total{{namespace="{namespace}"}} {oom_events}

# HELP eks_hpas_at_max HPAs currently at maximum replica count
# TYPE eks_hpas_at_max gauge
eks_hpas_at_max{{namespace="{namespace}"}} {hpas_at_max}

# HELP eks_restart_alerts Containers with restart count above threshold
# TYPE eks_restart_alerts gauge
eks_restart_alerts{{namespace="{namespace}"}} {restart_alerts}

# HELP eks_health_overall Overall cluster health — 0=HEALTHY 1=DEGRADED
# TYPE eks_health_overall gauge
eks_health_overall{{namespace="{namespace}"}} {overall}
"""


def generate_metrics(namespace: str, restart_threshold: int = 5) -> str:
    """Run health checks and format as Prometheus text exposition."""
    try:
        from kubernetes import client, config
        from eks_health_check.checker import EKSHealthChecker

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        checker = EKSHealthChecker(
            core_v1=client.CoreV1Api(),
            apps_v1=client.AppsV1Api(),
            autoscaling_v2=client.AutoscalingV2Api(),
        )
        summary = checker.get_summary(namespace, restart_threshold)

        nodes = summary["nodes"]
        ready = len([n for n in nodes if n["ready"]])
        not_ready = len(nodes) - ready

        return METRICS_TEMPLATE.format(
            namespace=namespace,
            ready_nodes=ready,
            not_ready_nodes=not_ready,
            unhealthy_deployments=len([
                d for d in summary["deployments"] if not d["healthy"]
            ]),
            oom_events=len(summary["oom_events"]),
            hpas_at_max=len([h for h in summary["hpa"] if h["at_max_capacity"]]),
            restart_alerts=len(summary["restart_alerts"]),
            overall=1 if summary["overall_status"] == "DEGRADED" else 0,
        )

    except Exception as e:
        log.error(f"Failed to generate metrics: {e}")
        return f"# ERROR generating metrics: {e}\n"


class MetricsHandler(BaseHTTPRequestHandler):
    namespace = "finance"
    restart_threshold = 5

    def do_GET(self):
        if self.path in ("/metrics", "/"):
            metrics = generate_metrics(self.namespace, self.restart_threshold)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(metrics.encode())
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        log.debug(f"HTTP {args}")


def main():
    parser = argparse.ArgumentParser(description="EKS Health Prometheus Exporter")
    parser.add_argument("--namespace", default="finance")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--restart-threshold", type=int, default=5)
    args = parser.parse_args()

    MetricsHandler.namespace = args.namespace
    MetricsHandler.restart_threshold = args.restart_threshold

    server = HTTPServer(("0.0.0.0", args.port), MetricsHandler)
    log.info(f"Prometheus metrics server on port {args.port}/metrics")
    log.info(f"Namespace: {args.namespace}")
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
