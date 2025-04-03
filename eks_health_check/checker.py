"""
checker.py — core health check logic
All Kubernetes API calls are encapsulated here for testability.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger(__name__)


class EKSHealthChecker:
    """
    Performs health checks against a Kubernetes cluster.
    Accepts a kubernetes client instance for dependency injection (testability).
    """

    def __init__(self, core_v1=None, apps_v1=None, autoscaling_v2=None, policy_v1=None):
        self.core_v1 = core_v1
        self.apps_v1 = apps_v1
        self.autoscaling_v2 = autoscaling_v2
        self.policy_v1 = policy_v1

    def check_nodes(self) -> list:
        """Check all node readiness and resource availability."""
        if not self.core_v1:
            return []
        nodes = self.core_v1.list_node()
        results = []
        for node in nodes.items:
            ready = False
            conditions = {}
            for cond in (node.status.conditions or []):
                conditions[cond.type] = cond.status
                if cond.type == "Ready":
                    ready = cond.status == "True"

            allocatable = node.status.allocatable or {}
            results.append({
                "name": node.metadata.name,
                "ready": ready,
                "conditions": conditions,
                "allocatable_cpu": allocatable.get("cpu", "unknown"),
                "allocatable_memory": allocatable.get("memory", "unknown"),
                "labels": dict(node.metadata.labels or {}),
                "role": node.metadata.labels.get(
                    "node.kubernetes.io/role",
                    node.metadata.labels.get("role", "worker")
                ) if node.metadata.labels else "worker",
            })
            if not ready:
                log.warning(f"Node {node.metadata.name} is NOT READY — conditions: {conditions}")
        return results

    def check_deployments(self, namespace: str) -> list:
        """Check deployment replica availability."""
        if not self.apps_v1:
            return []
        deployments = self.apps_v1.list_namespaced_deployment(namespace)
        results = []
        for dep in deployments.items:
            desired = dep.spec.replicas or 0
            ready = dep.status.ready_replicas or 0
            available = dep.status.available_replicas or 0
            unavailable = dep.status.unavailable_replicas or 0
            results.append({
                "name": dep.metadata.name,
                "namespace": namespace,
                "desired": desired,
                "ready": ready,
                "available": available,
                "unavailable": unavailable,
                "healthy": ready >= desired,
            })
            if ready < desired:
                log.warning(
                    f"Deployment {dep.metadata.name}: {ready}/{desired} replicas ready, "
                    f"{unavailable} unavailable"
                )
        return results

    def check_oom_events(self, namespace: str, lookback_minutes: int = 60) -> list:
        """Find OOMKilled events in the last N minutes."""
        if not self.core_v1:
            return []
        events = self.core_v1.list_namespaced_event(namespace)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
        oom_events = []
        for e in events.items:
            if not any(kw in (e.reason or "") or kw in (e.message or "")
                       for kw in ["OOMKill", "OOMKilling", "OOM"]):
                continue
            event_time = e.last_timestamp or e.event_time
            if event_time and hasattr(event_time, 'replace'):
                if event_time.replace(tzinfo=timezone.utc) < cutoff:
                    continue
            oom_events.append({
                "pod": e.involved_object.name,
                "namespace": e.involved_object.namespace,
                "reason": e.reason,
                "message": e.message,
                "count": e.count or 1,
                "last_seen": str(e.last_timestamp),
            })
            log.warning(
                f"OOM event: pod={e.involved_object.name} "
                f"count={e.count} message={e.message}"
            )
        return oom_events

    def check_hpa(self, namespace: str) -> list:
        """Check HPA status — flag at-max-capacity situations."""
        if not self.autoscaling_v2:
            return []
        hpas = self.autoscaling_v2.list_namespaced_horizontal_pod_autoscaler(namespace)
        results = []
        for hpa in hpas.items:
            current = hpa.status.current_replicas or 0
            desired = hpa.status.desired_replicas or 0
            max_rep = hpa.spec.max_replicas or 0
            min_rep = hpa.spec.min_replicas or 1
            at_max = current >= max_rep
            metrics_summary = []
            for m in (hpa.status.current_metrics or []):
                if m.resource:
                    metrics_summary.append({
                        "resource": m.resource.name,
                        "current": m.resource.current.average_utilization
                        if m.resource.current else None,
                    })
            results.append({
                "name": hpa.metadata.name,
                "namespace": namespace,
                "current_replicas": current,
                "desired_replicas": desired,
                "min_replicas": min_rep,
                "max_replicas": max_rep,
                "at_max_capacity": at_max,
                "current_metrics": metrics_summary,
            })
            if at_max:
                log.warning(
                    f"HPA {hpa.metadata.name} AT MAX CAPACITY: "
                    f"{current}/{max_rep} replicas"
                )
        return results

    def check_restart_counts(self, namespace: str, threshold: int = 5) -> list:
        """Flag containers with restart count above threshold."""
        if not self.core_v1:
            return []
        pods = self.core_v1.list_namespaced_pod(namespace)
        flagged = []
        for pod in pods.items:
            for cs in (pod.status.container_statuses or []):
                if cs.restart_count >= threshold:
                    last_state = None
                    if cs.last_state and cs.last_state.terminated:
                        last_state = cs.last_state.terminated.reason
                    flagged.append({
                        "pod": pod.metadata.name,
                        "container": cs.name,
                        "restart_count": cs.restart_count,
                        "last_termination_reason": last_state,
                    })
                    log.warning(
                        f"Pod {pod.metadata.name}/{cs.name}: "
                        f"{cs.restart_count} restarts "
                        f"(last reason: {last_state})"
                    )
        return flagged

    def check_pending_pods(self, namespace: str) -> list:
        """Find pods stuck in Pending state."""
        if not self.core_v1:
            return []
        pods = self.core_v1.list_namespaced_pod(namespace)
        pending = []
        for pod in pods.items:
            if pod.status.phase == "Pending":
                conditions = {}
                for c in (pod.status.conditions or []):
                    conditions[c.type] = c.message or c.reason
                pending.append({
                    "pod": pod.metadata.name,
                    "namespace": namespace,
                    "phase": pod.status.phase,
                    "conditions": conditions,
                })
                log.warning(f"Pod {pod.metadata.name} stuck in Pending: {conditions}")
        return pending


    def get_summary(self, namespace: str, restart_threshold: int = 5,
                    lookback_minutes: int = 60) -> dict:
        """
        Run all checks and return a summary dict.
        Convenience method for one-call health reporting.
        """
        nodes = self.check_nodes()
        deployments = self.check_deployments(namespace)
        oom = self.check_oom_events(namespace, lookback_minutes)
        hpa = self.check_hpa(namespace)
        restarts = self.check_restart_counts(namespace, restart_threshold)
        pending = self.check_pending_pods(namespace)

        unhealthy = (
            len([n for n in nodes if not n["ready"]]) +
            len([d for d in deployments if not d["healthy"]]) +
            len(oom) + len([h for h in hpa if h["at_max_capacity"]]) +
            len(restarts) + len(pending)
        )

        return {
            "overall_status": "DEGRADED" if unhealthy > 0 else "HEALTHY",
            "unhealthy_count": unhealthy,
            "nodes": nodes,
            "deployments": deployments,
            "oom_events": oom,
            "hpa": hpa,
            "restart_alerts": restarts,
            "pending_pods": pending,
        }
