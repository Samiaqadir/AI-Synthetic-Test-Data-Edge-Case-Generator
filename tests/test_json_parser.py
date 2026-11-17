"""Unit tests for JSON Schema Parser."""

import pytest

from samia.models.schema import NormalizedType
from samia.parsers.json_parser import JSONSchemaParser


def test_parse_json_schema_properties():
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Account",
        "type": "object",
        "required": ["account_id", "email"],
        "properties": {
            "account_id": {
                "type": "integer",
                "minimum": 1,
                "maximum": 999999
            },
            "email": {
                "type": "string",
                "format": "email",
                "maxLength": 120
            },
            "username": {
                "type": "string",
                "minLength": 3,
                "maxLength": 30,
                "pattern": "^[a-zA-Z0-9_]+$"
            },
            "balance": {
                "type": "number",
                "minimum": 0.0
            },
            "role": {
                "type": "string",
                "enum": ["admin", "member", "guest"]
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"}
            }
        }
    }

    parser = JSONSchemaParser()
    props = parser.parse(schema)

    assert len(props) == 6
    assert props["account_id"].required is True
    assert props["account_id"].min_value == 1.0
    assert props["account_id"].max_value == 999999.0
    assert props["account_id"].normalized_type == NormalizedType.INTEGER

    assert props["email"].required is True
    assert props["email"].format == "email"
    assert props["email"].max_length == 120
    assert props["email"].normalized_type == NormalizedType.EMAIL

    assert props["username"].min_length == 3
    assert props["username"].max_length == 30
    assert props["username"].pattern == "^[a-zA-Z0-9_]+$"

    assert props["role"].enum_values == ["admin", "member", "guest"]
    assert props["tags"].normalized_type == NormalizedType.ARRAY
    assert props["tags"].items.normalized_type == NormalizedType.STRING


def test_to_table_schema_conversion():
    schema = {
        "title": "Device",
        "type": "object",
        "required": ["id", "mac_address"],
        "properties": {
            "id": {"type": "integer"},
            "mac_address": {"type": "string", "maxLength": 17}
        }
    }
    parser = JSONSchemaParser()
    table = parser.to_table_schema("devices", schema)

    assert table.name == "devices"
    assert "id" in table.columns
    assert table.columns["id"].is_primary_key is True
    assert table.columns["id"].nullable is False
    assert table.columns["mac_address"].max_length == 17
