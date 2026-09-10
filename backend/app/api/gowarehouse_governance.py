from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update

from app.api.access import OpsAccess, UploadAccess
from app.dependencies import SessionDependency
from app.gowarehouse.importer import (
    ParsedImport,
    ParsedOperationalRecord,
    ParsedOrder,
    parse_inventory_file,
    parse_operational_file,
    parse_orders_file,
)
from app.models import (
    GoWarehouseImportBatch,
    GoWarehouseImportChange,
    GoWarehouseInventory,
    GoWarehouseOperationalRecord,
    GoWarehouseOrder,
    GoWarehousePendingImport,
    GoWarehouseProductMerchantMap,
    MerchantMaster,
    WarehouseMaster,
    utc_now,
)

router = APIRouter(prefix="/api/gw-imports", tags=["gowarehouse-governance"])

SUPPORTED_KINDS = {"orders", "inventory", "inbound", "returns", "picking", "consignment"}
ACTIVE = "ACTIVE"
PENDING = "PENDING"


class CatalogCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=40)
    aliases: list[str] = Field(default_factory=list, max_length=30)


class CatalogUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    aliases: list[str] | None = Field(default=None, max_length=30)
    status: Literal["ACTIVE", "PENDING", "INACTIVE"] | None = None


class BatchCorrection(BaseModel):
    merchant_id: str | None = None
    warehouse_id: str | None = None


class ConfirmAction(BaseModel):
    confirm: str


class ProductMerchantUpdate(BaseModel):
    merchant_id: str


def _ensure_seed_catalog(session) -> None:  # type: ignore[no-untyped-def]
    seeds = (
        ("warehouse-tamsui", "TAMSUI", "淡水倉", ["淡水", "淡水倉庫"]),
        ("warehouse-xizhi", "XIZHI", "汐止倉", ["汐止", "汐止倉庫"]),
    )
    changed = False
    for identifier, code, name, aliases in seeds:
        if session.get(WarehouseMaster, identifier) is None:
            session.add(
                WarehouseMaster(
                    id=identifier,
                    code=code,
                    name=name,
                    aliases_json=aliases,
                    status=ACTIVE,
                )
            )
            changed = True
    if changed:
        session.commit()


def _normalized(value: str) -> str:
    return re.sub(r"[\s｜|_\-]+", "", value.strip().casefold())


def _catalog_match(items: list[Any], name: str):  # type: ignore[no-untyped-def]
    needle = _normalized(name)
    for item in items:
        candidates = [item.name, *(item.aliases_json or [])]
        if any(_normalized(candidate) == needle for candidate in candidates):
            return item
    return None


def _catalog_payload(session, *, include_pending: bool = False) -> dict[str, object]:  # type: ignore[no-untyped-def]
    _ensure_seed_catalog(session)
    warehouses = session.scalars(select(WarehouseMaster).order_by(WarehouseMaster.name)).all()
    merchants = session.scalars(select(MerchantMaster).order_by(MerchantMaster.name)).all()
    allowed = {ACTIVE, PENDING} if include_pending else {ACTIVE}
    return {
        "warehouses": [_catalog_item(item) for item in warehouses if item.status in allowed],
        "merchants": [_catalog_item(item) for item in merchants if item.status in allowed],
    }


def _catalog_item(item: WarehouseMaster | MerchantMaster) -> dict[str, object]:
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "aliases": item.aliases_json or [],
        "status": item.status,
    }


@router.get("/catalog")
def upload_catalog(_: UploadAccess, session: SessionDependency) -> dict[str, object]:
    return _catalog_payload(session)


@router.get("/governance/catalog")
def admin_catalog(_: OpsAccess, session: SessionDependency) -> dict[str, object]:
    payload = _catalog_payload(session, include_pending=True)
    pending = session.scalars(
        select(GoWarehousePendingImport)
        .where(GoWarehousePendingImport.status == "WAITING_APPROVAL")
        .order_by(GoWarehousePendingImport.requested_at)
    ).all()
    payload["pending_imports"] = [
        {
            "id": item.id,
            "merchant_id": item.merchant_id,
            "requested_merchant_name": item.requested_merchant_name,
            "source_filename": item.source_filename,
            "record_count": item.record_count,
            "requested_at": item.requested_at,
        }
        for item in pending
    ]
    product_maps = session.scalars(
        select(GoWarehouseProductMerchantMap).order_by(
            GoWarehouseProductMerchantMap.status,
            GoWarehouseProductMerchantMap.last_seen_at.desc(),
        )
    ).all()
    payload["product_mappings"] = [
        {
            "id": item.id,
            "sku": item.sku,
            "merchant_id": item.merchant_id,
            "status": item.status,
            "source_kinds": item.source_kinds_json or [],
            "first_seen_at": item.first_seen_at,
            "last_seen_at": item.last_seen_at,
            "resolved_at": item.resolved_at,
        }
        for item in product_maps
    ]
    return payload


@router.patch("/governance/product-mappings/{item_id}")
def resolve_product_mapping(
    item_id: str,
    payload: ProductMerchantUpdate,
    _: OpsAccess,
    session: SessionDependency,
) -> dict[str, object]:
    item = session.get(GoWarehouseProductMerchantMap, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="找不到此商品對照項目。")
    merchant = _active_by_id(session, MerchantMaster, payload.merchant_id, "貨主")
    item.merchant_id = merchant.id
    item.status = ACTIVE
    item.resolved_at = utc_now()
    session.commit()
    return {
        "id": item.id,
        "sku": item.sku,
        "merchant_id": merchant.id,
        "merchant_name": merchant.name,
        "status": item.status,
        "source_kinds": item.source_kinds_json or [],
        "resolved_at": item.resolved_at,
    }


@router.post("/governance/warehouses", status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: CatalogCreate, _: OpsAccess, session: SessionDependency
) -> dict[str, object]:
    item = _create_catalog_item(session, WarehouseMaster, payload, "WH")
    session.commit()
    return _catalog_item(item)


