from kontiki_tui.components.services import apply_service_field_filter

FULL_ID = "aabbccddeeff001122334455"
SHORT_ID = "aabbccddeeff"


def _row(**overrides):
    row = {
        "service_name": "orders",
        "instance_id": SHORT_ID,
        "status": "degraded",
        "host": "host-a",
        "service_version": "1.2.0",
        "kontiki_version": "1.9.0",
        "metadata": {"instance_id": FULL_ID},
    }
    row.update(overrides)
    return row


ROWS = [
    _row(),
    _row(
        service_name="billing",
        instance_id="112233445566",
        status="active",
        host="host-b",
        service_version="2.0.0",
        kontiki_version="1.10.0",
        metadata={"instance_id": "11223344556677889900aabb"},
    ),
]


def _names(rows):
    return [row["service_name"] for row in rows]


def test_all_or_empty_value_keeps_every_row():
    assert apply_service_field_filter(ROWS, "all", "orders") == ROWS
    assert apply_service_field_filter(ROWS, "service_name", "") == ROWS
    assert apply_service_field_filter(ROWS, "", "orders") == ROWS


def test_service_name_substring_is_case_insensitive():
    out = apply_service_field_filter(ROWS, "service_name", "ORD")
    assert _names(out) == ["orders"]


def test_status_matches_raw_registry_value():
    out = apply_service_field_filter(ROWS, "status", "degrad")
    assert _names(out) == ["orders"]
    assert apply_service_field_filter(ROWS, "status", "🟠") == []


def test_instance_id_matches_short_id_and_full_uuid():
    by_short = apply_service_field_filter(ROWS, "instance_id", "aabbccdd")
    by_full = apply_service_field_filter(ROWS, "instance_id", "001122334455")
    assert _names(by_short) == ["orders"]
    assert _names(by_full) == ["orders"]


def test_host_and_version():
    by_host = apply_service_field_filter(ROWS, "host", "host-b")
    by_version = apply_service_field_filter(ROWS, "service_version", "2.0.0")
    by_kontiki = apply_service_field_filter(ROWS, "kontiki_version", "1.10")
    assert _names(by_host) == ["billing"]
    assert _names(by_version) == ["billing"]
    assert _names(by_kontiki) == ["billing"]


def test_missing_kontiki_version_does_not_match():
    rows = [
        _row(kontiki_version=""),
        _row(service_name="billing", kontiki_version="1.10.0"),
    ]
    assert _names(apply_service_field_filter(rows, "kontiki_version", "1.10")) == [
        "billing"
    ]
