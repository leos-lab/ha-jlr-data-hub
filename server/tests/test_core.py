import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "custom_components" / "jlr_data_hub"))  # the shared jlr_datahub client

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402

from jlr_datahub.crypto import PSS, DPoP, RSAKey, b64url_decode, client_assertion, jwt_claims  # noqa: E402
from jlr_datahub.signals import parse_signals  # noqa: E402
from store import Store  # noqa: E402
import os  # noqa: E402
import pytest  # noqa: E402

TEST_DB = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB, reason="set TEST_DATABASE_URL to a throwaway Postgres")


def fresh_store() -> Store:
    import psycopg
    with psycopg.connect(TEST_DB, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS latest, history, journeys, alerts, meta")
    return Store(TEST_DB)

KEY = RSAKey.generate()


def test_certificate_is_self_signed_pss_and_openssl_accepts_it():
    pem = KEY.certificate_pem("test")
    cert = x509.load_pem_x509_certificate(pem.encode())
    assert cert.signature_algorithm_oid.dotted_string == "1.2.840.113549.1.1.10"
    KEY.key.public_key().verify(cert.signature, cert.tbs_certificate_bytes, PSS, hashes.SHA256())
    with tempfile.NamedTemporaryFile("w", suffix=".pem") as f:
        f.write(pem)
        f.flush()
        out = subprocess.run(["openssl", "verify", "-CAfile", f.name, f.name], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_client_assertion_claims_and_signature():
    aud = "https://auth.jlr-vcdp.com/realms/public/protocol/openid-connect/token"
    jwt = client_assertion("cid", aud, KEY)
    h, c, s = jwt.split(".")
    assert json.loads(b64url_decode(h))["alg"] == "PS256"
    claims = jwt_claims(jwt)
    assert claims["iss"] == claims["sub"] == "cid" and claims["aud"] == aud and claims["exp"] - claims["iat"] == 300
    KEY.key.public_key().verify(b64url_decode(s), f"{h}.{c}".encode(), PSS, hashes.SHA256())


def test_dpop_matches_rfc9449_ath_and_strips_query():
    d = DPoP(KEY)
    proof = d.proof("get", "https://data.jlr-vcdp.com/v1/x?page=0", "Kz~8mXK1EalYznwH-LC-1fBAo.4Ljp~zsPE_NeO.gxU")
    claims = jwt_claims(proof)
    assert claims["htm"] == "GET" and claims["htu"] == "https://data.jlr-vcdp.com/v1/x"
    assert claims["ath"] == "fUHyO2r2Z3DZ53EsNrWBb0xWXoaNy59IiKCAqksmQEo"
    header = json.loads(b64url_decode(proof.split(".")[0]))
    assert header["typ"] == "dpop+jwt" and header["jwk"]["kty"] == "RSA" and header["jwk"]["e"] == "AQAB"


def test_parses_both_payload_shapes():
    nested = {"Vehicle": {"Powertrain": {"TractionBattery": {"StateOfCharge": {"Displayed": 90}}}},
              "timestamp": "2026-11-24T21:25:20Z"}
    s = parse_signals(nested)
    assert s == [{"name": "Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed", "value": 90, "unit": None,
                  "timestamp": 1795555520.0}]
    flat = {"name": "Vehicle.Body.Door.Lock.Status", "value": "TRUE", "unit": "none",
            "timestamp": "2026-11-24T21:30:00.000Z"}
    assert parse_signals(flat)[0]["unit"] is None


@needs_db
def test_trip_battery_use_and_charging_from_history():
    if True:
        st = fresh_store()
        soc = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed"
        t0 = time.time() - 86400
        # 80% when parked, trip of 30 min, 74% at switch-off, then charged to 90%.
        st.add_signals([{"name": soc, "value": 80, "unit": None, "timestamp": t0}], "rest")
        st.add_signals([{"name": soc, "value": 74, "unit": None, "timestamp": t0 + 3600 + 1800 + 20}], "stream")
        st.add_signals([{"name": soc, "value": 82, "unit": None, "timestamp": t0 + 7200}], "stream")
        st.add_signals([{"name": soc, "value": 90, "unit": None, "timestamp": t0 + 9000}], "stream")
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))  # noqa: E731
        st.add_journeys([{"journeyId": "1", "startTime": iso(t0 + 3600), "endTime": iso(t0 + 5400),
                          "distance": {"value": 30, "unit": "km"}}])
        [trip] = st.journeys(t0, time.time())
        assert (trip["socStart"], trip["socEnd"], trip["socUsed"]) == (80, 74, 6)
        [charge] = st.charges(t0, time.time())
        assert (charge["socStart"], charge["socEnd"], charge["socAdded"]) == (74, 90, 16)


@needs_db
def test_older_values_never_overwrite_newer():
    if True:
        st = fresh_store()
        st.add_signals([{"name": "Vehicle.X", "value": 2, "unit": None, "timestamp": 200}], "rest")
        st.add_signals([{"name": "Vehicle.X", "value": 1, "unit": None, "timestamp": 100}], "rest")
        assert st.state()["signals"][0]["value"] == 2


@needs_db
def test_alerts_open_once_and_clear():
    import alerts as alerting
    if True:
        st = fresh_store()
        lv = "Vehicle.LowVoltageBattery."
        st.add_signals([{"name": lv + "IsBatteryLow", "value": "BATTERY_LOW", "unit": None, "timestamp": 100},
                        {"name": lv + "CurrentVoltage", "value": 11.5, "unit": None, "timestamp": 100},
                        {"name": "Vehicle.System.DriveCycle.Status", "value": "KEY_REMOVED", "unit": None, "timestamp": 100}], "rest")
        opened = alerting.evaluate(st, now=200)
        assert {a["key"] for a in opened} == {"lv-low", "lv-voltage"}
        assert alerting.evaluate(st, now=300) == []  # still active: not raised again
        st.add_signals([{"name": lv + "IsBatteryLow", "value": "BATTERY_1_1", "unit": None, "timestamp": 400},
                        {"name": lv + "CurrentVoltage", "value": 12.6, "unit": None, "timestamp": 400}], "rest")
        alerting.evaluate(st, now=500)
        assert all(not a["active"] for a in st.alerts(0))
        # A fault code is raised once per value.
        dtc = [{"name": "Vehicle.Diagnostics.BECM.DTC.0x008F", "value": "P0A80", "unit": None, "timestamp": 600}]
        assert len(alerting.diagnostic_alerts(st, dtc)) == 1
        assert alerting.diagnostic_alerts(st, dtc) == []


def test_apns_jwt_is_es256():
    import alerts as alerting
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    with tempfile.TemporaryDirectory() as d:
        key = ec.generate_private_key(ec.SECP256R1())
        (Path(d) / "AuthKey_ABC123.p8").write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        apns = alerting.APNs(Path(d), "TEAM", "co.example")
        h, c, s = apns._token().split(".")
        assert json.loads(b64url_decode(h)) == {"alg": "ES256", "kid": "ABC123"}
        assert json.loads(b64url_decode(c))["iss"] == "TEAM" and len(b64url_decode(s)) == 64
