from types import SimpleNamespace

import pytest

from app.tls import configure_default_ca_bundle


@pytest.mark.parametrize("cafile,capath", [(None, None), ("system.pem", None), (None, "certs")])
def test_certificate_fallback_only_when_system_trust_is_missing(monkeypatch, cafile, capath):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setattr(
        "app.tls.ssl.get_default_verify_paths",
        lambda: SimpleNamespace(cafile=cafile, capath=capath),
    )
    monkeypatch.setattr("app.tls.certifi.where", lambda: "verified-roots.pem")
    configure_default_ca_bundle()
    import os

    assert os.environ.get("SSL_CERT_FILE") == (
        "verified-roots.pem" if not cafile and not capath else None
    )


@pytest.mark.parametrize("variable", ["SSL_CERT_FILE", "SSL_CERT_DIR"])
def test_custom_certificate_trust_is_preserved(monkeypatch, variable):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setenv(variable, "corporate-trust")
    configure_default_ca_bundle()
    import os

    assert os.environ[variable] == "corporate-trust"