@router.post("/governance/merchants", status_code=status.HTTP_201_CREATED)
def create_merchant(
    payload: CatalogCreate, _: OpsAccess, session: SessionDependency
) -> dict[str, object]:
    item = _create_catalog_item(session, MerchantMaster, payload, "MER")
    session.commit()
    return _catalog_item(item)


def _create_catalog_item(session, model, payload: CatalogCreate, prefix: str):  # type: ignore[no-untyped-def]
    name = payload.name.strip()
    items = session.scalars(select(model)).all()
    aliases = _clean_aliases(payload.aliases, name)
    if any(_catalog_match(items, candidate) for candidate in [name, *aliases]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "CATALOG_EXISTS", "message": "此名稱或別名已存在。"},
        )
    generated = f"{prefix}-{hashlib.sha256(name.encode()).hexdigest()[:10]}"
    code = (payload.code or generated).strip().upper()
    if session.scalar(select(model).where(model.code == code)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "CODE_EXISTS", "message": "此代碼已存在。"},
        )
    item = model(
        code=code,
        name=name,
        aliases_json=aliases,
        status=ACTIVE,
    )
    session.add(item)
    session.flush()
    return item


@router.patch("/governance/warehouses/{item_id}")
def update_warehouse(
    item_id: str, payload: CatalogUpdate, _: OpsAccess, session: SessionDependency
) -> dict[str, object]:
    return _update_catalog(session, WarehouseMaster, item_id, payload)


@router.patch("/governance/merchants/{item_id}")
def update_merchant(
    item_id: str, payload: CatalogUpdate, _: OpsAccess, session: SessionDependency
) -> dict[str, object]:
    return _update_catalog(session, MerchantMaster, item_id, payload)


def _update_catalog(session, model, item_id: str, payload: CatalogUpdate) -> dict[str, object]:  # type: ignore[no-untyped-def]
    item = session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="找不到此主檔項目。")
    next_name = payload.name.strip() if payload.name is not None else item.name
    next_aliases = (
        _clean_aliases(payload.aliases, next_name)
        if payload.aliases is not None
        else _clean_aliases(item.aliases_json or [], next_name)
    )
    others = [
        candidate
        for candidate in session.scalars(select(model)).all()
        if candidate.id != item.id
    ]
    if any(
        _catalog_match(others, candidate) is not None
        for candidate in [next_name, *next_aliases]
    ):
        raise HTTPException(
            status_code=409,
            detail={"error_code": "CATALOG_EXISTS", "message": "名稱或別名與其他項目重複。"},
        )
    item.name = next_name
    item.aliases_json = next_aliases
    if payload.status is not None:
        item.status = payload.status
    if model is WarehouseMaster:
        for record_model in (
            GoWarehouseOrder,
            GoWarehouseInventory,
            GoWarehouseOperationalRecord,
        ):
            session.execute(
                update(record_model)
                .where(record_model.warehouse_id == item.id)
                .values(warehouse=item.name)
            )
    else:
        for record_model in (
            GoWarehouseOrder,
            GoWarehouseInventory,
            GoWarehouseOperationalRecord,
        ):
            session.execute(
                update(record_model)
                .where(record_model.merchant_id == item.id)
                .values(merchant=item.name)
            )
        session.execute(
            update(GoWarehouseImportBatch)
            .where(GoWarehouseImportBatch.merchant_id == item.id)
            .values(merchant=item.name)
        )
        completed_imports = (
            _complete_pending_imports(session, item)
            if item.status == ACTIVE
            else 0
        )
    session.commit()
    result = _catalog_item(item)
    if model is MerchantMaster:
        result["completed_pending_imports"] = completed_imports
    return result


def _clean_aliases(values: list[str], name: str) -> list[str]:
    aliases: list[str] = []
    seen = {_normalized(name)}
    for value in values:
        cleaned = value.strip()
        key = _normalized(cleaned)
        if cleaned and key not in seen:
            aliases.append(cleaned)
            seen.add(key)
    return aliases


def _read_upload(file: UploadFile) -> tuple[str, str, bytes]:
    filename = Path(file.filename or "export.xlsx").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "INVALID_FILE", "message": "請上傳 .xlsx 或 .csv 檔案。"},
        )
    return filename, suffix, b""


def _parse(content: bytes, suffix: str, kind: str) -> ParsedImport:
    try:
        if kind == "orders":
            return parse_orders_file(content, suffix)
        if kind == "inventory":
            return parse_inventory_file(content, suffix)
        return parse_operational_file(content, suffix, kind)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "INVALID_FILE", "message": str(exc)},
        ) from exc


def _preview_checksum(content: bytes, kind: str) -> str:
    return hashlib.sha256(kind.encode() + b":" + content).hexdigest()


def _active_by_id(session, model, item_id: str | None, label: str):  # type: ignore[no-untyped-def]
    if not item_id:
        return None
    item = session.get(model, item_id)
    if item is None or item.status != ACTIVE:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "INVALID_SELECTION", "message": f"選擇的{label}不存在或已停用。"},
        )
    return item


def _merchant_from_sku(session, sku: str) -> tuple[str | None, str]:  # type: ignore[no-untyped-def]
    mapping = session.scalar(
        select(GoWarehouseProductMerchantMap).where(
            GoWarehouseProductMerchantMap.sku == sku,
            GoWarehouseProductMerchantMap.status == ACTIVE,
        )
    )
    if mapping is not None and mapping.merchant_id:
        merchant = session.get(MerchantMaster, mapping.merchant_id)
        if merchant is not None and merchant.status == ACTIVE:
            return merchant.name, "PRODUCT_MAPPING"
    names = set(
        session.scalars(
            select(GoWarehouseInventory.merchant).where(GoWarehouseInventory.sku == sku)
        ).all()
    )
    if len(names) == 1:
        return next(iter(names)), "INVENTORY_SKU"
    return None, "UNRESOLVED"


