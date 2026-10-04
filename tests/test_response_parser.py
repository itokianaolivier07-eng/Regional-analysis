from src.llm.response_parser import parse_json_response


def test_parse_json_response_recovers_truncated_object():
    raw = '''```json {
        "lot_id": "L1-Corse-du-Sud-2026-08-0006",
        "document_ids": [
            "42b5a2faf8d0139713b5f7d0d7431c6f312f7b7c2963a75844876635d31c6ab8",
            "6280e69d46420a4d183548ee17650e961c02fd42fd93232a043c2965de15f6b3",
            "e59d5aa5ec858eab805c2a18e5d8e584209b2d79ec324fe461c703581d5dd46c",
            "adc40'''

    data = parse_json_response(raw)

    assert data["lot_id"] == "L1-Corse-du-Sud-2026-08-0006"
    assert data["document_ids"] == [
        "42b5a2faf8d0139713b5f7d0d7431c6f312f7b7c2963a75844876635d31c6ab8",
        "6280e69d46420a4d183548ee17650e961c02fd42fd93232a043c2965de15f6b3",
        "e59d5aa5ec858eab805c2a18e5d8e584209b2d79ec324fe461c703581d5dd46c",
    ]


def test_parse_json_response_handles_trailing_commas():
    raw = '''```json {
        "lot_id": "L1-Corse-du-Sud-2026-08-0007",
        "document_ids": [
            "a",
            "b",
        ],
        "status": "ok"
    }```'''

    data = parse_json_response(raw)

    assert data["lot_id"] == "L1-Corse-du-Sud-2026-08-0007"
    assert data["document_ids"] == ["a", "b"]
    assert data["status"] == "ok"
