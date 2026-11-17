"""Dynamic Pydantic model generator and constraint validator."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Type, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from samia.models.report import (
    TableValidationSummary,
    ValidationReport,
    ViolationExample,
)
from samia.models.schema import ColumnSchema, NormalizedType, SchemaGraph, TableSchema


class PydanticValidator:
    """
    Validates synthetic data against table schemas using dynamically constructed
    Pydantic models, relational referential integrity checks, and uniqueness constraints.
    """

    def __init__(self, schema_graph: Optional[SchemaGraph] = None) -> None:
        self.schema_graph = schema_graph
        self._models: Dict[str, Type[BaseModel]] = {}

    def build_pydantic_model(self, table: TableSchema) -> Type[BaseModel]:
        """Dynamically construct a Pydantic v2 BaseModel matching the TableSchema."""
        if table.name in self._models:
            return self._models[table.name]

        field_definitions: Dict[str, Any] = {}

        for col_name, col in table.columns.items():
            py_type = self._map_to_python_type(col)
            field_kwargs: Dict[str, Any] = {}

            if col.min_value is not None:
                field_kwargs["ge"] = col.min_value
            if col.max_value is not None:
                field_kwargs["le"] = col.max_value
            if col.min_length is not None:
                field_kwargs["min_length"] = col.min_length
            if col.max_length is not None:
                field_kwargs["max_length"] = col.max_length
            if col.pattern is not None:
                field_kwargs["pattern"] = col.pattern

            if col.nullable:
                # Nullable: Optional with default None
                field_definitions[col_name] = (
                    Optional[py_type],
                    Field(default=None, **field_kwargs),
                )
            else:
                # Required NOT NULL
                field_definitions[col_name] = (
                    py_type,
                    Field(..., **field_kwargs),
                )

        model = create_model(
            f"{table.name.capitalize()}Model",
            __config__=ConfigDict(extra="ignore", arbitrary_types_allowed=True),
            **field_definitions,
        )
        self._models[table.name] = model
        return model

    def _map_to_python_type(self, col: ColumnSchema) -> Type[Any]:
        """Map normalized schema type to standard Python typing type."""
        nt = col.normalized_type
        if nt == NormalizedType.INTEGER:
            return int
        if nt in (NormalizedType.FLOAT, NormalizedType.DECIMAL):
            return float
        if nt == NormalizedType.BOOLEAN:
            return bool
        if nt == NormalizedType.DATE:
            return Union[date, str]
        if nt in (NormalizedType.DATETIME, NormalizedType.TIMESTAMP):
            return Union[datetime, str]
        if nt in (NormalizedType.JSON, NormalizedType.OBJECT):
            return Union[dict, str]
        if nt == NormalizedType.ARRAY:
            return list
        return str

    def validate_dataset(
        self,
        dataset: Dict[str, List[Dict[str, Any]]],
        schema_graph: Optional[SchemaGraph] = None,
        output_report_path: Optional[str | Path] = None,
    ) -> ValidationReport:
        """
        Validate an entire multi-table dataset against schema constraints,
        referential foreign keys, and uniqueness rules.
        """
        start_time = time.perf_counter()
        graph = schema_graph or self.schema_graph
        if not graph:
            raise ValueError("SchemaGraph must be provided to validate multi-table dataset")

        # 1. Build parent primary key lookup index for Foreign Key validation
        pk_index: Dict[str, Dict[str, Set[Any]]] = defaultdict(lambda: defaultdict(set))
        for table_name, rows in dataset.items():
            matched_table = graph.tables.get(table_name)
            if not matched_table:
                # Case-insensitive match fallback
                matched_table = next(
                    (t for t in graph.tables.values() if t.name.lower() == table_name.lower()),
                    None,
                )
            if not matched_table:
                continue

            for row in rows:
                for pk_col in matched_table.primary_keys:
                    if pk_col in row and row[pk_col] is not None:
                        pk_index[matched_table.name.lower()][pk_col.lower()].add(row[pk_col])

        # 2. Validate each table
        report = ValidationReport()

        for table_name, rows in dataset.items():
            matched_table = graph.tables.get(table_name)
            if not matched_table:
                matched_table = next(
                    (t for t in graph.tables.values() if t.name.lower() == table_name.lower()),
                    None,
                )
            if not matched_table:
                continue

            table_summary = self._validate_table_rows(
                table=matched_table,
                rows=rows,
                pk_index=pk_index,
            )
            report.tables[table_name] = table_summary
            report.total_records += table_summary.total_records
            report.valid_records += table_summary.valid_records
            report.invalid_records += table_summary.invalid_records
            report.sample_violations.extend(table_summary.sample_violations)

        report.pass_rate = (
            (report.valid_records / report.total_records * 100.0)
            if report.total_records > 0
            else 100.0
        )
        report.duration_seconds = time.perf_counter() - start_time

        if output_report_path:
            report.save(output_report_path)

        return report

    def _validate_table_rows(
        self,
        table: TableSchema,
        rows: List[Dict[str, Any]],
        pk_index: Dict[str, Dict[str, Set[Any]]],
    ) -> TableValidationSummary:
        """Validate all rows of a single table against Pydantic rules, FKs, and uniqueness."""
        model = self.build_pydantic_model(table)
        summary = TableValidationSummary(table_name=table.name, total_records=len(rows))

        # Track uniqueness
        seen_uniques: Dict[str, Set[Any]] = defaultdict(set)

        for row_idx, row in enumerate(rows):
            row_has_violation = False

            # A. Pydantic Field Validation
            try:
                model.model_validate(row)
            except ValidationError as exc:
                row_has_violation = True
                for err in exc.errors():
                    col_loc = str(err["loc"][0]) if err["loc"] else "unknown"
                    rule = err.get("type", "validation_error")
                    msg = err.get("msg", "Validation error")
                    raw_val = row.get(col_loc)

                    violation = ViolationExample(
                        table_name=table.name,
                        row_index=row_idx,
                        column_name=col_loc,
                        rule=rule,
                        value=raw_val,
                        message=msg,
                    )
                    summary.sample_violations.append(violation)
                    summary.violations_by_column[col_loc] = (
                        summary.violations_by_column.get(col_loc, 0) + 1
                    )
                    summary.violations_by_rule[rule] = (
                        summary.violations_by_rule.get(rule, 0) + 1
                    )

            # B. Custom Column Rule Validations (Enum, Unique, FK)
            for col_name, col in table.columns.items():
                val = row.get(col_name)

                # Null check for NOT NULL columns (already caught by Pydantic if defined)
                if not col.nullable and val is None:
                    continue

                if val is None:
                    continue

                # Enum validation
                if col.enum_values and val not in col.enum_values:
                    row_has_violation = True
                    v = ViolationExample(
                        table_name=table.name,
                        row_index=row_idx,
                        column_name=col_name,
                        rule="enum_constraint",
                        value=val,
                        message=f"Value '{val}' is not in allowed enums: {col.enum_values}",
                    )
                    summary.sample_violations.append(v)
                    summary.violations_by_column[col_name] = (
                        summary.violations_by_column.get(col_name, 0) + 1
                    )
                    summary.violations_by_rule["enum_constraint"] = (
                        summary.violations_by_rule.get("enum_constraint", 0) + 1
                    )

                # Uniqueness check (Primary Key or UNIQUE column)
                if col.is_unique or col.is_primary_key:
                    if val in seen_uniques[col_name]:
                        row_has_violation = True
                        v = ViolationExample(
                            table_name=table.name,
                            row_index=row_idx,
                            column_name=col_name,
                            rule="unique_constraint",
                            value=val,
                            message=f"Duplicate value '{val}' violates unique constraint on column '{col_name}'",
                        )
                        summary.sample_violations.append(v)
                        summary.violations_by_column[col_name] = (
                            summary.violations_by_column.get(col_name, 0) + 1
                        )
                        summary.violations_by_rule["unique_constraint"] = (
                            summary.violations_by_rule.get("unique_constraint", 0) + 1
                        )
                    else:
                        seen_uniques[col_name].add(val)

                # Foreign Key referential integrity
                if col.is_foreign_key and col.foreign_key_ref:
                    parent_tbl, parent_col = col.foreign_key_ref
                    parent_pool = pk_index.get(parent_tbl.lower(), {}).get(parent_col.lower(), set())

                    # Check if foreign key target value exists in parent pool
                    # Note: only validate if parent table was part of dataset
                    if parent_tbl.lower() in pk_index and val not in parent_pool:
                        row_has_violation = True
                        v = ViolationExample(
                            table_name=table.name,
                            row_index=row_idx,
                            column_name=col_name,
                            rule="foreign_key_referential_integrity",
                            value=val,
                            message=f"Foreign key value '{val}' references non-existent parent {parent_tbl}.{parent_col}",
                        )
                        summary.sample_violations.append(v)
                        summary.violations_by_column[col_name] = (
                            summary.violations_by_column.get(col_name, 0) + 1
                        )
                        summary.violations_by_rule["foreign_key_referential_integrity"] = (
                            summary.violations_by_rule.get("foreign_key_referential_integrity", 0) + 1
                        )

            if row_has_violation:
                summary.invalid_records += 1
            else:
                summary.valid_records += 1

        summary.pass_rate = (
            (summary.valid_records / summary.total_records * 100.0)
            if summary.total_records > 0
            else 100.0
        )
        return summary
