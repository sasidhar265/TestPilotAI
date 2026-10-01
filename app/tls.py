"""Supply verified roots for Python installations missing their default CA bundle."""

import os
import ssl

import certifi


def configure_default_ca_bundle() -> None:
    # Preserve administrator-provided trust and working operating-system defaults.
    if "SSL_CERT_FILE" in os.environ or "SSL_CERT_DIR" in os.environ:
        return
    defaults = ssl.get_default_verify_paths()
    if defaults.cafile is None and defaults.capath is None:
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
