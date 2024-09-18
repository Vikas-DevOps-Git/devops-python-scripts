"""
client.py — Vault client authentication and lease operations
Supports: Kubernetes auth (in-cluster), token auth (local dev), AppRole
"""
import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

# Vault K8s ServiceAccount JWT path
K8S_JWT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"


class VaultClient:
    """
    Thin wrapper around hvac.Client with authentication helpers.
    """

    def __init__(self, addr: str, namespace: str = ""):
        import hvac
        self._hvac = hvac.Client(url=addr, namespace=namespace or None)
        self.addr = addr

    def auth_kubernetes(self, role: str, jwt_path: str = K8S_JWT_PATH) -> str:
        """Authenticate using Kubernetes ServiceAccount JWT."""
        with open(jwt_path) as f:
            jwt = f.read().strip()
        resp = self._hvac.auth.kubernetes.login(role=role, jwt=jwt)
        self._hvac.token = resp["auth"]["client_token"]
        token_ttl = resp["auth"]["lease_duration"]
        log.info(f"Authenticated via Kubernetes auth, role={role}, ttl={token_ttl}s")
        return self._hvac.token

    def auth_token(self, token: str):
        """Authenticate with a static token (development only)."""
        self._hvac.token = token
        log.info("Using static token authentication")

    def auth_approle(self, role_id: str, secret_id: str) -> str:
        """Authenticate using AppRole method."""
        resp = self._hvac.auth.approle.login(
            role_id=role_id, secret_id=secret_id
        )
        self._hvac.token = resp["auth"]["client_token"]
        log.info("Authenticated via AppRole")
        return self._hvac.token

    def is_authenticated(self) -> bool:
        try:
            return self._hvac.is_authenticated()
        except Exception:
            return False

    def list_leases(self, prefix: str) -> list:
        """List lease IDs under a path prefix."""
        try:
            resp = self._hvac.sys.list_leases(prefix=prefix)
            keys = resp.get("data", {}).get("keys", [])
            return [f"{prefix}{k}" for k in keys if not k.endswith("/")]
        except Exception as e:
            log.warning(f"list_leases({prefix}) failed: {e}")
            return []

    def lookup_lease_ttl(self, lease_id: str) -> int:
        """Return remaining TTL in seconds for a lease."""
        try:
            resp = self._hvac.sys.read_lease(lease_id=lease_id)
            return resp.get("data", {}).get("ttl", 99999)
        except Exception as e:
            log.debug(f"lookup_lease_ttl({lease_id}) failed: {e}")
            return 99999

    def renew_lease(self, lease_id: str, increment: int = 3600) -> dict:
        """Renew a lease by increment seconds."""
        try:
            resp = self._hvac.sys.renew_lease(
                lease_id=lease_id, increment=increment
            )
            new_ttl = resp.get("lease_duration", 0)
            log.info(f"Renewed lease {lease_id} — new TTL: {new_ttl}s")
            return {"lease_id": lease_id, "status": "renewed", "new_ttl": new_ttl}
        except Exception as e:
            log.error(f"Failed to renew lease {lease_id}: {e}")
            return {"lease_id": lease_id, "status": "failed", "error": str(e)}

    def revoke_lease(self, lease_id: str) -> bool:
        """Revoke a lease explicitly."""
        try:
            self._hvac.sys.revoke_lease(lease_id=lease_id)
            log.info(f"Revoked lease {lease_id}")
            return True
        except Exception as e:
            log.error(f"Failed to revoke lease {lease_id}: {e}")
            return False

    def renew_self_token(self, increment: int = 3600):
        """Renew the current client token."""
        try:
            resp = self._hvac.auth.token.renew_self(increment=increment)
            ttl = resp.get("auth", {}).get("lease_duration", 0)
            log.info(f"Renewed self token — new TTL: {ttl}s")
            return ttl
        except Exception as e:
            log.error(f"Failed to renew self token: {e}")
            return 0
