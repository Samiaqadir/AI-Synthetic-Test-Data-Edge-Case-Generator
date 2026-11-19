"""SQL DDL Parser for extracting multi-table schemas, constraints, and DAG dependencies."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import sqlparse
from sqlparse.sql import Comment, Identifier, Parenthesis, Statement
from sqlparse.tokens import Keyword, Name, Punctuation, Whitespace

from samia.models.schema import (
    ColumnSchema,
    ForeignKeyConstraint,
    NormalizedType,
    SchemaGraph,
    SchemaParseError,
    TableSchema,
)


def clean_identifier(name: str) -> str:
    """Strip quotes, backticks, brackets, and whitespace from SQL identifiers."""
    name = name.strip()
    return re.sub(r"^[`\"'\[]|[`\"'\]]$", "", name).strip()


def split_clauses(body: str) -> List[str]:
    """
    Split table definition body into comma-separated column/constraint clauses,
    respecting nested parentheses and quoted strings.
    """
    clauses: List[str] = []
    current: List[str] = []
    depth = 0
    in_single_quote = False
    in_double_quote = False

    for char in body:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
        elif char == "(" and not in_single_quote and not in_double_quote:
            depth += 1
            current.append(char)
        elif char == ")" and not in_single_quote and not in_double_quote:
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0 and not in_single_quote and not in_double_quote:
            clause = "".join(current).strip()
            if clause:
                clauses.append(clause)
            current = []
        else:
            current.append(char)

    last = "".join(current).strip()
    if last:
        clauses.append(last)

    return clauses


class SQLDDLParser:
    """
    Parses multi-table SQL DDL schemas into structured TableSchema objects
    and builds a dependency DAG (SchemaGraph).
    """

    TABLE_NAME_PATTERN = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)",
        re.IGNORECASE,
    )
    TABLE_PK_PATTERN = re.compile(
        r"^(?:CONSTRAINT\s+[^\s]+\s+)?PRIMARY\s+KEY\s*\(([^)]+)\)",
        re.IGNORECASE,
    )
    TABLE_FK_PATTERN = re.compile(
        r"^(?:CONSTRAINT\s+[^\s]+\s+)?FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+([^\s(]+)\s*\(([^)]+)\)",
        re.IGNORECASE,
    )
    TABLE_UQ_PATTERN = re.compile(
        r"^(?:CONSTRAINT\s+[^\s]+\s+)?UNIQUE(?:\s+KEY|\s+INDEX)?\s*\(([^)]+)\)",
        re.IGNORECASE,
    )
    INLINE_FK_PATTERN = re.compile(
        r"\bREFERENCES\s+([^\s(]+)\s*\(([^)]+)\)",
        re.IGNORECASE,
    )
    TYPE_WITH_ARGS_PATTERN = re.compile(
        r"^([A-Za-z0-9_]+)(?:\s*\(\s*(\d+)(?:\s*,\s*(\d+))?\s*\))?",
    )
    CHECK_BETWEEN_PATTERN = re.compile(
        r"\bCHECK\s*\(\s*[^\s]+\s*(?:BETWEEN\s+(\d+(?:\.\d+)?)\s+AND\s+(\d+(?:\.\d+)?)|>=\s*(\d+(?:\.\d+)?)\s+AND\s+[^\s]+\s*<=\s*(\d+(?:\.\d+)?))\s*\)",
        re.IGNORECASE,
    )
    CHECK_MIN_PATTERN = re.compile(
        r"\bCHECK\s*\(\s*[^\s]+\s*(?:>=|>)\s*(\d+(?:\.\d+)?)\s*\)",
        re.IGNORECASE,
    )
    CHECK_MAX_PATTERN = re.compile(
        r"\bCHECK\s*\(\s*[^\s]+\s*(?:<=|<)\s*(\d+(?:\.\d+)?)\s*\)",
        re.IGNORECASE,
    )
    CHECK_IN_PATTERN = re.compile(
        r"\bCHECK\s*\(\s*[^\s]+\s+IN\s*\(([^)]+)\)\s*\)",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.warnings: List[str] = []

    def parse_file(self, file_path: str | Path, strict: bool = False) -> SchemaGraph:
        """Parse SQL DDL from a file."""
        content = Path(file_path).read_text(encoding="utf-8")
        return self.parse(content, strict=strict)

    def parse(self, sql_content: str, strict: bool = False) -> SchemaGraph:
        """Parse raw SQL DDL string into a SchemaGraph with all tables and relationships."""
        self.warnings = []
        graph = SchemaGraph()
        statements = sqlparse.parse(sql_content)

        found_create = False
        for stmt in statements:
            # We care about CREATE TABLE statements
            stmt_str = str(stmt).strip()
            if not re.search(r"CREATE\s+TABLE", stmt_str, re.IGNORECASE):
                continue

            found_create = True
            table = self._parse_create_table(stmt, stmt_str)
            if table:
                graph.add_table(table)

        if strict and not found_create and sql_content.strip():
            raise SchemaParseError("No valid CREATE TABLE statements found in SQL content")

        return graph

    def _parse_create_table(self, stmt: Statement, stmt_str: str) -> Optional[TableSchema]:
        """Parse a single CREATE TABLE statement."""
        # Validate balanced parentheses
        if stmt_str.count("(") != stmt_str.count(")"):
            raise SchemaParseError("Unbalanced parentheses in CREATE TABLE statement", stmt_str)

        # Find table name
        name_match = self.TABLE_NAME_PATTERN.search(stmt_str)
        if not name_match:
            raise SchemaParseError("Could not extract valid table name from CREATE TABLE statement", stmt_str)

        raw_table_name = name_match.group(1).strip()
        table_name = clean_identifier(raw_table_name)
        if not table_name or not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
            raise SchemaParseError(f"Invalid table identifier '{table_name}' in CREATE TABLE statement", stmt_str)

        table = TableSchema(name=table_name)

        # Extract parenthesized body containing columns and constraints
        body = self._extract_body(stmt, stmt_str)
        if not body:
            raise SchemaParseError(f"Table '{table_name}' has an empty or unclosed body definition", stmt_str)

        clauses = split_clauses(body)
        if not clauses:
            raise SchemaParseError(f"Table '{table_name}' does not contain any column definitions", stmt_str)

        # First pass: table-level constraints and column definitions
        for raw_clause in clauses:
            clause = raw_clause.strip()
            if not clause:
                continue

            # Table-level Primary Key
            pk_match = self.TABLE_PK_PATTERN.search(clause)
            if pk_match:
                cols = [clean_identifier(c) for c in pk_match.group(1).split(",")]
                is_single = len(cols) == 1
                for col in cols:
                    if col not in table.primary_keys:
                        table.primary_keys.append(col)
                    if col in table.columns:
                        table.columns[col].is_primary_key = True
                        table.columns[col].nullable = False
                        table.columns[col].is_unique = is_single
                continue

            # Table-level Foreign Key
            fk_match = self.TABLE_FK_PATTERN.search(clause)
            if fk_match:
                child_cols = [clean_identifier(c) for c in fk_match.group(1).split(",")]
                parent_table = clean_identifier(fk_match.group(2))
                parent_cols = [clean_identifier(c) for c in fk_match.group(3).split(",")]
                table.foreign_key_constraints.append(
                    ForeignKeyConstraint(
                        child_columns=child_cols,
                        parent_table=parent_table,
                        parent_columns=parent_cols,
                    )
                )
                for child_col, parent_col in zip(child_cols, parent_cols):
                    table.foreign_keys[child_col] = (parent_table, parent_col)
                    if child_col in table.columns:
                        table.columns[child_col].is_foreign_key = True
                        table.columns[child_col].foreign_key_ref = (parent_table, parent_col)
                continue

            # Table-level Unique Constraint
            uq_match = self.TABLE_UQ_PATTERN.search(clause)
            if uq_match:
                cols = [clean_identifier(c) for c in uq_match.group(1).split(",")]
                table.unique_constraints.append(cols)
                if len(cols) == 1 and cols[0] in table.columns:
                    table.columns[cols[0]].is_unique = True
                continue

            # Skip standalone table-level CHECK or INDEX definitions if not on column
            if re.match(r"^(?:CONSTRAINT\s+[^\s]+\s+)?CHECK\b", clause, re.IGNORECASE):
                continue

            # Column definition
            col = self._parse_column_clause(clause, table)
            if col:
                table.add_column(col)

        # Re-sync any table-level primary keys or foreign keys parsed before columns
        is_single_pk = len(table.primary_keys) == 1
        for pk in table.primary_keys:
            if pk in table.columns:
                table.columns[pk].is_primary_key = True
                table.columns[pk].nullable = False
                table.columns[pk].is_unique = is_single_pk

        for col_name, ref in table.foreign_keys.items():
            if col_name in table.columns:
                table.columns[col_name].is_foreign_key = True
                table.columns[col_name].foreign_key_ref = ref

        if not table.columns:
            raise SchemaParseError(f"Table '{table_name}' does not contain any valid column definitions", stmt_str)

        return table

    def _extract_body(self, stmt: Statement, stmt_str: str) -> Optional[str]:
        """Extract the content between the outermost parentheses in CREATE TABLE."""
        # Check sqlparse Parenthesis token first
        for token in stmt.tokens:
            if isinstance(token, Parenthesis):
                val = token.value.strip()
                if val.startswith("(") and val.endswith(")"):
                    return val[1:-1].strip()

        # Fallback to regex finding the outermost matching parentheses
        first_paren = stmt_str.find("(")
        last_paren = stmt_str.rfind(")")
        if first_paren != -1 and last_paren != -1 and last_paren > first_paren:
            return stmt_str[first_paren + 1 : last_paren].strip()

        return None

    def _parse_column_clause(self, clause: str, table: TableSchema) -> Optional[ColumnSchema]:
        """Parse an individual column definition clause."""
        tokens = clause.strip().split()
        if not tokens:
            return None

        raw_col_name = tokens[0]
        col_name = clean_identifier(raw_col_name)

        # Remaining string contains type and modifiers
        remaining = clause[len(raw_col_name):].strip()
        if not remaining:
            return ColumnSchema(name=col_name)

        # Extract type name and optional precision/length
        type_match = self.TYPE_WITH_ARGS_PATTERN.search(remaining)
        if not type_match:
            raw_type = tokens[1] if len(tokens) > 1 else "VARCHAR"
            max_len = None
            precision = None
            scale = None
        else:
            base_type = type_match.group(1).upper()
            arg1 = type_match.group(2)
            arg2 = type_match.group(3)

            raw_type = type_match.group(0)
            max_len = int(arg1) if arg1 and not arg2 and base_type in ("VARCHAR", "CHAR", "TEXT", "NVARCHAR") else None
            precision = int(arg1) if arg1 and arg2 else None
            scale = int(arg2) if arg2 else None

        # Check for column-level ENUM('val1', 'val2', ...)
        enum_col_m = re.search(r"\bENUM\s*\(([^)]+)\)", remaining, re.IGNORECASE)
        if enum_col_m:
            raw_type = enum_col_m.group(0)
            normalized_type = NormalizedType.STRING
        else:
            normalized_type = NormalizedType.from_sql_type(raw_type)

        if normalized_type == NormalizedType.UNKNOWN:
            self.warnings.append(
                f"Table '{table.name}', column '{col_name}': unsupported or unknown SQL type '{raw_type}'. Defaulting to string."
            )

        # Constraints analysis on remaining text
        upper_rem = remaining.upper()

        is_pk = bool(re.search(r"\bPRIMARY\s+KEY\b", upper_rem))
        is_uq = bool(re.search(r"\bUNIQUE\b", upper_rem))
        has_not_null = bool(re.search(r"\bNOT\s+NULL\b", upper_rem))
        nullable = not has_not_null and not is_pk

        # Auto-increment or SERIAL implies integer primary key not null
        if "SERIAL" in raw_type.upper() or "AUTO_INCREMENT" in upper_rem:
            is_pk = is_pk or bool("SERIAL" in raw_type.upper())
            nullable = False

        # Inline Foreign Key
        fk_match = self.INLINE_FK_PATTERN.search(remaining)
        is_fk = False
        fk_ref = None
        if fk_match:
            is_fk = True
            parent_tbl = clean_identifier(fk_match.group(1))
            parent_col = clean_identifier(fk_match.group(2))
            fk_ref = (parent_tbl, parent_col)
            table.foreign_keys[col_name] = fk_ref
            table.foreign_key_constraints.append(
                ForeignKeyConstraint(
                    child_columns=[col_name],
                    parent_table=parent_tbl,
                    parent_columns=[parent_col],
                )
            )

        # Check for CHECK constraints
        min_val: Optional[float] = None
        max_val: Optional[float] = None
        enum_vals: Optional[List[Any]] = None

        if enum_col_m:
            enum_raw = enum_col_m.group(1).split(",")
            enum_vals = [clean_identifier(v) for v in enum_raw]

        between_m = self.CHECK_BETWEEN_PATTERN.search(remaining)
        if between_m:
            v1 = between_m.group(1) or between_m.group(3)
            v2 = between_m.group(2) or between_m.group(4)
            min_val = float(v1) if v1 else None
            max_val = float(v2) if v2 else None
        else:
            min_m = self.CHECK_MIN_PATTERN.search(remaining)
            if min_m:
                min_val = float(min_m.group(1))
            max_m = self.CHECK_MAX_PATTERN.search(remaining)
            if max_m:
                max_val = float(max_m.group(1))

        in_m = self.CHECK_IN_PATTERN.search(remaining)
        if in_m:
            enum_raw = in_m.group(1).split(",")
            enum_vals = [clean_identifier(v) for v in enum_raw]

        # Extract DEFAULT
        default_m = re.search(r"\bDEFAULT\s+([^,\s]+)", remaining, re.IGNORECASE)
        default_val = clean_identifier(default_m.group(1)) if default_m else None

        return ColumnSchema(
            name=col_name,
            raw_type=raw_type,
            normalized_type=normalized_type,
            nullable=nullable,
            is_primary_key=is_pk,
            is_unique=is_uq or is_pk,
            is_foreign_key=is_fk,
            foreign_key_ref=fk_ref,
            min_value=min_val,
            max_value=max_val,
            max_length=max_len,
            enum_values=enum_vals,
            default=default_val,
            precision=precision,
            scale=scale,
        )
