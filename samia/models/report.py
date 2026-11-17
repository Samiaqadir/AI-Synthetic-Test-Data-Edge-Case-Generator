"""Models for validation reporting and violation tracking."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ViolationExample:
    """Represents a specific constraint violation found during validation."""
    table_name: str
    row_index: int
    column_name: str
    rule: str
    value: Any
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "row_index": self.row_index,
            "column_name": self.column_name,
            "rule": self.rule,
            "value": str(self.value) if not isinstance(self.value, (int, float, bool, type(None))) else self.value,
            "message": self.message,
        }


@dataclass
class TableValidationSummary:
    """Summary of validation metrics for an individual table."""
    table_name: str
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    pass_rate: float = 0.0
    violations_by_column: Dict[str, int] = field(default_factory=dict)
    violations_by_rule: Dict[str, int] = field(default_factory=dict)
    sample_violations: List[ViolationExample] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "total_records": self.total_records,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "pass_rate_percentage": round(self.pass_rate, 2),
            "violations_by_column": self.violations_by_column,
            "violations_by_rule": self.violations_by_rule,
            "sample_violations": [v.to_dict() for v in self.sample_violations],
        }


@dataclass
class ValidationReport:
    """Complete validation report tracking pass/fail counts and violation details."""
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    pass_rate: float = 0.0
    duration_seconds: float = 0.0
    tables: Dict[str, TableValidationSummary] = field(default_factory=dict)
    sample_violations: List[ViolationExample] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": {
                "total_records": self.total_records,
                "valid_records": self.valid_records,
                "invalid_records": self.invalid_records,
                "pass_rate_percentage": round(self.pass_rate, 2),
                "duration_seconds": round(self.duration_seconds, 4),
            },
            "tables": {
                name: summary.to_dict()
                for name, summary in self.tables.items()
            },
            "recent_violations": [v.to_dict() for v in self.sample_violations[:50]],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize report to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, filepath: str | Path) -> Path:
        """Save report to a JSON file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path
