import base64
import io

import pytest
from PIL import Image
from pydantic import ValidationError

from app.appearance import Appearance, AppearanceStore


def test_branding_survives_store_recreation_and_can_reset(tmp_path):
    path = tmp_path / "users.db"
    branding = Appearance(
        title="Health Quality",
        background="#eef0ff",
        font_size=20,
        navigation={"link:/usage": {"label": "Usage", "icon": "◎"}},
    )
    AppearanceStore(path).save(branding)
    assert AppearanceStore(path).read() == branding
    AppearanceStore(path).save(Appearance())
    assert AppearanceStore(path).read() == Appearance()


@pytest.mark.parametrize(
    "values",
    [
        {"font_size": 60},
        {"font_family": "url(external)"},
        {"background": "red; display:none"},
        {"title": " "},
        {"logo": "data:image/svg+xml;base64,PHN2Zz4="},
        {"logo": "data:image/png;base64,bm90IGFuIGltYWdl"},
        {"navigation": {"link:/": {"label": ""}}},
    ],
)
def test_appearance_rejects_invalid_values(values):
    with pytest.raises(ValidationError):
        Appearance(**values)


def test_logo_image_must_match_declared_type_and_dimensions():
    output = io.BytesIO()
    Image.new("RGB", (32, 32)).save(output, format="PNG")
    data = base64.b64encode(output.getvalue()).decode()
    assert Appearance(logo="data:image/png;base64," + data).logo
    with pytest.raises(ValidationError):
        Appearance(logo="data:image/jpeg;base64," + data)
    output = io.BytesIO()
    Image.new("RGB", (2049, 1)).save(output, format="PNG")
    with pytest.raises(ValidationError):
        Appearance(logo="data:image/png;base64," + base64.b64encode(output.getvalue()).decode())


@pytest.mark.parametrize("size", [256001, 500 * 1024])
def test_logo_up_to_500_kb_survives_storage(tmp_path, size):
    output = io.BytesIO()
    Image.new("RGB", (32, 32)).save(output, format="PNG")
    data = output.getvalue().ljust(size, b"\0")
    logo = "data:image/png;base64," + base64.b64encode(data).decode()
    appearance = Appearance(logo=logo)
    store = AppearanceStore(tmp_path / "users.db")
    store.save(appearance)
    assert store.read().logo == logo


def test_logo_one_byte_over_500_kb_is_rejected():
    output = io.BytesIO()
    Image.new("RGB", (32, 32)).save(output, format="PNG")
    data = output.getvalue().ljust(500 * 1024 + 1, b"\0")
    with pytest.raises(ValidationError, match="Logo must be no larger than 500 KB"):
        Appearance(logo="data:image/png;base64," + base64.b64encode(data).decode())
