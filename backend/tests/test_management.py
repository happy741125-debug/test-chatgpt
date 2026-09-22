from __future__ import annotations

from sqlalchemy import func, select

from app.models import ManagementRecordAudit

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def _payload(*, version: int = 1, capacity_summary: str = "A 倉目前有 100 個板位"):
    return {
        "source_code": "OPS_MASTER_CHAT_2026_09",
        "source_name": "營運管理對話",
        "source_type": "CHAT_SESSION",
        "authority_scope": "管理定義與人工觀察；系統事實仍須另行驗證",
        "source_url": "https://example.com/shared-operations-chat",
        "source_version": version,
        "records": [
            {
                "source_record_key": "capacity-a-pallets",
                "module": "CAPACITY",
                "title": "A 倉板位容量",
                "summary": capacity_summary,
                "subject_type": "WAREHOUSE",
                "subject_key": "WAREHOUSE_A",
                "fact_status": "USER_REPORTED",
                "observed_at": "2026-09-21T12:00:00+08:00",
                "evidence_ref": "shared-chat#prompt-11",
                "payload": {"capacity_unit": "PALLET", "total": 100},
            },
            {
                "source_record_key": "issue-a-space",
                "module": "ISSUE",
                "title": "A 倉空間利用待改善",
                "summary": "低頻物品占用主要作業區。",
                "subject_type": "WAREHOUSE_ZONE",
                "subject_key": "WAREHOUSE_A_ZONE_1",
                "fact_status": "USER_REPORTED",
                "evidence_ref": "shared-chat#prompt-9",
                "payload": {"impact": "CAPACITY"},
            },
            {
                "source_record_key": "person-manager-a",
                "module": "PEOPLE",
                "title": "主管甲",
                "summary": "待透過訪談確認其跨部門協作與帶人意願。",
                "subject_type": "PERSON",
                "subject_key": "PERSON_MANAGER_A",
                "fact_status": "SENSITIVE_OBSERVATION",
                "sensitivity": "INTERNAL",
                "evidence_ref": "shared-chat#prompt-7",
                "payload": {"current_role": "倉別主管", "needs_validation": True},
            },
        ],
    }


def test_management_endpoints_require_admin_token(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context

    assert client.get("/api/v1/management/overview").status_code == 403
    assert client.get("/api/v1/management/records").status_code == 403
    assert client.get("/api/v1/management/people").status_code == 403
    assert client.post("/api/v1/management/imports", json=_payload()).status_code == 403


def test_initial_import_is_traceable_and_people_stay_private(test_context) -> None:  # type: ignore[no-untyped-def]
    client, database, _ = test_context

    imported = client.post(
        "/api/v1/management/imports", headers=OPS_HEADERS, json=_payload()
    )

    assert imported.status_code == 200
    assert imported.json()["created"] == 3
    overview = client.get("/api/v1/management/overview", headers=OPS_HEADERS).json()
    assert overview["total_records"] == 3
    assert overview["private_records"] == 1
    assert overview["by_module"]["CAPACITY"] == 1
    assert overview["by_module"]["PEOPLE"] == 1

    general = client.get("/api/v1/management/records", headers=OPS_HEADERS)
    assert general.status_code == 200
    assert {item["module"] for item in general.json()} == {"CAPACITY", "ISSUE"}
    assert all(item["sensitivity"] != "PRIVATE_MANAGEMENT" for item in general.json())

    private_people = client.get("/api/v1/management/people", headers=OPS_HEADERS)
    assert private_people.status_code == 200
    assert private_people.json()[0]["title"] == "主管甲"
    assert private_people.json()[0]["sensitivity"] == "PRIVATE_MANAGEMENT"

    with database.session_factory() as session:
        assert session.scalar(select(func.count(ManagementRecordAudit.id))) == 3


def test_generic_endpoint_refuses_people_module(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context
    client.post("/api/v1/management/imports", headers=OPS_HEADERS, json=_payload())

    response = client.get(
        "/api/v1/management/records?module=PEOPLE", headers=OPS_HEADERS
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == (
        "PRIVATE_MODULE_REQUIRES_EXPLICIT_ENDPOINT"
    )


def test_identical_import_is_idempotent(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context
    first = client.post(
        "/api/v1/management/imports", headers=OPS_HEADERS, json=_payload()
    )
    second = client.post(
        "/api/v1/management/imports", headers=OPS_HEADERS, json=_payload()
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["unchanged"] == 3
    assert client.get(
        "/api/v1/management/overview", headers=OPS_HEADERS
    ).json()["total_records"] == 3


def test_same_version_conflict_is_not_silently_overwritten(test_context) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = test_context
    client.post("/api/v1/management/imports", headers=OPS_HEADERS, json=_payload())

    response = client.post(
        "/api/v1/management/imports",
        headers=OPS_HEADERS,
        json=_payload(capacity_summary="同版本卻出現不同數字"),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "MANAGEMENT_RECORD_VERSION_CONFLICT"
    records = client.get("/api/v1/management/records", headers=OPS_HEADERS).json()
    capacity = next(item for item in records if item["module"] == "CAPACITY")
    assert capacity["summary"] == "A 倉目前有 100 個板位"


def test_higher_source_version_updates_record_and_writes_audit(test_context) -> None:  # type: ignore[no-untyped-def]
    client, database, _ = test_context
    client.post("/api/v1/management/imports", headers=OPS_HEADERS, json=_payload())

    updated = client.post(
        "/api/v1/management/imports",
        headers=OPS_HEADERS,
        json=_payload(version=2, capacity_summary="A 倉複核後為 104 個板位"),
    )

    assert updated.status_code == 200
    assert updated.json()["updated"] == 3
    records = client.get("/api/v1/management/records", headers=OPS_HEADERS).json()
    capacity = next(item for item in records if item["module"] == "CAPACITY")
    assert capacity["source_version"] == 2
    assert capacity["summary"] == "A 倉複核後為 104 個板位"
    with database.session_factory() as session:
        assert session.scalar(select(func.count(ManagementRecordAudit.id))) == 6
