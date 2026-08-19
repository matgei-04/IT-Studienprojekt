"""Jinja2-Rendering ohne Web-Framework (nur die Template-Engine)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _de_date(value: datetime) -> str:
    return value.strftime("%d.%m.%Y")


def _de_datetime(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M")


def _percent(value: float) -> str:
    return f"{round(value * 100)}%"


def _de_currency(value: float | None, currency: str | None = None) -> str:
    if value is None:
        return "–"
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    symbol = "€" if (currency or "").upper() == "EUR" else (currency or "")
    return f"{formatted} {symbol}".strip()


def _file_size(value: int | None) -> str:
    if value is None:
        return "–"
    size = float(value)
    for unit in ("Bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "Bytes" else f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return f"{value} Bytes"


_env.filters["de_date"] = _de_date
_env.filters["de_datetime"] = _de_datetime
_env.filters["percent"] = _percent
_env.filters["de_currency"] = _de_currency
_env.filters["file_size"] = _file_size


def render(template_name: str, **context) -> str:
    template = _env.get_template(template_name)
    return template.render(**context)
