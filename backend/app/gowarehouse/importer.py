from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO, StringIO
from typing import Any

from openpyxl import load_workbook

MAX_IMPORT_BYTES = 15 * 1024 * 1024

ORDER_ALIASES = {
    "order_id": {"訂單編號", "order_id", "order id"},
    "channel": {"通路名稱", "銷售通路", "channel"},
    "platform": {"電商平台", "platform"},
    "shipping_type": {"物流類型", "物流方式", "shipping_type"},
    "amount": {"訂單金額", "amount", "total"},
    "urgent": {"急單", "urgent"},
    "reserved_ship_date": {"預約出貨日", "reserved_ship_date"},
    "shipped_at": {"出貨時間", "shipped_at"},
    "order_status": {"訂單狀態", "狀態", "status"},
    "created_at": {"建立時間", "created_at"},
}

INVENTORY_ALIASES = {
    "merchant": {"貨主名稱", "貨主", "merchant"},
    "sku": {"品號", "sku"},
    "product_name": {"商品名稱", "品名", "product_name"},
    "inventory_type": {"庫存類型", "庫別", "inventory_type"},
    "quantity": {"數量", "quantity"},
    "batch": {"批號", "batch"},
    "expiration_date": {"效期", "有效期限", "expiration_date"},
    "status": {"狀態", "status"},
    "available": {"可用數量", "available"},
    "allocated": {"已分配數量", "allocated"},
}


@dataclass(frozen=True)
class ParsedOrder:
    order_id: str
    channel: str | None
    platform: str | None
    shipping_type: str | None
    amount: float | None
    urgent: bool
    reserved_ship_date: date | None
    shipped_at: datetime | None
    order_status: str | None
    source_created_at: datetime | None


@dataclass(frozen=True)
class ParsedInventory:
    merchant: str
    sku: str
    product_name: str | None
    inventory_type: str | None
    quantity: int
    batch: str | None
    expiration_date: date | None
    status: str | None
    available: int | None
    allocated: int | None


@dataclass(frozen=True)
class ParsedImport:
    orders: tuple[ParsedOrder, ...] = ()
    inventory: tuple[ParsedInventory, ...] = ()
    warnings: tuple[str, ...] = ()


def parse_orders_file(content: bytes, suffix: str) -> ParsedImport:
    rows, columns = _open(content, suffix, ORDER_ALIASES, required=("order_id",), label="訂單")
    seen: dict[str, ParsedOrder] = {}
    warnings: list[str] = []
    for _row_number, row in rows:
        order_id = _text(_get(row, columns, "order_id"))
        if not order_id:
            continue
        if order_id in seen:
            # Orders export is line-item level; keep the first (order-level fields repeat).
            continue
        seen[order_id] = ParsedOrder(
            order_id=order_id,
            channel=_opt_text(_get(row, columns, "channel")),
            platform=_opt_text(_get(row, columns, "platform")),
            shipping_type=_opt_text(_get(row, columns, "shipping_type")),
            amount=_float(_get(row, columns, "amount")),
            urgent=_boolean(_get(row, columns, "urgent")),
            reserved_ship_date=_date_or_none(_get(row, columns, "reserved_ship_date")),
            shipped_at=_datetime_or_none(_get(row, columns, "shipped_at")),
            order_status=_opt_text(_get(row, columns, "order_status")),
            source_created_at=_datetime_or_none(_get(row, columns, "created_at")),
        )
    if not seen:
        raise ValueError("訂單匯出檔中沒有可匯入的訂單資料。")
    return ParsedImport(orders=tuple(seen.values()), warnings=tuple(warnings))


def parse_inventory_file(content: bytes, suffix: str) -> ParsedImport:
    rows, columns = _open(
        content, suffix, INVENTORY_ALIASES, required=("merchant", "sku"), label="庫存"
    )
    records: list[ParsedInventory] = []
    warnings: list[str] = []
    for _row_number, row in rows:
        merchant = _text(_get(row, columns, "merchant"))
        sku = _text(_get(row, columns, "sku"))
        if not merchant or not sku:
            continue
        records.append(
            ParsedInventory(
                merchant=merchant,
                sku=sku,
                product_name=_opt_text(_get(row, columns, "product_name")),
                inventory_type=_opt_text(_get(row, columns, "inventory_type")),
                quantity=_integer(_get(row, columns, "quantity")) or 0,
                batch=_opt_text(_get(row, columns, "batch")),
                expiration_date=_date_or_none(_get(row, columns, "expiration_date")),
                status=_opt_text(_get(row, columns, "status")),
                available=_integer(_get(row, columns, "available")),
                allocated=_integer(_get(row, columns, "allocated")),
            )
        )
    if not records:
        raise ValueError("庫存匯出檔中沒有可匯入的庫存資料。")
    return ParsedImport(inventory=tuple(records), warnings=tuple(warnings))


# --------------------------------------------------------------------------- #
# Shared parsing helpers
# --------------------------------------------------------------------------- #
def _open(
    content: bytes,
    suffix: str,
    aliases: dict[str, set[str]],
    *,
    required: tuple[str, ...],
    label: str,
):  # type: ignore[no-untyped-def]
    if not content:
        raise ValueError(f"上傳的{label}檔是空白檔案。")
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError(f"{label}檔超過 15 MB，請縮小後再匯入。")
    rows = _xlsx_rows(content) if suffix == ".xlsx" else _csv_rows(content)
    header = next(rows, None)
    if not header:
        raise ValueError(f"{label}檔沒有欄位名稱。")
    columns = _resolve_columns(header, aliases)
    for field in required:
        if field not in columns:
            names = "、".join(sorted(aliases[field]))
            raise ValueError(f"{label}檔缺少必要欄位（{names}）。")
    return enumerate(rows, start=2), columns


def _xlsx_rows(content: bytes):  # type: ignore[no-untyped-def]
    try:
        workbook = load_workbook(BytesIO(content), data_only=True)
        sheet = workbook.active
        yield from sheet.iter_rows(values_only=True)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("無法讀取這份 Excel，請確認檔案沒有損壞。") from exc


def _csv_rows(content: bytes):  # type: ignore[no-untyped-def]
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("big5")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV 請使用 UTF-8 或 Big5 編碼。") from exc
    yield from csv.reader(StringIO(text))


def _resolve_columns(
    header: tuple[Any, ...] | list[Any], aliases: dict[str, set[str]]
) -> dict[str, int]:
    normalized = {_text(value).casefold(): index for index, value in enumerate(header)}
    resolved: dict[str, int] = {}
    for field, names in aliases.items():
        for alias in names:
            if alias.casefold() in normalized:
                resolved[field] = normalized[alias.casefold()]
                break
    return resolved


def _get(row, columns: dict[str, int], field: str) -> Any:  # type: ignore[no-untyped-def]
    index = columns.get(field)
    if index is None or index >= len(row):
        return None
    return row[index]


def _text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _opt_text(value: Any) -> str | None:
    return _text(value) or None


def _boolean(value: Any) -> bool:
    return _text(value).casefold() in {"1", "true", "yes", "y", "是", "急單"}


def _integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _date_or_none(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = _parse_datetime(_text(value))
    return parsed.date() if parsed else None


def _datetime_or_none(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or UTC)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), UTC)
    return _parse_datetime(_text(value))


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=parsed.tzinfo or UTC)
    except ValueError:
        return None