def _merchant_from_order(
    session, item: ParsedOrder
) -> tuple[str | None, str]:  # type: ignore[no-untyped-def]
    ref_hash = hashlib.sha256(item.order_id.encode()).hexdigest()
    by_order = session.scalar(
        select(GoWarehouseOperationalRecord.merchant)
        .where(
            GoWarehouseOperationalRecord.order_ref_hash == ref_hash,
            GoWarehouseOperationalRecord.merchant.is_not(None),
        )
        .limit(1)
    )
    if by_order:
        return str(by_order), "ORDER_LINK"
    if not item.skus:
        return None, "UNRESOLVED"
    results = [_merchant_from_sku(session, sku) for sku in item.skus]
    mapped = {result[0] for result in results if result[0]}
    if len(mapped) == 1 and all(result[0] for result in results):
        method = (
            "PRODUCT_MAPPING"
            if any(result[1] == "PRODUCT_MAPPING" for result in results)
            else "INVENTORY_SKU"
        )
        return next(iter(mapped)), method
    return None, "UNRESOLVED"


def _merchant_from_operational(
    session, item: ParsedOperationalRecord
) -> tuple[str | None, str]:  # type: ignore[no-untyped-def]
    if item.merchant:
        return item.merchant, "SOURCE_FIELD"
    if item.order_id:
        ref_hash = hashlib.sha256(item.order_id.encode()).hexdigest()
        from_order = session.scalar(
            select(GoWarehouseOrder.merchant)
            .where(GoWarehouseOrder.order_id == item.order_id)
            .limit(1)
        ) or session.scalar(
            select(GoWarehouseOperationalRecord.merchant)
            .where(
                GoWarehouseOperationalRecord.order_ref_hash == ref_hash,
                GoWarehouseOperationalRecord.merchant.is_not(None),
            )
            .limit(1)
        )
        if from_order:
            return str(from_order), "ORDER_LINK"
    if item.sku:
        return _merchant_from_sku(session, item.sku)
    return None, "UNRESOLVED"


def _warehouse_from_order(session, item: ParsedOrder) -> str | None:  # type: ignore[no-untyped-def]
    warehouse = session.scalar(
        select(GoWarehouseOrder.warehouse)
        .where(
            GoWarehouseOrder.order_id == item.order_id,
            GoWarehouseOrder.warehouse.is_not(None),
        )
        .limit(1)
    )
    return str(warehouse) if warehouse else None


def _warehouse_from_operational(session, item: ParsedOperationalRecord) -> str | None:  # type: ignore[no-untyped-def]
    if item.warehouse:
        return item.warehouse
    if not item.order_id:
        return None
    warehouse = session.scalar(
        select(GoWarehouseOrder.warehouse)
        .where(
            GoWarehouseOrder.order_id == item.order_id,
            GoWarehouseOrder.warehouse.is_not(None),
        )
        .limit(1)
    )
    if warehouse:
        return str(warehouse)
    ref_hash = hashlib.sha256(item.order_id.encode()).hexdigest()
    warehouse = session.scalar(
        select(GoWarehouseOperationalRecord.warehouse)
        .where(
            GoWarehouseOperationalRecord.order_ref_hash == ref_hash,
            GoWarehouseOperationalRecord.warehouse.is_not(None),
        )
        .limit(1)
    )
    return str(warehouse) if warehouse else None


def _mapping_conflicts(
    session, orders: tuple[ParsedOrder, ...], operational: tuple[ParsedOperationalRecord, ...]
) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    merchant_conflicts = 0
    warehouse_conflicts = 0
    for item in orders:
        merchants = {
            name
            for name, _ in (_merchant_from_sku(session, sku) for sku in item.skus)
            if name
        }
        warehouses = set(
            session.scalars(
                select(GoWarehouseOrder.warehouse).where(
                    GoWarehouseOrder.order_id == item.order_id,
                    GoWarehouseOrder.warehouse.is_not(None),
                )
            ).all()
        )
        merchant_conflicts += len({_normalized(name) for name in merchants}) > 1
        warehouse_conflicts += len({_normalized(name) for name in warehouses}) > 1
    for item in operational:
        merchants = {item.merchant} if item.merchant else set()
        warehouses = {item.warehouse} if item.warehouse else set()
        if item.order_id:
            ref_hash = hashlib.sha256(item.order_id.encode()).hexdigest()
            merchants.update(
                session.scalars(
                    select(GoWarehouseOrder.merchant).where(
                        GoWarehouseOrder.order_id == item.order_id
                    )
                ).all()
            )
            merchants.update(
                session.scalars(
                    select(GoWarehouseOperationalRecord.merchant).where(
                        GoWarehouseOperationalRecord.order_ref_hash == ref_hash,
                        GoWarehouseOperationalRecord.merchant.is_not(None),
                    )
                ).all()
            )
            warehouses.update(
                session.scalars(
                    select(GoWarehouseOrder.warehouse).where(
                        GoWarehouseOrder.order_id == item.order_id,
                        GoWarehouseOrder.warehouse.is_not(None),
                    )
                ).all()
            )
        if item.sku:
            sku_merchant, _ = _merchant_from_sku(session, item.sku)
            if sku_merchant:
                merchants.add(sku_merchant)
        merchant_conflicts += len({_normalized(name) for name in merchants}) > 1
        warehouse_conflicts += len({_normalized(name) for name in warehouses}) > 1
    return merchant_conflicts, warehouse_conflicts


