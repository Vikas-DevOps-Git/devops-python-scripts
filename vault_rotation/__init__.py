"""
vault_rotation — HashiCorp Vault lease renewal and secret rotation orchestrator
Connects via Kubernetes auth method (pod ServiceAccount JWT) or static token.
Renews leases expiring within threshold, logs all rotation events to file.
"""
__version__ = "1.2.0"
__author__ = "Vikas Dhamija"
