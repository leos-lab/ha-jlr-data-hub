"""Postgres: the latest value of every signal, a history of the ones that
matter, trips and alerts. Plus the analytics built from them (battery used per trip, charging sessions).

Times are timestamptz and values JSONB, so the tables read well in any Postgres browser.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time

import psycopg
from psycopg.types.json import Jsonb

from jlr_datahub.signals import CHARGING_STATUS, ODOMETER, SOC, number, parse_time

log = logging.getLogger("jlr.store")

# Always kept in history, even when unchanged, so every report is a data point.
KEY_PATHS = set(SOC) | {
    "Vehicle.Powertrain.TractionBattery.Range", ODOMETER, CHARGING_STATUS,
    "Vehicle.Powertrain.TractionBattery.Charging.ChargingPort.AnyPosition.IsChargingCableConnected",
    "Vehicle.Powertrain.TractionBattery.Charging.Session.Energy",
    "Vehicle.CurrentLocation.Latitude", "Vehicle.CurrentLocation.Longitude",
    "Vehicle.Body.Door.Lock.Status", "Vehicle.System.DriveCycle.Status",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS latest (path text PRIMARY KEY, value jsonb, unit text, reported timestamptz,
                                   received timestamptz);
CREATE TABLE IF NOT EXISTS history (path text, value jsonb, unit text, reported timestamptz, received timestamptz,
                                    source text, PRIMARY KEY (path, reported));
CREATE INDEX IF NOT EXISTS history_reported ON history (reported);
CREATE TABLE IF NOT EXISTS journeys (id text PRIMARY KEY, started timestamptz, ended timestamptz, body jsonb);
CREATE INDEX IF NOT EXISTS journeys_started ON journeys (started);
CREATE TABLE IF NOT EXISTS alerts (id bigserial PRIMARY KEY, key text, title text, body text, severity text,
                                   started timestamptz, cleared timestamptz);
CREATE INDEX IF NOT EXISTS alerts_key ON alerts (key);
CREATE TABLE IF NOT EXISTS meta (key text PRIMARY KEY, value text);
"""


def ts(seconds: float | None) -> dt.datetime | None:
    return None if seconds is None else dt.datetime.fromtimestamp(seconds, dt.timezone.utc)


def secs(when: dt.datetime | None) -> float | None:
    return None if when is None else when.timestamp()