def _analyze(session, parsed: ParsedImport, kind: str) -> dict[str, object]:  # type: ignore[no-untyped-def]
    merchant_names: list[str | None]
    merchant_methods: list[str]
    warehouse_names: list[str | None]
    if kind == "orders":
        merchant_results = [_merchant_from_order(session, item) for item in parsed.orders]
        merchant_names = [result[0] for result in merchant_results]
        merchant_methods = [result[1] for result in merchant_results]
        warehouse_names = [_warehouse_from_order(session, item) for item in parsed.orders]
        count = len(parsed.orders)
    elif kind == "inventory":
        merchant_names = [item.merchant for item in parsed.inventory]
        merchant_methods = ["SOURCE_FIELD"] * len(parsed.inventory)
        warehouse_names = [None] * len(parsed.inventory)
        count = len(parsed.inventory)
    else:
        merchant_results = [
            _merchant_from_operational(session, item) for item in parsed.operational
        ]
        merchant_names = [result[0] for result in merchant_results]
        merchant_methods = [result[1] for result in merchant_results]
        warehouse_names = [
            _warehouse_from_operational(session, item) for item in parsed.operational
        ]
        count = len(parsed.operational)
    merchant_conflicts, warehouse_conflicts = _mapping_conflicts(
        session, parsed.orders, parsed.operational
    )
    conflicts = []
    if merchant_conflicts:
        conflicts.append(f"{merchant_conflicts} 筆資料的貨主對照互相衝突")
    if warehouse_conflicts:
        conflicts.append(f"{warehouse_conflicts} 筆資料的倉庫對照互相衝突")
    return {
        "record_count": count,
        "merchant_names": merchant_names,
        "warehouse_names": warehouse_names,
        "unresolved_merchant_count": sum(name is None for name in merchant_names),
        "unresolved_warehouse_count": sum(name is None for name in warehouse_names),
        "detected_merchants": sorted({name for name in merchant_names if name}),
        "detected_warehouses": sorted({name for name in warehouse_names if name}),
        "merchant_detection_summary": dict(Counter(merchant_methods)),
        "conflict_count": merchant_conflicts + warehouse_conflicts,
        "conflicts": conflicts,
    }


