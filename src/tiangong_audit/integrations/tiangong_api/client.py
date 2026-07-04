"""Small Supabase HTTP client for the Tiangong platform."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import requests


class TiangongAPIError(Exception):
    """Base exception for Tiangong API errors."""


class TiangongAuthError(TiangongAPIError):
    """Raised when required Supabase credentials are missing."""


class TiangongWriteDisabledError(TiangongAPIError):
    """Raised when a caller attempts a platform write without enabling writes."""


AccountRole = Literal["admin", "member"]


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def _load_local_env(path: Path) -> None:
    """Load simple KEY=VALUE settings without overriding the shell environment."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.removeprefix("export ").partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def _looks_like_expired_auth(response: Any) -> bool:
    if response.status_code == 401:
        return True
    if response.status_code != 403:
        return False
    text = response.text.lower()
    return "bad_jwt" in text or "jwt" in text and "expired" in text


class TiangongAPIClient:
    """Call the Supabase REST, RPC, and Edge Function endpoints used by Tiangong."""

    def __init__(
        self,
        supabase_url: str | None = None,
        publishable_key: str | None = None,
        access_token: str | None = None,
        email: str | None = None,
        password: str | None = None,
        *,
        account_role: AccountRole | str | None = None,
        timeout: float = 30,
        session: Any | None = None,
        allow_writes: bool | None = None,
    ):
        _load_local_env(Path.cwd() / ".env")
        self.account_role = self._resolve_account_role(account_role)
        self.supabase_url = (
            os.getenv("TIANGONG_SUPABASE_URL", "") if supabase_url is None else supabase_url
        ).rstrip("/")
        self.publishable_key = (
            os.getenv("TIANGONG_SUPABASE_ANON_KEY", "")
            if publishable_key is None
            else publishable_key
        )
        self.access_token = self._credential(
            "ACCESS_TOKEN", "TIANGONG_SUPABASE_ACCESS_TOKEN", access_token
        )
        self.email = self._credential("EMAIL", "TIANGONG_SUPABASE_EMAIL", email)
        self.password = self._credential("PASSWORD", "TIANGONG_SUPABASE_PASSWORD", password)
        self.timeout = timeout
        self.session = session or requests.Session()
        self.allow_writes = (
            _env_flag("TIANGONG_API_ALLOW_WRITES")
            if allow_writes is None
            else allow_writes
        )

        missing = [
            name
            for name, value in (
                ("TIANGONG_SUPABASE_URL", self.supabase_url),
                ("TIANGONG_SUPABASE_ANON_KEY", self.publishable_key),
            )
            if not value
        ]
        if not self.access_token and not self._can_login():
            role_prefix = (
                f"TIANGONG_{self.account_role.upper()}_"
                if self.account_role is not None
                else ""
            )
            missing.append(
                f"{role_prefix}ACCESS_TOKEN or both "
                f"{role_prefix}EMAIL/{role_prefix}PASSWORD"
            )
        if missing:
            raise TiangongAuthError(
                "Missing platform configuration: " + ", ".join(missing)
            )

    @staticmethod
    def _resolve_account_role(account_role: AccountRole | str | None) -> AccountRole | None:
        value = (
            os.getenv("TIANGONG_ACTIVE_ACCOUNT", "")
            if account_role is None
            else account_role
        )
        normalized = value.strip().lower() if isinstance(value, str) else ""
        if not normalized:
            return None
        if normalized not in {"admin", "member"}:
            raise TiangongAuthError(
                "Invalid account role. Use admin or member."
            )
        return normalized  # type: ignore[return-value]

    def _credential(
        self,
        suffix: str,
        legacy_name: str,
        explicit_value: str | None,
    ) -> str:
        if explicit_value is not None:
            return explicit_value
        if self.account_role is not None:
            prefix = f"TIANGONG_{self.account_role.upper()}"
            return (
                os.getenv(f"{prefix}_{suffix}", "")
                or os.getenv(f"{prefix}_SUPABASE_{suffix}", "")
                or os.getenv(legacy_name, "")
            )
        return os.getenv(legacy_name, "")

    def _can_login(self) -> bool:
        return bool(self.email and self.password)

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _login(self) -> None:
        """Exchange the dedicated review account credentials for a fresh token."""
        if not self._can_login():
            raise TiangongAuthError(
                "The access token expired and no review account credentials are configured."
            )
        url = f"{self.supabase_url}/auth/v1/token?grant_type=password"
        try:
            response = self.session.request(
                "POST",
                url,
                json={"email": self.email, "password": self.password},
                headers={
                    "apikey": self.publishable_key,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise TiangongAuthError(f"Platform login failed: {error}") from error

        if not 200 <= response.status_code < 300:
            raise TiangongAuthError(
                f"Platform login returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        try:
            result = response.json()
        except (json.JSONDecodeError, ValueError) as error:
            raise TiangongAuthError("Platform login returned invalid JSON") from error
        access_token = result.get("access_token") if isinstance(result, dict) else None
        if not access_token:
            raise TiangongAuthError("Platform login response did not contain an access token")
        self.access_token = access_token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.supabase_url}/{path.lstrip('/')}"
        if not self.access_token:
            self._login()
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise TiangongAPIError(f"Platform request failed: {error}") from error

        if _looks_like_expired_auth(response) and self._can_login():
            self._login()
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=payload,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except requests.RequestException as error:
                raise TiangongAPIError(f"Platform request failed: {error}") from error

        if not 200 <= response.status_code < 300:
            raise TiangongAPIError(
                f"Platform returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as error:
            raise TiangongAPIError("Platform returned invalid JSON") from error

    def rpc(self, name: str, payload: dict[str, Any]) -> Any:
        """Call a read-only Supabase RPC."""
        return self._request("POST", f"rest/v1/rpc/{name}", payload=payload)

    def command(self, name: str, payload: dict[str, Any]) -> Any:
        """Call a write-capable Supabase RPC after writes are explicitly enabled."""
        if not self.allow_writes:
            raise TiangongWriteDisabledError(
                "Platform writes are disabled. Enable writes only immediately "
                "before a confirmed write operation."
            )
        return self._request("POST", f"rest/v1/rpc/{name}", payload=payload)

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read rows from a Supabase PostgREST table."""
        params: dict[str, Any] = {"select": columns}
        params.update(filters or {})
        if limit is not None:
            params["limit"] = limit
        result = self._request("GET", f"rest/v1/{table}", params=params)
        if not isinstance(result, list):
            raise TiangongAPIError(f"Expected a list response from table {table}")
        return result

    def invoke_function(self, name: str, payload: dict[str, Any]) -> Any:
        """Invoke a platform Edge Function after writes are explicitly enabled."""
        if not self.allow_writes:
            raise TiangongWriteDisabledError(
                "Platform writes are disabled. Set TIANGONG_API_ALLOW_WRITES=true "
                "only immediately before a confirmed write operation."
            )
        return self._request("POST", f"functions/v1/{name}", payload=payload)

    def upload_external_doc(
        self,
        object_name: str,
        path: str | Path,
        content_type: str,
    ) -> Any:
        """Upload one file to the external_docs storage bucket after writes are enabled."""
        if not self.allow_writes:
            raise TiangongWriteDisabledError(
                "Platform writes are disabled. Set TIANGONG_API_ALLOW_WRITES=true "
                "only immediately before a confirmed write operation."
            )
        if not self.access_token:
            self._login()
        url = f"{self.supabase_url}/storage/v1/object/external_docs/{object_name}"
        headers = {
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": content_type,
        }
        try:
            with Path(path).open("rb") as handle:
                response = self.session.request(
                    "POST",
                    url,
                    data=handle,
                    headers=headers,
                    timeout=self.timeout,
                )
        except requests.RequestException as error:
            raise TiangongAPIError(f"Platform storage upload failed: {error}") from error
        if not 200 <= response.status_code < 300:
            raise TiangongAPIError(
                f"Platform storage upload returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError):
            return {"status_code": response.status_code, "text": response.text}
