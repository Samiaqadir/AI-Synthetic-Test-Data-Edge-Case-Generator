"""Models for validation reporting and violation tracking."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ViolationExample:
    """Represents a specific constraint violation found during validation."""
    table_name: str
    row_index: int
    column_name: str
    rule: str
    value: Any
    message: str
    category: str = "Data Types"  # "Data Types", "Regex Formats", "Uniqueness Constraints", "Foreign-Key Integrity", "Bounds & Nullability"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "row_index": self.row_index,
            "column_name": self.column_name,
            "rule": self.rule,
            "category": self.category,
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
    violations_by_category: Dict[str, int] = field(default_factory=dict)
    sample_violations: List[ViolationExample] = field(default_factory=list)
    row_violations: Dict[int, List[ViolationExample]] = field(default_factory=dict)
    category_badges: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_name": self.table_name,
            "total_records": self.total_records,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "pass_rate_percentage": round(self.pass_rate, 2),
            "status": "PASS" if self.invalid_records == 0 else "FAIL",
            "category_badges": self.category_badges,
            "violations_by_column": self.violations_by_column,
            "violations_by_rule": self.violations_by_rule,
            "violations_by_category": self.violations_by_category,
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
    category_badges: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": {
                "total_records": self.total_records,
                "valid_records": self.valid_records,
                "invalid_records": self.invalid_records,
                "pass_rate_percentage": round(self.pass_rate, 2),
                "duration_seconds": round(self.duration_seconds, 4),
                "overall_status": "PASS" if self.invalid_records == 0 else "FAIL",
            },
            "category_badges": self.category_badges,
            "tables": {
                name: summary.to_dict()
                for name, summary in self.tables.items()
            },
            "recent_violations": [v.to_dict() for v in self.sample_violations[:100]],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize report to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_markdown_summary(self) -> str:
        """Generate human-readable Markdown summary for QA documentation."""
        status_badge = "🟢 PASS (100% Valid)" if self.invalid_records == 0 else f"🔴 FAIL ({self.invalid_records} Violations Found)"
        lines = [
            f"# QA Validation Report",
            f"",
            f"**Overall Status:** {status_badge}  ",
            f"**Total Records Inspected:** {self.total_records}  ",
            f"**Valid Records:** {self.valid_records}  ",
            f"**Invalid Records:** {self.invalid_records}  ",
            f"**Pass Rate:** {round(self.pass_rate, 2)}%  ",
            f"**Validation Duration:** {round(self.duration_seconds, 4)}s  ",
            f"",
            f"## Automated QA Category Verification Badges",
            f"",
            f"| QA Category | Status | Badge | Violations Detected |",
            f"| :--- | :---: | :---: | :---: |",
        ]

        categories = [
            "Data Types",
            "Regex Formats",
            "Uniqueness Constraints",
            "Foreign-Key Integrity",
        ]
        for cat in categories:
            info = self.category_badges.get(cat, {"status": "PASS", "badge": "🟢 PASS", "count": 0})
            badge = info.get("badge", "🟢 PASS")
            status = info.get("status", "PASS")
            count = info.get("count", 0)
            lines.append(f"| **{cat}** | `{status}` | {badge} | {count} |")

        lines.extend([
            f"",
            f"## Table-by-Table Breakdown",
            f"",
            f"| Table Name | Records | Valid | Invalid | Pass Rate | Status |",
            f"| :--- | :---: | :---: | :---: | :---: | :---: |",
        ])

        for tbl_name, tbl_sum in self.tables.items():
            tbl_badge = "🟢 PASS" if tbl_sum.invalid_records == 0 else f"🔴 FAIL ({tbl_sum.invalid_records})"
            lines.append(
                f"| `{tbl_name}` | {tbl_sum.total_records} | {tbl_sum.valid_records} | "
                f"{tbl_sum.invalid_records} | {round(tbl_sum.pass_rate, 1)}% | {tbl_badge} |"
            )

        if self.sample_violations:
            lines.extend([
                f"",
                f"## Detected Sample Violations (First {min(len(self.sample_violations), 15)})",
                f"",
                f"| Table | Row | Column | Category | Rule | Offending Value | Diagnostic Message |",
                f"| :--- | :---: | :--- | :--- | :--- | :--- | :--- |",
            ])
            for v in self.sample_violations[:15]:
                val_repr = str(v.value).replace("\n", " ")[:30]
                lines.append(
                    f"| `{v.table_name}` | {v.row_index} | `{v.column_name}` | {v.category} | `{v.rule}` | `{val_repr}` | {v.message} |"
                )

        return "\n".join(lines)

    def save(self, filepath: str | Path) -> Path:
        """Save report to a JSON file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path