def _record_unresolved_products(session, parsed: ParsedImport, kind: str) -> int:  # type: ignore[no-untyped-def]
    unresolved: set[str] = set()
    if kind == "orders":
        for item in parsed.orders:
            if _merchant_from_order(session, item)[0] is None:
                unresolved.update(
                    sku
                    for sku in item.skus
                    if _merchant_from_sku(session, sku)[0] is None
                )
    elif kind not in {"inventory"}:
        for item in parsed.operational:
            if (
                item.sku
                and _merchant_from_operational(session, item)[0] is None
                and _merchant_from_sku(session, item.sku)[0] is None
            ):
                unresolved.add(item.sku)
    now = utc_now()
    for sku in unresolved:
        identifier = hashlib.sha256(sku.encode()).hexdigest()
        item = session.get(GoWarehouseProductMerchantMap, identifier)
        if item is None:
            session.add(
                GoWarehouseProductMerchantMap(
                    id=identifier,
                    sku=sku,
                    status=PENDING,
                    source_kinds_json=[kind],
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        elif item.status == PENDING:
            item.source_kinds_json = sorted({*(item.source_kinds_json or []), kind})
            item.last_seen_at = now
    return len(unresolved)


@router.post("/preview/{kind}")
async def preview_import(
    kind: str,
    _: UploadAccess,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    if kind not in SUPPORTED_KINDS:
        raise HTTPException(status_code=404, detail="不支援的匯入類型。")
    filename, suffix, _ = _read_upload(file)
    content = await file.read()
    parsed = _parse(content, suffix, kind)
    analysis = _analyze(session, parsed, kind)
    pending_product_count = _record_unresolved_products(session, parsed, kind)
    catalog = _catalog_payload(session)
    session.commit()
    return {
        "kind": kind,
        "filename": filename,
        "preview_checksum": _preview_checksum(content, kind),
        **analysis,
        **catalog,
        "requires_merchant_selection": analysis["unresolved_merchant_count"] > 0,
        "requires_warehouse_selection": analysis["unresolved_warehouse_count"] > 0,
        "pending_product_count": pending_product_count,
        "warnings": list(parsed.warnings),
    }


def _ensure_named_master(session, model, name: str, prefix: str):  # type: ignore[no-untyped-def]
    items = session.scalars(select(model)).all()
    existing = _catalog_match(items, name)
    if existing is not None:
        return existing
    item = model(
        code=f"{prefix}-{hashlib.sha256(name.encode()).hexdigest()[:10].upper()}",
        name=name.strip(),
        aliases_json=[],
        status=PENDING,
    )
    session.add(item)
    session.flush()
    return item


def _batch_for_commit(
    session,
    *,
    checksum: str,
    filename: str,
    kind: str,
    count: int,
    merchant,
    warehouse,
    analysis: dict[str, object],
):  # type: ignore[no-untyped-def]
    existing = session.scalar(
        select(GoWarehouseImportBatch).where(GoWarehouseImportBatch.checksum_sha256 == checksum)
    )
    if existing is not None and existing.status == "IMPORTED":
        return existing, True
    if existing is not None:
        session.execute(
            delete(GoWarehouseImportChange).where(GoWarehouseImportChange.batch_id == existing.id)
        )
        batch = existing
        batch.status = "IMPORTED"
        batch.undone_at = None
    else:
        batch = GoWarehouseImportBatch(
            checksum_sha256=checksum,
            source_filename=filename,
            kind=kind,
            record_count=count,
            warning_count=0,
        )
        session.add(batch)
    batch.merchant = merchant.name if merchant is not None else None
    batch.merchant_id = merchant.id if merchant is not None else None
    batch.warehouse_id = warehouse.id if warehouse is not None else None
    batch.confirmed_at = utc_now()
    batch.imported_at = utc_now()
    batch.source_filename = filename
    batch.record_count = count
    batch.detection_json = {
        "unresolved_merchant_count": analysis["unresolved_merchant_count"],
        "unresolved_warehouse_count": analysis["unresolved_warehouse_count"],
        "detected_merchant_count": len(analysis["detected_merchants"]),
        "detected_warehouse_count": len(analysis["detected_warehouses"]),
        "merchant_detection_summary": analysis.get("merchant_detection_summary", {}),
    }
    session.flush()
    return batch, False


def _serialize_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date | datetime) else value


_FIELDS = {
    "order": (
        "id", "import_batch_id", "merchant", "merchant_id", "warehouse", "warehouse_id",
        "order_id", "channel", "platform", "shipping_type", "amount", "urgent",
        "reserved_ship_date", "shipped_at", "order_status", "source_created_at", "imported_at",
    ),
    "inventory": (
        "id", "import_batch_id", "merchant", "merchant_id", "warehouse", "warehouse_id",
        "sku", "product_name", "inventory_type", "quantity", "batch", "expiration_date",
        "status", "available", "allocated", "imported_at",
    ),
    "operational": (
        "id", "import_batch_id", "kind", "occurred_on", "category", "merchant", "merchant_id",
        "warehouse", "warehouse_id", "order_ref_hash", "channel", "status", "planned_quantity",
        "accepted_quantity", "completed_quantity", "shipment_count", "item_count", "imported_at",
    ),
}


def _snapshot(entity_type: str, record) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {field: _serialize_value(getattr(record, field)) for field in _FIELDS[entity_type]}


def _record_change(session, batch_id: str, entity_type: str, record, action: str) -> None:  # type: ignore[no-untyped-def]
    session.add(
        GoWarehouseImportChange(
            batch_id=batch_id,
            entity_type=entity_type,
            entity_id=record.id,
            action=action,
            before_json=None if action == "created" else _snapshot(entity_type, record),
        )
    )


def _resolve_names(session, names: list[str | None], fallback, model, prefix: str):  # type: ignore[no-untyped-def]
    resolved = []
    for name in names:
        if name:
            resolved.append(_ensure_named_master(session, model, name, prefix))
        elif fallback is not None:
            resolved.append(fallback)
        else:
            resolved.append(None)
    return resolved


def _pending_order_payload(
    items: tuple[ParsedOrder, ...], merchant_ids: list[str], warehouse_ids: list[str]
) -> dict[str, object]:
    return {
        "orders": [
            {
                "order_id": item.order_id,
                "channel": item.channel,
                "platform": item.platform,
                "shipping_type": item.shipping_type,
                "amount": item.amount,
                "urgent": item.urgent,
                "reserved_ship_date": _serialize_value(item.reserved_ship_date),
                "shipped_at": _serialize_value(item.shipped_at),
                "order_status": item.order_status,
                "source_created_at": _serialize_value(item.source_created_at),
                "skus": list(item.skus),
            }
            for item in items
        ],
        "merchant_ids": merchant_ids,
        "warehouse_ids": warehouse_ids,
    }


def _restore_pending_orders(payload: dict[str, object]) -> tuple[ParsedOrder, ...]:
    rows = payload.get("orders")
    if not isinstance(rows, list):
        raise HTTPException(status_code=409, detail="待確認批次內容不完整。")
    return tuple(
        ParsedOrder(
            order_id=str(row["order_id"]),
            channel=row.get("channel"),
            platform=row.get("platform"),
            shipping_type=row.get("shipping_type"),
            amount=row.get("amount"),
            urgent=bool(row.get("urgent")),
            reserved_ship_date=(
                date.fromisoformat(str(row["reserved_ship_date"]))
                if row.get("reserved_ship_date")
                else None
            ),
            shipped_at=(
                datetime.fromisoformat(str(row["shipped_at"]))
                if row.get("shipped_at")
                else None
            ),
            order_status=row.get("order_status"),
            source_created_at=(
                datetime.fromisoformat(str(row["source_created_at"]))
                if row.get("source_created_at")
                else None
            ),
            skus=tuple(str(value) for value in row.get("skus", [])),
        )
        for row in rows
        if isinstance(row, dict)
    )


def _complete_pending_imports(session, merchant: MerchantMaster) -> int:  # type: ignore[no-untyped-def]
    pending_imports = session.scalars(
        select(GoWarehousePendingImport).where(
            GoWarehousePendingImport.merchant_id == merchant.id,
            GoWarehousePendingImport.status == "WAITING_APPROVAL",
        )
    ).all()
    completed = 0
    for pending in pending_imports:
        items = _restore_pending_orders(pending.payload_json)
        merchant_ids = pending.payload_json.get("merchant_ids", [])
        warehouse_ids = pending.payload_json.get("warehouse_ids", [])
        if not isinstance(merchant_ids, list) or not isinstance(warehouse_ids, list):
            raise HTTPException(status_code=409, detail="待確認批次歸屬資料不完整。")
        merchants = [session.get(MerchantMaster, str(identifier)) for identifier in merchant_ids]
        warehouses = [session.get(WarehouseMaster, str(identifier)) for identifier in warehouse_ids]
        if (
            len(items) != len(merchants)
            or len(items) != len(warehouses)
            or any(item is None for item in merchants)
            or any(item is None for item in warehouses)
        ):
            raise HTTPException(status_code=409, detail="待確認批次無法還原貨主或倉庫歸屬。")
        analysis = {
            "unresolved_merchant_count": 0,
            "unresolved_warehouse_count": 0,
            "detected_merchants": [merchant.name],
            "detected_warehouses": sorted({item.name for item in warehouses if item}),
            "merchant_detection_summary": {"MANUAL_SELECTION": len(items)},
        }
        batch, duplicate = _batch_for_commit(
            session,
            checksum=pending.checksum_sha256,
            filename=pending.source_filename,
            kind=pending.kind,
            count=pending.record_count,
            merchant=merchant,
            warehouse=(
                warehouses[0]
                if len({item.id for item in warehouses if item}) == 1
                else None
            ),
            analysis=analysis,
        )
        if not duplicate:
            _commit_orders(session, batch, items, merchants, warehouses)
        pending.status = "IMPORTED"
        pending.import_batch_id = batch.id
        pending.resolved_at = utc_now()
        completed += 1
    return completed


@router.post("/request-merchant/orders", status_code=status.HTTP_202_ACCEPTED)
async def request_order_merchant(
    _: UploadAccess,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
    preview_checksum: Annotated[str, Form()],
    merchant_name: Annotated[str, Form(min_length=1, max_length=120)],
    warehouse_id: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    filename, suffix, _ = _read_upload(file)
    content = await file.read()
    if not preview_checksum or preview_checksum != _preview_checksum(content, "orders"):
        raise HTTPException(
            status_code=409,
            detail={"error_code": "PREVIEW_CHANGED", "message": "檔案已變更，請重新預覽。"},
        )
    parsed = _parse(content, suffix, "orders")
    analysis = _analyze(session, parsed, "orders")
    if analysis["conflict_count"]:
        raise HTTPException(
            status_code=409,
            detail={"error_code": "MAPPING_CONFLICT", "message": "資料對照有衝突，請通知管理者。"},
        )
    if not analysis["unresolved_merchant_count"]:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "MERCHANT_ALREADY_RESOLVED",
                "message": "系統已辨識貨主，請直接確認匯入。",
            },
        )
    fallback_warehouse = _active_by_id(session, WarehouseMaster, warehouse_id, "倉庫")
    if analysis["unresolved_warehouse_count"] and fallback_warehouse is None:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "WAREHOUSE_REQUIRED", "message": "請先選擇這批訂單所屬倉庫。"},
        )
    requested_name = merchant_name.strip()
    all_merchants = session.scalars(select(MerchantMaster)).all()
    requested_merchant = _catalog_match(all_merchants, requested_name)
    if requested_merchant is not None and requested_merchant.status == ACTIVE:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "MERCHANT_EXISTS",
                "message": "此貨主已在清單中，請直接選擇後匯入。",
            },
        )
    if requested_merchant is None:
        requested_merchant = MerchantMaster(
            code=f"MER-{hashlib.sha256(requested_name.encode()).hexdigest()[:10].upper()}",
            name=requested_name,
            aliases_json=[],
            status=PENDING,
        )
        session.add(requested_merchant)
        session.flush()
    merchant_names = analysis["merchant_names"]
    warehouse_names = analysis["warehouse_names"]
    assert isinstance(merchant_names, list) and isinstance(warehouse_names, list)
    merchants = _resolve_names(
        session, merchant_names, requested_merchant, MerchantMaster, "MER"
    )
    warehouses = _resolve_names(
        session, warehouse_names, fallback_warehouse, WarehouseMaster, "WH"
    )
    assignments = "|".join(
        f"{merchant.id}:{warehouse.id}"
        for merchant, warehouse in zip(merchants, warehouses, strict=True)
    )
    checksum = hashlib.sha256(content + b"orders" + assignments.encode()).hexdigest()
    existing = session.scalar(
        select(GoWarehousePendingImport).where(
            GoWarehousePendingImport.checksum_sha256 == checksum
        )
    )
    if existing is not None:
        session.rollback()
        return {
            "duplicate": True,
            "request_id": existing.id,
            "status": existing.status,
            "message": "這份訂單的新貨主申請已送出過。",
        }
    pending = GoWarehousePendingImport(
        checksum_sha256=checksum,
        source_filename=filename,
        kind="orders",
        requested_merchant_name=requested_name,
        merchant_id=requested_merchant.id,
        warehouse_id=fallback_warehouse.id if fallback_warehouse else None,
        payload_json=_pending_order_payload(
            parsed.orders,
            [item.id for item in merchants],
            [item.id for item in warehouses],
        ),
        record_count=int(analysis["record_count"]),
        status="WAITING_APPROVAL",
    )
    session.add(pending)
    session.commit()
    return {
        "duplicate": False,
        "request_id": pending.id,
        "status": pending.status,
        "message": "新貨主申請已送出；管理者確認後，這批訂單會自動完成匯入。",
    }


