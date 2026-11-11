"""Validated shared branding, stored independently of provider and workflow configuration."""

import base64
import binascii
import io
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings, get_settings

MAX_LOGO_BYTES = 500 * 1024
# The data URL carries base64 text, which is larger than the uploaded image bytes.
MAX_LOGO_DATA_URL_LENGTH = 4 * ((MAX_LOGO_BYTES + 2) // 3) + len("data:image/jpeg;base64,")

router = APIRouter()


class NavigationLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=60)
    icon: str = Field(default="", max_length=8)


class Appearance(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(default="Auto Finance Quality", min_length=1, max_length=80)
    subtitle: str = Field(default="Vehicle finance testing", max_length=100)
    logo: str = Field(default="", max_length=MAX_LOGO_DATA_URL_LENGTH)
    background: str = Field(default="", pattern=r"^(#[0-9a-fA-F]{6})?$")
    font_size: int = Field(default=16, ge=14, le=22)
    font_family: Literal["system", "arial", "georgia", "verdana", "mono"] = "system"
    navigation: dict[str, NavigationLabel] = Field(default_factory=dict, max_length=60)

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, value: str) -> str:
        if not value:
            return value
        header, separator, data = value.partition(",")
        formats = {
            "data:image/png;base64": "PNG",
            "data:image/jpeg;base64": "JPEG",
            "data:image/webp;base64": "WEBP",
        }
        if not separator or header not in formats:
            raise ValueError("Use a PNG, JPEG or WebP logo")
        try:
            decoded = base64.b64decode(data, validate=True)
            if len(decoded) > MAX_LOGO_BYTES:
                raise ValueError("Logo must be no larger than 500 KB")
            with Image.open(io.BytesIO(decoded)) as image:
                if image.format != formats[header] or max(image.size) > 2048:
                    raise ValueError("Logo dimensions must not exceed 2048 pixels")
                image.verify()
        except (
            binascii.Error,
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
        ) as error:
            raise ValueError("Logo image is invalid") from error
        return value


class AppearanceStore:
    def __init__(self, path: Path) -> None:
        self.path = path.with_name("appearance.db")

    def read(self) -> Appearance:
        if not self.path.exists():
            return Appearance()
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT document FROM appearance WHERE id=1").fetchone()
        return Appearance.model_validate_json(row[0]) if row else Appearance()

    def save(self, appearance: Appearance) -> Appearance:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS appearance "
                "(id INTEGER PRIMARY KEY, document TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO appearance VALUES (1, ?) ON CONFLICT(id) "
                "DO UPDATE SET document=excluded.document",
                (appearance.model_dump_json(),),
            )
        return appearance


@router.get("/api/appearance")
async def read_appearance(settings: Annotated[Settings, Depends(get_settings)]) -> Appearance:
    try:
        return AppearanceStore(settings.user_database_path).read()
    except (sqlite3.Error, OSError, ValueError) as error:
        raise HTTPException(503, "Appearance settings could not be read") from error


@router.put("/api/admin/appearance")
async def save_appearance(
    appearance: Appearance, settings: Annotated[Settings, Depends(get_settings)]
) -> Appearance:
    try:
        return AppearanceStore(settings.user_database_path).save(appearance)
    except (sqlite3.Error, OSError) as error:
        raise HTTPException(503, "Appearance settings could not be saved") from error
