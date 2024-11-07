"""
incident_triage — PagerDuty + Slack incident triage dispatcher
Classifies incidents by keyword, posts formatted Slack alerts with
runbook links, severity labels, and team routing.
Can run as a CLI one-shot or as a persistent HTTP webhook server.
"""
__version__ = "1.1.0"
__author__ = "Vikas Dhamija"