@router.post("/commit/{kind}", status_code=status.HTTP_201_CREATED)
async def commit_import(
    kind: str,
    _: UploadAccess,
    session: SessionDependency,
    file: Annotated[UploadFile, File()],
    preview_checksum: Annotated[str, Form()],
    merchant_id: Annotated[str | None, Form()] = None,
    warehouse_id: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    if kind not in SUPPORTED_KINDS:
        raise HTTPException(status_code=404, detail="不支援的匯入類型。")
    filename, suffix, _ = _read_upload(file)
    content = await file.read()
    if not preview_checksum or preview_checksum != _preview_checksum(content, kind):
        raise HTTPException(
            status_code=409,
            detail={"error_code": "PREVIEW_CHANGED", "message": "檔案已變更，請重新預覽。"},
        )
    parsed = _parse(content, suffix, kind)
    analysis = _analyze(session, parsed, kind)
    if analysis["conflict_count"]:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "MAPPING_CONFLICT",
                "message": "貨主或倉庫對照有衝突，請由管理者先更正主檔。",
            },
        )
    fallback_merchant = _active_by_id(session, MerchantMaster, merchant_id, "貨主")
    fallback_warehouse = _active_by_id(session, WarehouseMaster, warehouse_id, "倉庫")
    if analysis["unresolved_merchant_count"] and fallback_merchant is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "MERCHANT_REQUIRED",
                "message": "仍有資料無法辨識貨主，請從清單選擇。",
            },
        )
    if analysis["unresolved_warehouse_count"] and fallback_warehouse is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "WAREHOUSE_REQUIRED",
                "message": "仍有資料無法辨識倉庫，請從清單選擇。",
            },
        )
    merchant_names = analysis["merchant_names"]
    warehouse_names = analysis["warehouse_names"]
    assert isinstance(merchant_names, list) and isinstance(warehouse_names, list)
    merchants = _resolve_names(session, merchant_names, fallback_merchant, MerchantMaster, "MER")
    warehouses = _resolve_names(session, warehouse_names, fallback_warehouse, WarehouseMaster, "WH")
    assignments = "|".join(
        f"{merchant.id}:{warehouse.id}"
        for merchant, warehouse in zip(merchants, warehouses, strict=True)
    )
    checksum = hashlib.sha256(content + kind.encode() + assignments.encode()).hexdigest()
    count = int(analysis["record_count"])
    batch, duplicate = _batch_for_commit(
        session,
        checksum=checksum,
        filename=filename,
        kind=kind,
        count=count,
        merchant=fallback_merchant,
        warehouse=fallback_warehouse,
        analysis=analysis,
    )
    if duplicate:
        session.rollback()
        return {
            "duplicate": True,
            "batch_id": batch.id,
            "kind": kind,
            "record_count": batch.record_count,
            "message": "這份檔案與歸屬設定已匯入過，沒有重複建立資料。",
        }
    if kind == "orders":
        _commit_orders(session, batch, parsed.orders, merchants, warehouses)
    elif kind == "inventory":
        _commit_inventory(session, batch, parsed.inventory, merchants, warehouses)
    else:
        _commit_operational(session, batch, parsed.operational, merchants, warehouses)
    session.commit()
    return {
        "duplicate": False,
        "batch_id": batch.id,
        "kind": kind,
        "record_count": count,
        "message": f"已確認並匯入 {count} 筆資料。",
    }


