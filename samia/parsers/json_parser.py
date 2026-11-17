"""JSON Schema Parser for extracting fields, types, constraints, and validation patterns."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from samia.models.schema import (
    ColumnSchema,
    JSONPropertySchema,
    NormalizedType,
    TableSchema,
)


class JSONSchemaParser:
    """
    Parses standard JSON Schema (Draft 4/7/2020-12) specifications into
    JSONPropertySchema trees and converts them into TableSchema objects.
    """

    def parse_file(self, file_path: str | Path) -> Dict[str, JSONPropertySchema]:
        """Parse JSON schema from a .json or .yaml/.yml file."""
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() in (".yaml", ".yml"):
            raw_schema = yaml.safe_load(content)
        else:
            raw_schema = json.loads(content)
        return self.parse(raw_schema)

    def parse(self, schema: Union[str, Dict[str, Any]]) -> Dict[str, JSONPropertySchema]:
        """
        Parse raw JSON schema dictionary or JSON string.
        Returns a dictionary mapping field name to JSONPropertySchema.
        """
        if isinstance(schema, str):
            schema = json.loads(schema)

        if not isinstance(schema, dict):
            raise ValueError(f"Invalid JSON Schema: expected dictionary, got {type(schema).__name__}")

        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))

        result: Dict[str, JSONPropertySchema] = {}
        for prop_name, prop_def in properties.items():
            is_req = prop_name in required_fields
            result[prop_name] = self._parse_property(prop_name, prop_def, required=is_req)

        return result

    def _parse_property(
        self,
        name: str,
        prop_def: Dict[str, Any],
        required: bool = False,
    ) -> JSONPropertySchema:
        """Recursively parses a single property definition."""
        raw_type = prop_def.get("type", "string")
        nullable = False

        # Handle type arrays like ["string", "null"]
        if isinstance(raw_type, list):
            nullable = "null" in raw_type
            filtered = [t for t in raw_type if t != "null"]
            clean_type = filtered[0] if filtered else "string"
        else:
            clean_type = str(raw_type)

        fmt = prop_def.get("format")
        normalized_type = NormalizedType.from_json_type(clean_type, fmt)

        # Min / Max values (handling exclusive bounds)
        min_val = prop_def.get("minimum")
        if min_val is None and "exclusiveMinimum" in prop_def:
            ex_min = prop_def["exclusiveMinimum"]
            min_val = ex_min + 1 if isinstance(ex_min, (int, float)) else None

        max_val = prop_def.get("maximum")
        if max_val is None and "exclusiveMaximum" in prop_def:
            ex_max = prop_def["exclusiveMaximum"]
            max_val = ex_max - 1 if isinstance(ex_max, (int, float)) else None

        min_len = prop_def.get("minLength")
        max_len = prop_def.get("maxLength")
        pattern = prop_def.get("pattern")
        enum_vals = prop_def.get("enum")
        default = prop_def.get("default")
        desc = prop_def.get("description")

        # Nested items for arrays
        items_schema: Optional[JSONPropertySchema] = None
        if clean_type == "array" and "items" in prop_def:
            items_def = prop_def["items"]
            if isinstance(items_def, dict):
                items_schema = self._parse_property("item", items_def, required=True)

        # Nested properties for objects
        nested_props: Optional[Dict[str, JSONPropertySchema]] = None
        if clean_type == "object" and "properties" in prop_def:
            nested_props = {}
            nested_required = set(prop_def.get("required", []))
            for sub_name, sub_def in prop_def["properties"].items():
                nested_props[sub_name] = self._parse_property(
                    sub_name, sub_def, required=sub_name in nested_required
                )

        return JSONPropertySchema(
            name=name,
            normalized_type=normalized_type,
            raw_type=clean_type,
            required=required and not nullable,
            format=fmt,
            min_value=float(min_val) if min_val is not None else None,
            max_value=float(max_val) if max_val is not None else None,
            min_length=int(min_len) if min_len is not None else None,
            max_length=int(max_len) if max_len is not None else None,
            pattern=pattern,
            enum_values=enum_vals,
            default=default,
            items=items_schema,
            properties=nested_props,
            description=desc,
        )

    def to_table_schema(
        self,
        entity_name: str,
        schema: Union[str, Dict[str, Any]],
    ) -> TableSchema:
        """
        Converts a top-level JSON Schema into a TableSchema representation
        for unified generation and validation pipeline processing.
        """
        parsed_props = self.parse(schema)
        table = TableSchema(name=entity_name)

        for prop_name, prop in parsed_props.items():
            col = ColumnSchema(
                name=prop.name,
                raw_type=prop.raw_type,
                normalized_type=prop.normalized_type,
                nullable=not prop.required,
                min_value=prop.min_value,
                max_value=prop.max_value,
                min_length=prop.min_length,
                max_length=prop.max_length,
                pattern=prop.pattern,
                enum_values=prop.enum_values,
                default=prop.default,
                description=prop.description,
            )
            # Detect primary key heuristic (e.g. id, uuid)
            if prop_name.lower() in ("id", f"{entity_name.lower()}_id"):
                col.is_primary_key = True
                col.is_unique = True
                col.nullable = False

            table.add_column(col)

        return table
