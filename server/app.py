"""jlr-server: holds the one JLR Data Hub credential an account allows and shares the car's data with any number of
clients (Home Assistant instances, apps, scripts). It keeps the sign-in alive, stays on the live stream, polls the REST
API as a backstop, and keeps a history so trips can show the battery they used.

Everything under /api needs  Authorization: Bearer <API_TOKEN>.

  GET  /api/status            sign-in, stream and polling state
  GET  /api/certificate       the PEM to upload in the JLR portal
  PUT  /api/config            {clientId, vin, streamUsername, accountId}
  POST /api/signin            start Device Code sign-in -> {userCode, verificationUri, verificationUriComplete}
  GET  /api/signin            its progress
  POST /api/signout
  GET  /api/state             latest signals (the shape the app's SignalParser reads)
  POST /api/refresh           fetch from JLR now, then /api/state
  GET  /api/journeys?days=30  trips, with socStart/socEnd/socUsed where history allows
  GET  /api/charges?days=30   charging sessions
  GET  /api/history?path=…&days=7
  GET  /api/alerts?days=365       warnings raised from the car's reports (12 V battery, charging, fault codes)
  POST /api/push/register         {token, environment} from the app, for alert pushes
  POST /api/alerts/test           push a test alert to every registered device
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import alerts as alerting
from jlr_datahub import Config, JLRClient, JLRError, SignInRequired, Stream
from store import Store, iso

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("jlr")

DATA = Path(os.environ.get("DATA_DIR", "/data"))
API_TOKEN = os.environ.get("API_TOKEN", "")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "600"))
JOURNEY_SECONDS = int(os.environ.get("JOURNEY_SECONDS", "1800"))

client = JLRClient(DATA / "jlr")
store = Store(os.environ["DATABASE_URL"])


app = FastAPI(title="JLR server", docs_url=None, redoc_url=None)

poll_state = {"last_snapshot": None, "last_journeys": None, "last_error": None}
# Optional: Apple push for your own iOS app (an APNs .p8 key, its team ID and the app's bundle ID). Off by default.
apns = alerting.APNs(Path(os.environ.get("APNS_DIR", "/apns")), os.environ.get("APNS_TEAM_ID", ""),
                     os.environ.get("APNS_TOPIC", ""))
alert_lock = threading.Lock()


def devices() -> list[dict]:
    return json.loads(store.get_meta("push_devices") or "[]")


def push(alert: dict) -> list[str]:
    """Sends an alert to every registered device; forgets devices Apple says are gone."""
    if not apns.enabled:
        return ["push off: no APNs key"]
    results, keep = [], []
    for d in devices():
        try:
            status, reason = apns.send(d, alert["title"], alert["body"])
        except Exception as e:
            status, reason = 0, str(e)
        results.append(f"{d['token'][:8]}…: {status} {reason}".strip())
        if status not in (400, 410) or reason not in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
            keep.append(d)
    store.set_meta("push_devices", json.dumps(keep))
    log.info("pushed %r: %s", alert["title"], "; ".join(results))
    return results


def record(signals: list[dict], source: str) -> None:
    """Stores signals, then raises or clears alerts and pushes new ones."""
    if not store.add_signals(signals, source):
        return
    with alert_lock:
        opened = alerting.diagnostic_alerts(store, signals) + alerting.evaluate(store)
    for alert in opened:
        push(alert)
signin_state: dict = {"state": "idle"}
signin_cancel = threading.Event()
wake_poller = threading.Event()


def on_stream_signals(signals: list[dict], topic: str) -> None:
    record(signals, "stream")


stream = Stream(client, on_stream_signals)


def require_token(request: Request) -> None:
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not API_TOKEN or not hmac.compare_digest(given.encode(), API_TOKEN.encode()):
        raise HTTPException(401, "Bad or missing token")


auth = [Depends(require_token)]


# MARK: Workers

def fetch_snapshot() -> None:
    signals, errors = client.snapshot()
    record(signals, "rest")
    poll_state.update(last_snapshot=time.time(), last_error="; ".join(errors.values()) or None)


def fetch_journeys() -> None:
    # First run: the last 90 days, a month at a time. After that, the last week.
    now = time.time()
    spans = [(now - 7 * 86400, now)] if store.get_meta("journeys_backfilled") else \
        [(now - (d + 30) * 86400, now - d * 86400) for d in (0, 30, 60)]
    for start, end in spans:
        store.add_journeys(client.journeys(start, end))
    store.set_meta("journeys_backfilled", "1")
    poll_state["last_journeys"] = time.time()


def poller() -> None:
    next_journeys = 0.0
    while True:
        if client.config.configured and client.signed_in:
            try:
                fetch_snapshot()
                if time.time() >= next_journeys:
                    fetch_journeys()
                    next_journeys = time.time() + JOURNEY_SECONDS
            except SignInRequired as e:
                poll_state["last_error"] = str(e)
            except Exception as e:  # keep polling whatever happens
                log.exception("poll failed")
                poll_state["last_error"] = str(e)
        wake_poller.wait(POLL_SECONDS)
        wake_poller.clear()


threading.Thread(target=poller, daemon=True, name="poller").start()
stream.start()


# MARK: API

class ConfigBody(BaseModel):
    clientId: str
    vin: str
    streamUsername: str = ""
    accountId: str = ""


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/status", dependencies=auth)
def status():
    t = client.tokens
    c = client.config
    return {
        "configured": c.configured,
        "config": {"clientId": c.client_id, "vin": c.vin, "streamUsername": c.stream_username, "accountId": c.account_id},
        "signedIn": client.signed_in,
        "sessionExpiresAt": iso(t.session_expires_at) if t else None,
        "stream": {**stream.status, "since": iso(stream.status["since"]),
                   "last_message_at": iso(stream.status["last_message_at"])},
        "lastSnapshot": iso(poll_state["last_snapshot"]),
        "lastJourneys": iso(poll_state["last_journeys"]),
        "lastError": poll_state["last_error"],
        "rateLimit": client.rate_limit,
        "signin": signin_state,
    }


@app.get("/api/certificate", dependencies=auth, response_class=PlainTextResponse)
def certificate():
    return client.certificate_pem()


@app.put("/api/config", dependencies=auth)
def put_config(body: ConfigBody):
    vin = body.vin.strip().upper()
    if len(vin) != 17:
        raise HTTPException(400, "A VIN is 17 characters.")
    client.save_config(Config(body.clientId.strip(), vin, body.streamUsername.strip(), body.accountId.strip()))
    stream.restart()
    return status()


@app.post("/api/signin", dependencies=auth)
def signin():
    if not client.config.configured:
        raise HTTPException(400, "Save the client ID and VIN first.")
    signin_cancel.set()
    try:
        pending = client.start_device_authorization()
    except JLRError as e:
        raise HTTPException(400, str(e))
    signin_cancel.clear()
    signin_state.clear()
    signin_state.update(state="pending", userCode=pending.user_code, verificationUri=pending.verification_uri,
                        verificationUriComplete=pending.verification_uri_complete, expiresAt=iso(pending.expires_at))

    def wait():
        try:
            client.poll_device_token(pending, should_stop=signin_cancel.is_set)
            signin_state.update(state="done")
            wake_poller.set()
            stream.restart()
        except JLRError as e:
            if not signin_cancel.is_set():
                signin_state.update(state="error", error=str(e))

    threading.Thread(target=wait, daemon=True, name="signin").start()
    return signin_state


@app.get("/api/signin", dependencies=auth)
def signin_progress():
    return signin_state


@app.post("/api/signout", dependencies=auth)
def signout():
    signin_cancel.set()
    client.save_tokens(None)
    return status()


@app.get("/api/state", dependencies=auth)
def state():
    return store.state()


@app.post("/api/refresh", dependencies=auth)
def refresh():
    try:
        fetch_snapshot()
    except SignInRequired as e:
        raise HTTPException(409, str(e))
    except JLRError as e:
        raise HTTPException(502, str(e))
    return store.state()


@app.get("/api/journeys", dependencies=auth)
def journeys(days: float = 30):
    now = time.time()
    return {"items": list(reversed(store.journeys(now - days * 86400, now)))}


@app.get("/api/charges", dependencies=auth)
def charges(days: float = 30):
    now = time.time()
    return {"items": list(reversed(store.charges(now - days * 86400, now)))}


class PushDevice(BaseModel):
    token: str
    environment: str = "development"


@app.get("/api/alerts", dependencies=auth)
def get_alerts(days: float = 365):
    return {"items": store.alerts(time.time() - days * 86400), "push": apns.enabled, "devices": len(devices())}


@app.post("/api/push/register", dependencies=auth)
def register_push(body: PushDevice):
    token = body.token.strip().lower()
    if not token or len(token) > 200 or any(c not in "0123456789abcdef" for c in token):
        raise HTTPException(400, "Not a device token.")
    others = [d for d in devices() if d["token"] != token]
    store.set_meta("push_devices", json.dumps(others + [{"token": token, "environment": body.environment}]))
    return {"devices": len(others) + 1, "push": apns.enabled}


@app.post("/api/alerts/test", dependencies=auth)
def test_alert():
    return {"results": push({"title": "JLR alerts are on", "body": "Battery warnings from the car will arrive here."})}


@app.get("/api/history", dependencies=auth)
def history(path: str, days: float = 7):
    now = time.time()
    return {"path": path, "points": [{"t": iso(t), "v": v} for t, v in store.history(path, now - days * 86400, now)]}
