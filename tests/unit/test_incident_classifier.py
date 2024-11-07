"""
Unit tests for incident_triage.classifier
No external dependencies required.
"""
import pytest
from incident_triage.classifier import classify


class TestOOMClassification:
    def test_oom_in_title(self):
        result = classify("OOM kill on payment-api pod")
        assert result.severity == "P1"
        assert result.category == "OOM_KILL"
        assert result.team == "platform-team"

    def test_memory_limit_exceeded(self):
        result = classify("Container killed", "memory limit exceeded on finance namespace")
        assert result.severity == "P1"
        assert result.category == "OOM_KILL"


class TestNodeFailureClassification:
    def test_node_not_ready(self):
        result = classify("Node not ready", "node-1 failed health check")
        assert result.severity == "P1"
        assert result.category == "NODE_FAILURE"

    def test_disk_pressure(self):
        result = classify("DiskPressure condition on node-3")
        assert result.severity == "P1"
        assert result.category == "NODE_FAILURE"


class TestSecurityClassification:
    def test_vault_auth_failure(self):
        result = classify("Vault auth failed", "token expired for payment-api")
        assert result.severity == "P1"
        assert result.category == "SECURITY"
        assert result.team == "security-team"

    def test_403_unauthorized(self):
        result = classify("403 unauthorized on secrets endpoint")
        assert result.severity == "P1"
        assert result.category == "SECURITY"


class TestScalingClassification:
    def test_hpa_scaling(self):
        result = classify("HPA scaling failed for payment-api")
        assert result.severity == "P2"
        assert result.category == "SCALING"

    def test_insufficient_capacity(self):
        result = classify("Insufficient capacity", "no nodes available for pod scheduling")
        assert result.severity == "P2"
        assert result.category == "SCALING"


class TestCICDClassification:
    def test_deploy_failed(self):
        result = classify("Deploy failed on main branch")
        assert result.severity == "P2"
        assert result.category == "CICD_FAILURE"

    def test_argocd_sync_failed(self):
        result = classify("ArgoCD sync failed for payment-api-prod")
        assert result.severity == "P2"
        assert result.category == "CICD_FAILURE"


class TestDefaultClassification:
    def test_unknown_incident(self):
        result = classify("Something weird happened")
        assert result.severity == "P3"
        assert result.category == "GENERAL"

    def test_empty_title(self):
        result = classify("")
        assert result.severity == "P3"


class TestSlackMessageBuilding:
    def test_message_has_blocks(self):
        from incident_triage.notifier import build_slack_message
        incident = {
            "id": "INC-001",
            "title": "OOM kill on payment-api",
            "environment": "production",
            "service": "payment-api",
        }
        classification = classify("OOM kill on payment-api")
        msg = build_slack_message(incident, classification)
        assert "blocks" in msg
        assert len(msg["blocks"]) > 0

    def test_message_contains_severity(self):
        from incident_triage.notifier import build_slack_message
        incident = {"id": "INC-002", "title": "Node not ready"}
        classification = classify("Node not ready")
        msg = build_slack_message(incident, classification)
        msg_str = str(msg)
        assert "P1" in msg_str
