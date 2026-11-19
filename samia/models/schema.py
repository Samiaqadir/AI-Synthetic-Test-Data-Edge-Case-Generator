"""Data models representing schemas, columns, tables, and relational graphs."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class NormalizedType(str, Enum):
    """Normalized data types supported across SQL and JSON schema."""
    INTEGER = "integer"
    FLOAT = "float"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    STRING = "string"
    TEXT = "text"
    DATE = "date"
    DATETIME = "datetime"
    TIMESTAMP = "timestamp"
    UUID = "uuid"
    EMAIL = "email"
    JSON = "json"
    ARRAY = "array"
    OBJECT = "object"
    UNKNOWN = "unknown"

    @classmethod
    def from_sql_type(cls, sql_type: str) -> "NormalizedType":
        """Map raw SQL type string to NormalizedType."""
        clean = sql_type.strip().upper()
        if re.search(r"\b(INT|INTEGER|SERIAL|TINYINT|BIGINT|SMALLINT|INT2|INT4|INT8)\b", clean):
            return cls.INTEGER
        if re.search(r"\b(DECIMAL|NUMERIC|MONEY)\b", clean):
            return cls.DECIMAL
        if re.search(r"\b(FLOAT|DOUBLE|REAL)\b", clean):
            return cls.FLOAT
        if re.search(r"\b(BOOL|BOOLEAN)\b", clean):
            return cls.BOOLEAN
        if re.search(r"\bUUID\b", clean):
            return cls.UUID
        if re.search(r"^\s*DATE\b", clean):
            return cls.DATE
        if re.search(r"\b(DATETIME|TIMESTAMP)\b", clean) or re.search(r"\bTIME\b", clean):
            # Guard against INTERVAL containing DAY TO SECOND or TIME
            if "INTERVAL" in clean:
                return cls.UNKNOWN
            return cls.DATETIME
        if re.search(r"\b(TEXT|CLOB|BLOB)\b", clean):
            return cls.TEXT
        if re.search(r"\b(CHAR|VARCHAR|STRING|NVARCHAR)\b", clean):
            return cls.STRING
        if re.search(r"\b(JSON|JSONB)\b", clean):
            return cls.JSON
        return cls.UNKNOWN

    @classmethod
    def from_json_type(cls, json_type: str, fmt: Optional[str] = None) -> "NormalizedType":
        """Map JSON Schema type and format to NormalizedType."""
        jt = (json_type or "string").lower()
        fmt = (fmt or "").lower()

        if fmt == "email":
            return cls.EMAIL
        if fmt == "uuid":
            return cls.UUID
        if fmt == "date":
            return cls.DATE
        if fmt in ("date-time", "timestamp"):
            return cls.DATETIME

        if jt == "integer":
            return cls.INTEGER
        if jt == "number":
            return cls.FLOAT
        if jt == "boolean":
            return cls.BOOLEAN
        if jt == "array":
            return cls.ARRAY
        if jt == "object":
            return cls.OBJECT
        return cls.STRING


@dataclass
class ColumnSchema:
    """Represents a single column / field in a relational table or entity."""
    name: str
    raw_type: str = "VARCHAR"
    normalized_type: NormalizedType = NormalizedType.STRING
    nullable: bool = True
    is_primary_key: bool = False
    is_unique: bool = False
    is_foreign_key: bool = False
    foreign_key_ref: Optional[Tuple[str, str]] = None  # (target_table, target_column)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    enum_values: Optional[List[Any]] = None
    default: Optional[Any] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    description: Optional[str] = None

    @property
    def is_numeric(self) -> bool:
        return self.normalized_type in (
            NormalizedType.INTEGER,
            NormalizedType.FLOAT,
            NormalizedType.DECIMAL,
        )

    @property
    def is_integer(self) -> bool:
        return self.normalized_type == NormalizedType.INTEGER

    @property
    def is_string(self) -> bool:
        return self.normalized_type in (
            NormalizedType.STRING,
            NormalizedType.TEXT,
            NormalizedType.EMAIL,
            NormalizedType.UUID,
        )

    @property
    def is_datetime(self) -> bool:
        return self.normalized_type in (
            NormalizedType.DATE,
            NormalizedType.DATETIME,
            NormalizedType.TIMESTAMP,
        )


@dataclass
class ForeignKeyConstraint:
    """Represents a single- or multi-column foreign key constraint."""
    child_columns: List[str]
    parent_table: str
    parent_columns: List[str]
    name: Optional[str] = None


@dataclass
class TableSchema:
    """Represents a relational table definition with columns and constraints."""
    name: str
    columns: Dict[str, ColumnSchema] = field(default_factory=dict)
    primary_keys: List[str] = field(default_factory=list)
    foreign_keys: Dict[str, Tuple[str, str]] = field(default_factory=dict)  # col -> (target_table, target_col)
    foreign_key_constraints: List[ForeignKeyConstraint] = field(default_factory=list)
    unique_constraints: List[List[str]] = field(default_factory=list)

    @property
    def dependencies(self) -> Set[str]:
        """Set of other tables that this table directly depends on via Foreign Keys."""
        deps = set()
        for target_table, _ in self.foreign_keys.values():
            if target_table.lower() != self.name.lower():
                deps.add(target_table)
        for fk in self.foreign_key_constraints:
            if fk.parent_table.lower() != self.name.lower():
                deps.add(fk.parent_table)
        return deps

    def add_column(self, column: ColumnSchema) -> None:
        self.columns[column.name] = column
        if column.is_primary_key and column.name not in self.primary_keys:
            self.primary_keys.append(column.name)
        if column.is_foreign_key and column.foreign_key_ref:
            self.foreign_keys[column.name] = column.foreign_key_ref


class SchemaParseError(Exception):
    """Raised when SQL DDL or schema syntax cannot be parsed or is invalid."""
    def __init__(self, message: str, statement: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.statement = statement


class CyclicDependencyError(Exception):
    """Raised when the schema graph contains circular foreign key dependencies."""
    def __init__(self, cycle_tables: List[str]):
        super().__init__(f"Circular dependency detected among tables: {' -> '.join(cycle_tables)}")
        self.cycle_tables = cycle_tables


@dataclass
class SchemaGraph:
    """Manages a multi-table relational schema DAG and dependency resolution."""
    tables: Dict[str, TableSchema] = field(default_factory=dict)

    def add_table(self, table: TableSchema) -> None:
        self.tables[table.name] = table

    def get_dependency_map(self) -> Dict[str, List[str]]:
        """Returns map of table_name -> list of tables it depends on."""
        return {
            table_name: sorted(list(table.dependencies))
            for table_name, table in self.tables.items()
        }

    def get_topological_order(self) -> List[str]:
        """
        Computes the topological generation order using Kahn's algorithm.
        Tables with no dependencies are generated first.
        
        Raises:
            CyclicDependencyError: If a cycle is detected among tables.
        """
        # In-degree represents how many tables a table depends on
        in_degree: Dict[str, int] = {t: 0 for t in self.tables}
        # Adjacency list: parent_table -> set of child tables that depend on it
        dependents: Dict[str, Set[str]] = defaultdict(set)

        for table_name, table in self.tables.items():
            for parent in table.dependencies:
                # Find matching case-insensitive table in schema if exists
                matched_parent = next((t for t in self.tables if t.lower() == parent.lower()), parent)
                if matched_parent in self.tables:
                    dependents[matched_parent].add(table_name)
                    in_degree[table_name] += 1

        # Queue of nodes with 0 in-degree (no unresolved parent dependencies)
        queue = deque([t for t, deg in in_degree.items() if deg == 0])
        # Sort queue deterministically
        ordered: List[str] = []

        while queue:
            # Deterministic sorting for tie-breaking
            current = queue.popleft()
            ordered.append(current)

            for child in sorted(dependents[current]):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(ordered) != len(self.tables):
            unresolved = [t for t, deg in in_degree.items() if deg > 0]
            raise CyclicDependencyError(unresolved)

        return ordered


@dataclass
class JSONPropertySchema:
    """Represents a property parsed from a JSON Schema specification."""
    name: str
    normalized_type: NormalizedType = NormalizedType.STRING
    raw_type: str = "string"
    required: bool = False
    format: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    enum_values: Optional[List[Any]] = None
    default: Optional[Any] = None
    items: Optional[JSONPropertySchema] = None
    properties: Optional[Dict[str, JSONPropertySchema]] = None
    description: Optional[str] = None
