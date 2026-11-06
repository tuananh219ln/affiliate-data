"""Shape-tolerant helpers for reading site JSON."""

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def walk_dicts(obj: Any) -> Iterator[dict[str, Any]]:
    """Every dict inside `obj`, outermost first."""
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_dicts(value)


def pick(d: dict[str, Any], *keys: str) -> Any:
    """The first value that is not None among `keys`.

    A key may be a dotted path ("stats.playCount"); a number in the path indexes a list ("url_list.0").
    """
    for key in keys:
        value: Any = d
        for part in key.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
                value = value[int(part)]
            else:
                value = None
            if value is None:
                break
        if value is not None and value != "":
            return value
    return None


def has_any(d: dict[str, Any], *keys: str) -> bool:
    return pick(d, *keys) is not None


_SUFFIX = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "tr": 1_000_000, "n": 1_000}


def to_decimal(value: Any) -> Decimal | None:
    """Numbers as sites print them: 12000, "12.000", "12,5k", "1.2M", "₫99.000", "10%"."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    text = str(value).strip().lower().replace("₫", "").replace("đ", "").replace("%", "").replace("+", "").strip()
    match = re.fullmatch(r"([\d.,]+)\s*(k|m|b|tr|n)?", text)
    if not match:
        return None
    number, suffix = match.groups()
    if suffix:
        # "1,2k" / "1.2k": the separator is a decimal point.
        number = number.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}([.,]\d{3})+", number):
        # "12.000" / "12,000": thousands separators.
        number = number.replace(".", "").replace(",", "")
    else:
        number = number.replace(",", ".")
    try:
        result = Decimal(number)
    except InvalidOperation:
        return None
    return result * _SUFFIX[suffix] if suffix else result


def to_int(value: Any) -> int | None:
    number = to_decimal(value)
    return int(number) if number is not None else None


def to_rate(value: Any) -> float | None:
    """A commission rate as a fraction (0.1 = 10 %).

    "10%" and 10 both mean 10 %; 0.1 is already a fraction; values above 100 are basis points
    (TikTok reports 1000 for 10 %).
    """
    if value is None:
        return None
    number = to_decimal(value)
    if number is None:
        return None
    if isinstance(value, str) and "%" in value:
        return float(number / 100)
    if number > 100:
        return float(number / 10_000)
    if number > 1:
        return float(number / 100)
    return float(number)


def to_datetime(value: Any) -> datetime | None:
    """Epoch seconds or milliseconds, or an ISO string."""
    if value is None or value == "":
        return None
    number = to_decimal(value)
    if number is not None and number > 0:
        seconds = float(number) / 1000 if number > 10_000_000_000 else float(number)
        return datetime.fromtimestamp(seconds, tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def text(value: Any) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def dedupe(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Keeps the last row for each key: later responses on a page are the fresher ones."""
    by_key = {row[key]: row for row in rows}
    return list(by_key.values())
