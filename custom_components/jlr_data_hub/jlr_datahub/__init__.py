"""A Python client for the JLR Data Hub (vehicle owner access): keys and certificate, Device Code sign-in, DPoP-bound
REST, and the MQTT stream. Shared by the N100 server and this Home Assistant integration.

Vendored from Utils-ios/jlr-server/jlr_datahub at 178e92b. Local changes: JLRClient takes the User-Agent and the
certificate's common name. Keep the rest identical so fixes can flow both ways."""
from .client import Config, DeviceAuthorization, JLRClient, JLRError, SignInRequired, Tokens
from .signals import parse_signals
from .stream import Stream

__all__ = ["Config", "DeviceAuthorization", "JLRClient", "JLRError", "SignInRequired", "Tokens", "parse_signals", "Stream"]