def iso(value) -> str | None:
    if value is None:
        return None
    when = value if isinstance(value, dt.datetime) else ts(value)
    return when.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Store:
    def __init__(self, url: str):
        self.url = url
        self.lock = threading.RLock()
        self.conn: psycopg.Connection | None = None
        self._q(SCHEMA)

    def _connect(self) -> psycopg.Connection:
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(self.url, autocommit=True, connect_timeout=10)
        return self.conn

    def _q(self, sql: str, params=(), fetch: str | None = None):
        """Runs one statement, reconnecting once if the connection dropped (a Postgres restart, say)."""
        with self.lock:
            for attempt in (0, 1):
                try:
                    with self._connect().cursor() as cur:
                        cur.execute(sql, params)
                        if fetch == "one":
                            return cur.fetchone()
                        if fetch == "all":
                            return cur.fetchall()
                        return cur.rowcount
                except psycopg.OperationalError:
                    self.conn = None
                    if attempt:
                        raise
                    log.warning("database connection lost; reconnecting")

    # MARK: Signals

    def add_signals(self, signals: list[dict], source: str) -> int:
        """Merges signals (newer reports win) and records history. Returns how many were new."""
        now = ts(time.time())
        new = 0
        with self.lock:
            for s in signals:
                path, reported = s["name"], ts(s.get("timestamp") or time.time())
                row = self._q("SELECT value, reported FROM latest WHERE path=%s", (path,), "one")
                if row and row[1] is not None and reported < row[1]:
                    continue
                changed = not row or row[0] != s["value"]
                if row and row[1] == reported and not changed:
                    continue
                self._q("""INSERT INTO latest VALUES (%s,%s,%s,%s,%s) ON CONFLICT (path) DO UPDATE
                           SET value=EXCLUDED.value, unit=EXCLUDED.unit, reported=EXCLUDED.reported,
                               received=EXCLUDED.received""",
                        (path, Jsonb(s["value"]), s.get("unit"), reported, now))
                if changed or path in KEY_PATHS:
                    self._q("INSERT INTO history VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (path, Jsonb(s["value"]), s.get("unit"), reported, now, source))
                new += 1
        return new

    def state(self) -> dict:
        rows = self._q("SELECT path, value, unit, reported, received FROM latest ORDER BY path", fetch="all")
        return {
            "signals": [{"name": p, "value": v, "unit": u, "timestamp": iso(r)} for p, v, u, r, _ in rows],
            "receivedAt": iso(max((r[4] for r in rows), default=None)),
            "reportedAt": iso(max((r[3] for r in rows if r[3]), default=None)),
        }

    def latest_values(self) -> dict:
        return dict(self._q("SELECT path, value FROM latest", fetch="all"))

    def latest_report_time(self) -> float | None:
        return secs(self._q("SELECT MAX(reported) FROM latest", fetch="one")[0])

    def history(self, path: str, start: float, end: float) -> list[tuple[float, object]]:
        rows = self._q("SELECT reported, value FROM history WHERE path=%s AND reported BETWEEN %s AND %s ORDER BY reported",
                       (path, ts(start), ts(end)), "all")
        return [(secs(r), v) for r, v in rows]

    def soc_readings(self, start: float, end: float) -> list[tuple[float, float]]:
        out: dict[float, float] = {}
        for path in SOC:
            for t, v in self.history(path, start, end):
                n = number(v)
                if n is not None:
                    out.setdefault(t, n)
        return sorted(out.items())

    # MARK: Journeys

    def add_journeys(self, items: list[dict]) -> int:
        new = 0
        with self.lock:
            for j in items:
                start, end = parse_time(j.get("startTime")), parse_time(j.get("endTime"))
                if not j.get("journeyId") or start is None:
                    continue
                new += self._q("""INSERT INTO journeys VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE
                                  SET started=EXCLUDED.started, ended=EXCLUDED.ended, body=EXCLUDED.body""",
                               (str(j["journeyId"]), ts(start), ts(end or start), Jsonb(j)))
        return new

    def journeys(self, start: float, end: float) -> list[dict]:
        rows = [(secs(s), secs(e), body) for s, e, body in self._q(
            "SELECT started, ended, body FROM journeys WHERE started BETWEEN %s AND %s ORDER BY started",
            (ts(start), ts(end)), "all")]
        socs = self.soc_readings(start - 3 * 86400, end + 86400)
        out = []
        for i, (s, e, j) in enumerate(rows):
            next_start = rows[i + 1][0] if i + 1 < len(rows) else e + 6 * 3600
            before = [r for r in socs if r[0] <= s + 60]
            after = [r for r in socs if e - 120 <= r[0] <= min(next_start, e + 6 * 3600)]
            if before and after and s - before[-1][0] <= 3 * 86400:
                start_soc, end_soc = before[-1][1], after[0][1]
                j["socStart"], j["socEnd"] = start_soc, end_soc
                if start_soc >= end_soc:
                    j["socUsed"] = round(start_soc - end_soc, 1)
            out.append(j)
        return out

    # MARK: Charging

    def charges(self, start: float, end: float) -> list[dict]:
        """Charging sessions: runs of rising battery %, closed when it stops rising."""
        socs = self.soc_readings(start, end)
        energy = self.history("Vehicle.Powertrain.TractionBattery.Charging.Session.Energy", start, end)
        sessions, cur = [], None
        for (t0, s0), (t1, s1) in zip(socs, socs[1:]):
            if s1 > s0:
                if cur is None:
                    cur = {"start": t0, "socStart": s0}
                cur.update(end=t1, socEnd=s1)
            elif cur and s1 < cur["socEnd"]:
                sessions.append(cur)
                cur = None
        if cur:
            sessions.append(cur)
        for c in sessions:
            kwh = [number(v) for t, v in energy if c["start"] - 600 <= t <= c["end"] + 3600]
            kwh = [k for k in kwh if k is not None]
            c["energyKWh"] = max(kwh) if kwh else None
            c["socAdded"] = round(c["socEnd"] - c["socStart"], 1)
            c["start"], c["end"] = iso(c["start"]), iso(c["end"])
        return sessions

    # MARK: Alerts

    @staticmethod
    def _alert(row) -> dict:
        id_, key, title, body, severity, started, cleared = row
        return {"id": id_, "key": key, "title": title, "body": body, "severity": severity,
                "startedAt": iso(started), "clearedAt": iso(cleared), "active": cleared is None}

    def add_alert(self, key: str, title: str, body: str, severity: str, started: float, closed: bool = False) -> dict:
        row = self._q("""INSERT INTO alerts (key, title, body, severity, started, cleared) VALUES (%s,%s,%s,%s,%s,%s)
                         RETURNING id, key, title, body, severity, started, cleared""",
                      (key, title, body, severity, ts(started), ts(started) if closed else None), "one")
        return self._alert(row)

    def open_alert(self, key: str) -> dict | None:
        row = self._q("""SELECT id, key, title, body, severity, started, cleared FROM alerts
                         WHERE key=%s AND cleared IS NULL ORDER BY id DESC LIMIT 1""", (key,), "one")
        return self._alert(row) if row else None

    def alert_exists(self, key: str) -> bool:
        return self._q("SELECT 1 FROM alerts WHERE key=%s LIMIT 1", (key,), "one") is not None

    def close_alert(self, alert_id: int, when: float) -> None:
        self._q("UPDATE alerts SET cleared=%s WHERE id=%s", (ts(when), alert_id))

    def alerts(self, since: float) -> list[dict]:
        rows = self._q("""SELECT id, key, title, body, severity, started, cleared FROM alerts
                          WHERE started >= %s OR cleared IS NULL ORDER BY started DESC""", (ts(since),), "all")
        return [self._alert(r) for r in rows]

    # MARK: Meta

    def get_meta(self, key: str) -> str | None:
        row = self._q("SELECT value FROM meta WHERE key=%s", (key,), "one")
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._q("INSERT INTO meta VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (key, value))