def _commit_orders(session, batch, items, merchants, warehouses) -> None:  # type: ignore[no-untyped-def]
    for item, merchant, warehouse in zip(items, merchants, warehouses, strict=True):
        matches = session.scalars(
            select(GoWarehouseOrder)
            .where(GoWarehouseOrder.order_id == item.order_id)
            .order_by(GoWarehouseOrder.imported_at.desc())
        ).all()
        record = matches[0] if matches else None
        for duplicate in matches[1:]:
            _record_change(session, batch.id, "order", duplicate, "deleted")
            session.delete(duplicate)
        values = {
            "import_batch_id": batch.id,
            "merchant": merchant.name,
            "merchant_id": merchant.id,
            "warehouse": warehouse.name,
            "warehouse_id": warehouse.id,
            "order_id": item.order_id,
            "channel": item.channel,
            "platform": item.platform,
            "shipping_type": item.shipping_type,
            "amount": item.amount,
            "urgent": item.urgent,
            "reserved_ship_date": item.reserved_ship_date,
            "shipped_at": item.shipped_at,
            "order_status": item.order_status,
            "source_created_at": item.source_created_at,
        }
        if record is None:
            identifier = hashlib.sha256(item.order_id.encode()).hexdigest()
            record = GoWarehouseOrder(id=identifier, **values)
            session.add(record)
            _record_change(session, batch.id, "order", record, "created")
        else:
            _record_change(session, batch.id, "order", record, "updated")
            for field, value in values.items():
                setattr(record, field, value)


def _commit_inventory(session, batch, items, merchants, warehouses) -> None:  # type: ignore[no-untyped-def]
    for item, merchant, warehouse in zip(items, merchants, warehouses, strict=True):
        key = "|".join(
            [merchant.id, warehouse.id, item.sku, item.batch or "", item.inventory_type or ""]
        )
        identifier = hashlib.sha256(key.encode()).hexdigest()
        record = session.get(GoWarehouseInventory, identifier)
        values = {
            "import_batch_id": batch.id,
            "merchant": merchant.name,
            "merchant_id": merchant.id,
            "warehouse": warehouse.name,
            "warehouse_id": warehouse.id,
            "sku": item.sku,
            "product_name": item.product_name,
            "inventory_type": item.inventory_type,
            "quantity": item.quantity,
            "batch": item.batch,
            "expiration_date": item.expiration_date,
            "status": item.status,
            "available": item.available,
            "allocated": item.allocated,
        }
        if record is None:
            record = GoWarehouseInventory(id=identifier, **values)
            session.add(record)
            _record_change(session, batch.id, "inventory", record, "created")
        else:
            _record_change(session, batch.id, "inventory", record, "updated")
            for field, value in values.items():
                setattr(record, field, value)


def _commit_operational(session, batch, items, merchants, warehouses) -> None:  # type: ignore[no-untyped-def]
    for item, merchant, warehouse in zip(items, merchants, warehouses, strict=True):
        identifier = hashlib.sha256(f"{item.kind}|{item.source_key}".encode()).hexdigest()
        record = session.get(GoWarehouseOperationalRecord, identifier)
        values = {
            "import_batch_id": batch.id,
            "kind": item.kind,
            "occurred_on": item.occurred_on,
            "category": item.category,
            "merchant": merchant.name,
            "merchant_id": merchant.id,
            "warehouse": warehouse.name,
            "warehouse_id": warehouse.id,
            "order_ref_hash": (
                hashlib.sha256(item.order_id.encode()).hexdigest() if item.order_id else None
            ),
            "channel": item.channel,
            "status": item.status,
            "planned_quantity": item.planned_quantity,
            "accepted_quantity": item.accepted_quantity,
            "completed_quantity": item.completed_quantity,
            "shipment_count": item.shipment_count,
            "item_count": item.item_count,
        }
        if record is None:
            record = GoWarehouseOperationalRecord(id=identifier, **values)
            session.add(record)
            _record_change(session, batch.id, "operational", record, "created")
        else:
            _record_change(session, batch.id, "operational", record, "updated")
            for field, value in values.items():
                setattr(record, field, value)


