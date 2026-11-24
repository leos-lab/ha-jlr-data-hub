"""OAuth flows and DPoP-bound REST calls for one owner client and car. Synchronous (httpx), thread-safe for refresh."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .crypto import DPoP, RSAKey, client_assertion, jwt_claims, pkce
from .signals import parse_signals

AUTH_BASE = "https://auth.jlr-vcdp.com/realms/public"
API_BASE = "https://data.jlr-vcdp.com"
STREAM_HOST = "stream-data.jlr-vcdp.com"
STREAM_PORT = 8883
TOKEN_URL = f"{AUTH_BASE}/protocol/openid-connect/token"
DEVICE_URL = f"{AUTH_BASE}/protocol/openid-connect/auth/device"
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


class JLRError(Exception):
    def __init__(self, message: str, *, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


class SignInRequired(JLRError):
    def __init__(self, message: str = "Sign in again."):
        super().__init__(message, code="sign_in_required")


@dataclass
class Config:
    client_id: str = ""
    vin: str = ""
    stream_username: str = ""
    account_id: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.client_id and len(self.vin) == 17)

    @property
    def stream_configured(self) -> bool:
        return bool(self.stream_username and self.account_id)


@dataclass
class Tokens:
    access_token: str
    expires_at: float
    refresh_token: str | None = None
    refresh_expires_at: float | None = None
    token_type: str = "DPoP"

    @classmethod
    def from_response(cls, body: dict, now: float | None = None) -> "Tokens":
        now = now or time.time()
        expires = body.get("expires_in") or (jwt_claims(body["access_token"]).get("exp", now + 300) - now)
        rexp = body.get("refresh_expires_in")
        return cls(access_token=body["access_token"], expires_at=now + float(expires),
                   refresh_token=body.get("refresh_token"),
                   refresh_expires_at=(now + float(rexp)) if rexp else None,
                   token_type=body.get("token_type", "DPoP"))

    def access_valid(self, margin: float = 60) -> bool:
        return self.expires_at - time.time() > margin

    def can_refresh(self) -> bool:
        if not self.refresh_token:
            return False
        return self.refresh_expires_at is None or self.refresh_expires_at - time.time() > 30

    @property
    def session_expires_at(self) -> float | None:
        return self.refresh_expires_at if self.refresh_token else self.expires_at


@dataclass
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None
    expires_at: float
    interval: float
    code_verifier: str = field(repr=False)


class JLRClient:
    """Keys, config and tokens live in `data_dir` (0600 files)."""

    def __init__(self, data_dir: Path, user_agent: str = "jlr-datahub-server", certificate_name: str = "JLR server (N100)"):
        self.dir = data_dir
        self.certificate_name = certificate_name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.client_key = RSAKey.load_or_create(self.dir / "client-key.pem")
        self.dpop = DPoP(RSAKey.load_or_create(self.dir / "dpop-key.pem"))
        self.http = httpx.Client(timeout=30, headers={"User-Agent": user_agent})
        self._lock = threading.RLock()
        self.config = self._load_config()
        self.tokens = self._load_tokens()
        self.rate_limit: dict = {}

    # MARK: Storage

    def _write(self, name: str, data: str) -> None:
        path = self.dir / name
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(data)
        tmp.replace(path)

    def _load_config(self) -> Config:
        try:
            return Config(**json.loads((self.dir / "config.json").read_text()))
        except Exception:
            return Config()

    def save_config(self, config: Config) -> None:
        with self._lock:
            if config.client_id != self.config.client_id:
                self.save_tokens(None)
            self.config = config
            self._write("config.json", json.dumps(asdict(config), indent=2))

    def _load_tokens(self) -> Tokens | None:
        try:
            return Tokens(**json.loads((self.dir / "tokens.json").read_text()))
        except Exception:
            return None

    def save_tokens(self, tokens: Tokens | None) -> None:
        with self._lock:
            self.tokens = tokens
            if tokens is None:
                (self.dir / "tokens.json").unlink(missing_ok=True)
            else:
                self._write("tokens.json", json.dumps(asdict(tokens)))

    def certificate_pem(self) -> str:
        return self.client_key.certificate_pem(self.certificate_name)

    @property
    def signed_in(self) -> bool:
        t = self.tokens
        return bool(t and (t.access_valid(0) or t.can_refresh()))

    # MARK: Token endpoint

    def _assertion(self) -> list[tuple[str, str]]:
        return [("client_assertion_type", ASSERTION_TYPE),
                ("client_assertion", client_assertion(self.config.client_id, TOKEN_URL, self.client_key))]

    def _post(self, url: str, fields: list[tuple[str, str]], dpop: bool) -> httpx.Response:
        for attempt in range(2):
            headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
            if dpop:
                headers["DPoP"] = self.dpop.proof("POST", url)
            r = self.http.post(url, content=urlencode(fields), headers=headers)
            changed = self.dpop.note_nonce(url, r.headers)
            if attempt == 0 and dpop and changed and _oauth_error(r) == "use_dpop_nonce":
                continue
            return r
        return r

    @staticmethod
    def _raise(r: httpx.Response) -> None:
        try:
            body = r.json()
        except Exception:
            body = {}
        if "error" in body:
            raise JLRError(body.get("error_description") or body["error"], code=body["error"], status=r.status_code)
        title = " ".join(str(body.get(k)) for k in ("title", "detail") if body.get(k))
        raise JLRError(title or f"HTTP {r.status_code}: {r.text[:200]}", status=r.status_code)

    def start_device_authorization(self) -> DeviceAuthorization:
        verifier, challenge = pkce()
        fields = [("client_id", self.config.client_id), ("response_type", "device_code"),
                  ("code_challenge", challenge), ("code_challenge_method", "S256")]
        r = self._post(DEVICE_URL, fields, dpop=False)
        if r.status_code == 401 or _oauth_error(r) == "invalid_client":
            r = self._post(DEVICE_URL, fields + self._assertion(), dpop=False)
        if r.status_code != 200:
            self._raise(r)
        b = r.json()
        return DeviceAuthorization(b["device_code"], b["user_code"], b["verification_uri"],
                                   b.get("verification_uri_complete"), time.time() + float(b["expires_in"]),
                                   max(float(b.get("interval", 5)), 1), verifier)

    def poll_device_token(self, auth: DeviceAuthorization, should_stop=lambda: False) -> Tokens:
        interval = auth.interval
        while not should_stop():
            time.sleep(interval)
            if time.time() > auth.expires_at:
                raise JLRError("The sign-in code expired.", code="expired_token")
            fields = [("grant_type", "urn:ietf:params:oauth:grant-type:device_code"),
                      ("client_id", self.config.client_id), ("device_code", auth.device_code),
                      ("code_verifier", auth.code_verifier)] + self._assertion()
            r = self._post(TOKEN_URL, fields, dpop=True)
            if r.status_code == 200:
                tokens = Tokens.from_response(r.json())
                self.save_tokens(tokens)
                return tokens
            err = _oauth_error(r)
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 5
                continue
            if err == "access_denied":
                raise JLRError("Sign-in was declined.", code=err)
            self._raise(r)
        raise JLRError("Sign-in cancelled.", code="cancelled")

    def access_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            t = self.tokens
            if not t:
                raise SignInRequired()
            if not force_refresh and t.access_valid():
                return t.access_token
            if not t.can_refresh():
                self.save_tokens(None)
                raise SignInRequired("The sign-in has lapsed. Sign in again.")
            fields = [("grant_type", "refresh_token"), ("client_id", self.config.client_id),
                      ("refresh_token", t.refresh_token)] + self._assertion()
            r = self._post(TOKEN_URL, fields, dpop=True)
            if r.status_code != 200:
                if _oauth_error(r) == "invalid_grant":
                    self.save_tokens(None)
                    raise SignInRequired("The sign-in has lapsed. Sign in again.")
                self._raise(r)
            fresh = Tokens.from_response(r.json())
            if not fresh.refresh_token:
                fresh.refresh_token, fresh.refresh_expires_at = t.refresh_token, t.refresh_expires_at
            self.save_tokens(fresh)
            return fresh.access_token

    def client_credentials(self) -> Tokens:
        """The MQTT password: no DPoP, no refresh token, about 5 minutes."""
        fields = [("grant_type", "client_credentials"), ("client_id", self.config.client_id)] + self._assertion()
        r = self._post(TOKEN_URL, fields, dpop=False)
        if r.status_code != 200:
            self._raise(r)
        return Tokens.from_response(r.json())

    # MARK: REST

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        url = f"{API_BASE}/{path.lstrip('/')}"
        retried_nonce = retried_token = False
        while True:
            token = self.access_token()
            r = self.http.get(url, params=params, headers={
                "Authorization": f"DPoP {token}", "DPoP": self.dpop.proof("GET", url, token),
                "Accept": "application/json"})
            self.rate_limit = {k: r.headers.get(f"X-RateLimit-{k}") for k in ("Limit", "Remaining", "Reset")}
            changed = self.dpop.note_nonce(url, r.headers)
            if r.status_code == 401:
                if not retried_nonce and (changed or "use_dpop_nonce" in r.headers.get("WWW-Authenticate", "")):
                    retried_nonce = True
                    continue
                if not retried_token:
                    retried_token = True
                    self.access_token(force_refresh=True)
                    continue
            if r.status_code == 429:
                raise JLRError(f"Rate limited; retry after {r.headers.get('Retry-After', '?')} s", status=429)
            if r.status_code >= 400:
                self._raise(r)
            return r

    def snapshot(self) -> tuple[list[dict], dict[str, str]]:
        """Signals from /status, /ev and /location. Returns (signals, errors by resource); 403/404 are skipped."""
        signals: list[dict] = []
        errors: dict[str, str] = {}
        for resource in ("status", "ev", "location"):
            try:
                signals += parse_signals(self.get(f"v1/vehicles/{self.config.vin}/{resource}").json())
            except SignInRequired:
                raise
            except JLRError as e:
                if e.status not in (403, 404):
                    errors[resource] = str(e)
        if not signals and errors:
            raise JLRError("; ".join(f"{k}: {v}" for k, v in errors.items()))
        return signals, errors

    def journeys(self, start: float, end: float) -> list[dict]:
        out: list[dict] = []
        page = 0
        while page < 50:
            body = self.get(f"v1/vehicles/{self.config.vin}/journeys", {
                "page": page, "size": 100,
                "from": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start)),
                "to": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end))}).json()
            items = body.get("items", [])
            out += items
            page += 1
            if not items or page >= (body.get("page") or {}).get("totalPages", 1):
                return out
        return out


def _oauth_error(r: httpx.Response) -> str | None:
    try:
        return r.json().get("error")
    except Exception:
        return None
