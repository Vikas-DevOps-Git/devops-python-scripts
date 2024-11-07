"""
Unit tests for eks_health_check.checker
Uses mock Kubernetes API objects — no cluster connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from eks_health_check.checker import EKSHealthChecker


def make_node(name, ready=True, role="core"):
    node = MagicMock()
    node.metadata.name = name
    node.metadata.labels = {"role": role}
    cond = MagicMock()
    cond.type = "Ready"
    cond.status = "True" if ready else "False"
    node.status.conditions = [cond]
    node.status.allocatable = {"cpu": "4", "memory": "8Gi"}
    return node


def make_deployment(name, desired=3, ready=3, available=3, unavailable=0):
    dep = MagicMock()
    dep.metadata.name = name
    dep.spec.replicas = desired
    dep.status.ready_replicas = ready
    dep.status.available_replicas = available
    dep.status.unavailable_replicas = unavailable
    return dep


def make_hpa(name, current=3, desired=3, max_rep=10, min_rep=2):
    hpa = MagicMock()
    hpa.metadata.name = name
    hpa.status.current_replicas = current
    hpa.status.desired_replicas = desired
    hpa.spec.max_replicas = max_rep
    hpa.spec.min_replicas = min_rep
    hpa.status.current_metrics = []
    return hpa


def make_pod(name, restart_count=0, last_reason=None):
    pod = MagicMock()
    pod.metadata.name = name
    pod.status.phase = "Running"
    cs = MagicMock()
    cs.name = "app"
    cs.restart_count = restart_count
    if last_reason:
        cs.last_state.terminated.reason = last_reason
    else:
        cs.last_state = None
    pod.status.container_statuses = [cs]
    return pod


class TestNodeChecks:
    def test_all_nodes_ready(self):
        core_v1 = MagicMock()
        core_v1.list_node.return_value.items = [
            make_node("node-1", ready=True),
            make_node("node-2", ready=True),
        ]
        checker = EKSHealthChecker(core_v1=core_v1)
        result = checker.check_nodes()
        assert len(result) == 2
        assert all(n["ready"] for n in result)

    def test_node_not_ready_flagged(self):
        core_v1 = MagicMock()
        core_v1.list_node.return_value.items = [
            make_node("node-1", ready=True),
            make_node("node-2", ready=False),
        ]
        checker = EKSHealthChecker(core_v1=core_v1)
        result = checker.check_nodes()
        not_ready = [n for n in result if not n["ready"]]
        assert len(not_ready) == 1
        assert not_ready[0]["name"] == "node-2"

    def test_no_core_v1_returns_empty(self):
        checker = EKSHealthChecker()
        result = checker.check_nodes()
        assert result == []


class TestDeploymentChecks:
    def test_healthy_deployments(self):
        apps_v1 = MagicMock()
        apps_v1.list_namespaced_deployment.return_value.items = [
            make_deployment("payment-api", desired=3, ready=3),
        ]
        checker = EKSHealthChecker(apps_v1=apps_v1)
        result = checker.check_deployments("finance")
        assert result[0]["healthy"] is True

    def test_degraded_deployment_flagged(self):
        apps_v1 = MagicMock()
        apps_v1.list_namespaced_deployment.return_value.items = [
            make_deployment("payment-api", desired=3, ready=1, unavailable=2),
        ]
        checker = EKSHealthChecker(apps_v1=apps_v1)
        result = checker.check_deployments("finance")
        assert result[0]["healthy"] is False
        assert result[0]["unavailable"] == 2


class TestHPAChecks:
    def test_hpa_at_max_flagged(self):
        autoscaling_v2 = MagicMock()
        autoscaling_v2.list_namespaced_horizontal_pod_autoscaler.return_value.items = [
            make_hpa("payment-api-hpa", current=10, max_rep=10),
        ]
        checker = EKSHealthChecker(autoscaling_v2=autoscaling_v2)
        result = checker.check_hpa("finance")
        assert result[0]["at_max_capacity"] is True

    def test_hpa_below_max_not_flagged(self):
        autoscaling_v2 = MagicMock()
        autoscaling_v2.list_namespaced_horizontal_pod_autoscaler.return_value.items = [
            make_hpa("payment-api-hpa", current=5, max_rep=20),
        ]
        checker = EKSHealthChecker(autoscaling_v2=autoscaling_v2)
        result = checker.check_hpa("finance")
        assert result[0]["at_max_capacity"] is False


class TestRestartCounts:
    def test_high_restart_count_flagged(self):
        core_v1 = MagicMock()
        core_v1.list_namespaced_pod.return_value.items = [
            make_pod("payment-api-abc", restart_count=8, last_reason="OOMKilled"),
        ]
        checker = EKSHealthChecker(core_v1=core_v1)
        result = checker.check_restart_counts("finance", threshold=5)
        assert len(result) == 1
        assert result[0]["restart_count"] == 8

    def test_low_restart_count_not_flagged(self):
        core_v1 = MagicMock()
        core_v1.list_namespaced_pod.return_value.items = [
            make_pod("payment-api-abc", restart_count=2),
        ]
        checker = EKSHealthChecker(core_v1=core_v1)
        result = checker.check_restart_counts("finance", threshold=5)
        assert len(result) == 0