@router.get("/governance/batches")
def list_batches(_: OpsAccess, session: SessionDependency) -> list[dict[str, object]]:
    batches = session.scalars(
        select(GoWarehouseImportBatch).order_by(GoWarehouseImportBatch.imported_at.desc()).limit(50)
    ).all()
    return [
        {
            "id": batch.id,
            "kind": batch.kind,
            "source_filename": batch.source_filename,
            "record_count": batch.record_count,
            "status": batch.status,
            "imported_at": batch.imported_at,
            "merchant_id": batch.merchant_id,
            "warehouse_id": batch.warehouse_id,
        }
        for batch in batches
    ]


@router.patch("/governance/batches/{batch_id}")
def correct_batch(
    batch_id: str, payload: BatchCorrection, _: OpsAccess, session: SessionDependency
) -> dict[str, object]:
    batch = _active_batch(session, batch_id)
    merchant = _active_by_id(session, MerchantMaster, payload.merchant_id, "貨主")
    warehouse = _active_by_id(session, WarehouseMaster, payload.warehouse_id, "倉庫")
    if merchant is None and warehouse is None:
        raise HTTPException(status_code=422, detail="請至少選擇一項要更正的歸屬。")
    for entity_type, model in (
        ("order", GoWarehouseOrder),
        ("inventory", GoWarehouseInventory),
        ("operational", GoWarehouseOperationalRecord),
    ):
        records = session.scalars(select(model).where(model.import_batch_id == batch.id)).all()
        for record in records:
            _record_change(session, batch.id, entity_type, record, "updated")
            if merchant is not None:
                record.merchant = merchant.name
                record.merchant_id = merchant.id
            if warehouse is not None:
                record.warehouse = warehouse.name
                record.warehouse_id = warehouse.id
    if merchant is not None:
        batch.merchant = merchant.name
        batch.merchant_id = merchant.id
    if warehouse is not None:
        batch.warehouse_id = warehouse.id
    session.commit()
    return {"ok": True, "batch_id": batch.id}


def _active_batch(session, batch_id: str) -> GoWarehouseImportBatch:  # type: ignore[no-untyped-def]
    batch = session.get(GoWarehouseImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="找不到此匯入批次。")
    if batch.status != "IMPORTED":
        raise HTTPException(status_code=409, detail="此批次已撤銷。")
    return batch


_MODEL_BY_TYPE = {
    "order": GoWarehouseOrder,
    "inventory": GoWarehouseInventory,
    "operational": GoWarehouseOperationalRecord,
}
_DATE_FIELDS = {"reserved_ship_date", "occurred_on", "expiration_date"}
_DATETIME_FIELDS = {"shipped_at", "source_created_at", "imported_at"}


def _decoded(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in _DATE_FIELDS:
        return date.fromisoformat(value)
    if field in _DATETIME_FIELDS:
        return datetime.fromisoformat(value)
    return value


@router.post("/governance/batches/{batch_id}/undo")
def undo_batch(
    batch_id: str, payload: ConfirmAction, _: OpsAccess, session: SessionDependency
) -> dict[str, object]:
    batch = _active_batch(session, batch_id)
    if payload.confirm != batch_id:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "CONFIRMATION_REQUIRED", "message": "確認內容與批次編號不符。"},
        )
    changes = session.scalars(
        select(GoWarehouseImportChange)
        .where(GoWarehouseImportChange.batch_id == batch.id)
        .order_by(GoWarehouseImportChange.created_at.desc(), GoWarehouseImportChange.id.desc())
    ).all()
    restored = 0
    removed = 0
    for change in changes:
        model = _MODEL_BY_TYPE[change.entity_type]
        record = session.get(model, change.entity_id)
        if change.action == "created":
            if record is not None and record.import_batch_id == batch.id:
                session.delete(record)
                removed += 1
        elif change.action in {"updated", "deleted"} and change.before_json:
            if record is not None and record.import_batch_id != batch.id:
                continue
            values = {field: _decoded(field, value) for field, value in change.before_json.items()}
            if record is None:
                session.add(model(**values))
            else:
                for field, value in values.items():
                    setattr(record, field, value)
            restored += 1
    batch.status = "UNDONE"
    batch.undone_at = utc_now()
    session.commit()
    return {"ok": True, "batch_id": batch.id, "removed": removed, "restored": restored}


@router.post("/governance/cleanup-orders")
def cleanup_duplicate_orders(
    payload: ConfirmAction, _: OpsAccess, session: SessionDependency
) -> dict[str, object]:
    orders = session.scalars(
        select(GoWarehouseOrder).order_by(
            GoWarehouseOrder.order_id, GoWarehouseOrder.imported_at.desc()
        )
    ).all()
    grouped: dict[str, list[GoWarehouseOrder]] = {}
    for order in orders:
        grouped.setdefault(order.order_id, []).append(order)
    duplicates = [item for records in grouped.values() for item in records[1:]]
    if payload.confirm != "MERGE-DUPLICATE-ORDERS":
        return {"dry_run": True, "duplicate_records": len(duplicates)}
    if not duplicates:
        return {"dry_run": False, "duplicate_records": 0, "batch_id": None}
    batch = GoWarehouseImportBatch(
        checksum_sha256=hashlib.sha256(f"cleanup:{utc_now().isoformat()}".encode()).hexdigest(),
        source_filename="system-cleanup",
        kind="cleanup",
        status="IMPORTED",
        detection_json={"operation": "duplicate_order_cleanup"},
        record_count=len(duplicates),
        warning_count=0,
        confirmed_at=utc_now(),
    )
    session.add(batch)
    session.flush()
    for duplicate in duplicates:
        _record_change(session, batch.id, "order", duplicate, "deleted")
        session.delete(duplicate)
    session.commit()
    return {"dry_run": False, "duplicate_records": len(duplicates), "batch_id": batch.id}
