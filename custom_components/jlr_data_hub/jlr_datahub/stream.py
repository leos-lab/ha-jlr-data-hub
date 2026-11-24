"""The live stream, kept connected in a thread.

How JLR's broker really behaves (tested against an I-Pace, November 2026), which differs from the docs:
- the MQTT client ID must be the stream username;
- only exact `account/{id}/vehicles/{vin}/{category}` topics are allowed (no wildcards below the VIN);
- one topic per SUBSCRIBE, or it answers "quota exceeded";
- MQTT 5 gives reason codes, 3.1.1 just closes the socket.
The password is a client-credentials token (about 5 minutes). The docs say the broker drops the session when the
token expires and after an hour; this reconnects with a fresh token whenever it's dropped, and logs how long each
connection lasted.
"""
from __future__ import annotations

import json
import logging
import random
import ssl
import threading
import time
from typing import Callable

import paho.mqtt.client as mqtt

from .client import STREAM_HOST, STREAM_PORT, JLRClient, JLRError
from .crypto import jwt_claims
from .signals import parse_signals

log = logging.getLogger("jlr.stream")
SESSION_CAP = 55 * 60


class Stream(threading.Thread):
    def __init__(self, client: JLRClient, on_signals: Callable[[list[dict], str], None]):
        super().__init__(daemon=True, name="jlr-stream")
        self.client = client
        self.on_signals = on_signals
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.status = {"state": "off", "detail": None, "since": time.time(), "topics": [], "messages": 0,
                       "last_message_at": None, "connections": 0, "last_connection_seconds": None}

    def _set(self, state: str, detail: str | None = None) -> None:
        if state != self.status["state"] or detail != self.status["detail"]:
            log.info("stream %s%s", state, f": {detail}" if detail else "")
            self.status.update(state=state, detail=detail, since=time.time())

    def restart(self) -> None:
        """Reconnect now (after a config change)."""
        self.wake.set()

    def run(self) -> None:
        failures = 0
        while not self.stop_event.is_set():
            cfg = self.client.config
            if not (cfg.configured and cfg.stream_configured):
                self._set("off", "Add the stream username and account ID.")
                self.wake.wait(60)
                self.wake.clear()
                continue
            started = time.time()
            ok, refused = self._session(cfg.stream_username)
            lasted = time.time() - started
            self.status["last_connection_seconds"] = round(lasted)
            if self.stop_event.is_set():
                break
            if refused:
                # Credentials or topics refused: retrying fast won't help.
                self.wake.wait(15 * 60)
                self.wake.clear()
                continue
            failures = 0 if ok and lasted > 120 else failures + 1
            wait = 0 if failures == 0 else min(300, 5 * 2 ** (failures - 1)) * random.uniform(0.8, 1.2)
            if wait:
                self._set("waiting", f"{self.status['detail'] or 'Disconnected'}; retrying in {int(wait)} s")
                self.wake.wait(wait)
                self.wake.clear()

    def _session(self, username: str) -> tuple[bool, bool]:
        """One connection. Returns (reached live, refused for good)."""
        self._set("connecting")
        try:
            token = self.client.client_credentials()
        except JLRError as e:
            self._set("error", f"Streaming token: {e}")
            return False, e.code in ("invalid_client", "unauthorized_client")
        claims = jwt_claims(token.access_token)
        categories = claims.get("categories") or ["ev", "status", "position"]
        account = (claims.get("dsas") or {}).get("account_id") or self.client.config.account_id
        vin = self.client.config.vin
        pending = [f"account/{account}/vehicles/{vin}/{c}" for c in categories]
        granted: list[str] = []
        done = threading.Event()
        result = {"live": False, "refused": False}

        m = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=username,
                        protocol=mqtt.MQTTv5, reconnect_on_failure=False)
        m.username_pw_set(username, token.access_token)
        m.tls_set(cert_reqs=ssl.CERT_REQUIRED)

        def subscribe_next(c):
            if pending:
                c.subscribe(pending[0], qos=0)

        def on_connect(c, _u, _flags, reason, _props):
            if reason.is_failure:
                result["refused"] = reason.value in (0x86, 0x87, 0x85, 0x8A)
                self._set("error", f"Login refused: {reason}")
                done.set()
                return
            self.status["connections"] += 1
            subscribe_next(c)

        def on_subscribe(c, _u, _mid, codes, _props):
            topic = pending.pop(0) if pending else "?"
            if codes and not codes[0].is_failure:
                granted.append(topic.rsplit("/", 1)[-1])
            else:
                log.warning("subscription refused for %s: %s", topic, codes[0] if codes else "?")
            if pending:
                subscribe_next(c)
            elif granted:
                result["live"] = True
                self.status["topics"] = granted
                self._set("live")
            else:
                result["refused"] = True
                self._set("error", "Every category was refused.")
                done.set()

        def on_message(_c, _u, msg):
            try:
                signals = parse_signals(json.loads(msg.payload))
            except Exception:
                log.warning("unreadable message on %s", msg.topic)
                return
            self.status["messages"] += 1
            self.status["last_message_at"] = time.time()
            if signals:
                self.on_signals(signals, msg.topic)

        def on_disconnect(_c, _u, _flags, reason, _props):
            if not done.is_set():
                self._set("dropped", f"Broker closed the connection ({reason})")
            done.set()

        m.on_connect, m.on_subscribe, m.on_message, m.on_disconnect = on_connect, on_subscribe, on_message, on_disconnect
        try:
            m.connect(STREAM_HOST, STREAM_PORT, keepalive=60, clean_start=True)
        except Exception as e:
            self._set("error", f"Couldn't connect: {e}")
            return False, False
        m.loop_start()
        deadline = time.time() + SESSION_CAP
        while not done.is_set() and not self.stop_event.is_set() and not self.wake.is_set() and time.time() < deadline:
            done.wait(5)
        if self.wake.is_set():
            self.wake.clear()
        done.set()  # our own disconnect isn't a drop
        m.disconnect()
        m.loop_stop()
        return result["live"], result["refused"]
