"""The vendored library: certificate, client assertion and DPoP (from jlr-server's own tests)."""
import json
import subprocess
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from custom_components.jlr_data_hub.jlr_datahub.crypto import (
    PSS,
    DPoP,
    RSAKey,
    b64url_decode,
    client_assertion,
    jwt_claims,
)
from custom_components.jlr_data_hub.jlr_datahub.signals import parse_signals

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
    assert parse_signals(nested) == [{"name": "Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed",
                                      "value": 90, "unit": None, "timestamp": 1795555520.0}]
    flat = {"name": "Vehicle.Body.Door.Lock.Status", "value": "TRUE", "unit": "none",
            "timestamp": "2026-11-24T21:30:00.000Z"}
    assert parse_signals(flat)[0]["unit"] is None



def test_parses_real_stream_messages():
    # What the stream really sends (captured from an I-Pace, 25 Nov 2026): not the documented {name, value}.
    streamed = [{"vssIdentifier": "Vehicle.Powertrain.TractionBattery.Range", "signalValue": "334",
                 "signalTimestamp": "1795622756215", "signalName": "Powertrain.TractionBattery.Range",
                 "dataType": "int32", "unit": "km", "description": "Remaining range in Kilometres"},
                {"vssIdentifier": "Vehicle.Body.Lights.Beam.Low.IsOn", "signalValue": "UNKNOWN",
                 "signalTimestamp": "1795622756215", "unit": "none"}]
    assert parse_signals(streamed) == [
        {"name": "Vehicle.Powertrain.TractionBattery.Range", "value": "334", "unit": "km", "timestamp": 1795622756.215},
        {"name": "Vehicle.Body.Lights.Beam.Low.IsOn", "value": "UNKNOWN", "unit": None, "timestamp": 1795622756.215},
    ]
