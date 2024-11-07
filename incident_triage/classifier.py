"""
classifier.py — incident classification engine
Maps incident text to severity, category, runbook, and owning team.
"""
from dataclasses import dataclass
from typing import Optional

RUNBOOK_BASE = "https://github.com/Vikas-DevOps-Git/kubernetes-platform-labs/blob/main/docs"

@dataclass
class Classification:
    severity: str
    category: str
    runbook_url: str
    team: str
    matched_keyword: Optional[str] = None


# Rules are evaluated in order — first match wins
CLASSIFICATION_RULES = [
    {
        "keywords": ["oom", "oomkill", "out of memory", "memory limit exceeded",
                     "container killed", "evicted"],
        "severity": "P1",
        "category": "OOM_KILL",
        "runbook": f"{RUNBOOK_BASE}/blue-green-runbook.md#oom-kills",
        "team": "platform-team",
    },
    {
        "keywords": ["node not ready", "node failure", "nodepressure",
                     "diskpressure", "memorypressure", "node unreachable"],
        "severity": "P1",
        "category": "NODE_FAILURE",
        "runbook": f"{RUNBOOK_BASE}/blue-green-runbook.md#node-failures",
        "team": "platform-team",
    },
    {
        "keywords": ["vault", "secret", "auth failed", "token expired",
                     "permission denied", "403", "unauthorized"],
        "severity": "P1",
        "category": "SECURITY",
        "runbook": f"{RUNBOOK_BASE}/argocd-setup.md#vault",
        "team": "security-team",
    },
    {
        "keywords": ["payment", "transaction", "gateway", "checkout",
                     "payment failed", "payment timeout"],
        "severity": "P1",
        "category": "PAYMENT_FAILURE",
        "runbook": f"{RUNBOOK_BASE}/blue-green-runbook.md",
        "team": "payments-team",
    },
    {
        "keywords": ["eks scaling", "hpa", "autoscaler", "scaling failed",
                     "insufficient capacity", "no nodes available"],
        "severity": "P2",
        "category": "SCALING",
        "runbook": f"{RUNBOOK_BASE}/hpa-tuning-guide.md",
        "team": "platform-team",
    },
    {
        "keywords": ["split brain", "elasticsearch", "elk", "kibana",
                     "logstash", "index", "shard"],
        "severity": "P2",
        "category": "OBSERVABILITY",
        "runbook": f"{RUNBOOK_BASE}/argocd-setup.md",
        "team": "observability-team",
    },
    {
        "keywords": ["pipeline", "github actions", "deploy failed", "build failed",
                     "rollback", "argocd", "sync failed", "image pull"],
        "severity": "P2",
        "category": "CICD_FAILURE",
        "runbook": f"{RUNBOOK_BASE}/argocd-setup.md",
        "team": "platform-team",
    },
    {
        "keywords": ["database", "db connection", "postgres", "mysql",
                     "connection pool", "query timeout", "deadlock"],
        "severity": "P2",
        "category": "DATABASE",
        "runbook": f"{RUNBOOK_BASE}/blue-green-runbook.md",
        "team": "dba-team",
    },
    {
        "keywords": ["high latency", "slow response", "timeout", "p99",
                     "slo breach", "error rate", "5xx"],
        "severity": "P2",
        "category": "PERFORMANCE",
        "runbook": f"{RUNBOOK_BASE}/hpa-tuning-guide.md",
        "team": "platform-team",
    },
]

SEVERITY_EMOJI = {
    "P1": "🔴",
    "P2": "🟠",
    "P3": "🟡",
    "P4": "🟢",
}

DEFAULT_CLASSIFICATION = Classification(
    severity="P3",
    category="GENERAL",
    runbook_url=f"{RUNBOOK_BASE}/blue-green-runbook.md",
    team="platform-team",
)


def classify(title: str, description: str = "", body: str = "") -> Classification:
    """
    Classify an incident based on text content.
    Returns a Classification with severity, category, runbook, and team.
    """
    text = " ".join([title, description, body]).lower()

    for rule in CLASSIFICATION_RULES:
        for kw in rule["keywords"]:
            if kw in text:
                return Classification(
                    severity=rule["severity"],
                    category=rule["category"],
                    runbook_url=rule["runbook"],
                    team=rule["team"],
                    matched_keyword=kw,
                )

    return DEFAULT_CLASSIFICATION
