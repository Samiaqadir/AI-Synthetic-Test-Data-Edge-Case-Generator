"""Orchestrator for managing topological generation of multi-table relational schemas."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from samia.engine.generator_happy import HappyPathGenerator, RelationalContext
from samia.engine.generator_stress import StressGenerator
from samia.models.schema import SchemaGraph, TableSchema


class GenerationMode(str, Enum):
    """Execution mode for test data generation."""
    HAPPY = "happy"
    STRESS = "stress"
    MIXED = "mixed"
    TARGETED_STRESS = "targeted_stress"


@dataclass
class GenerationResult:
    """Encapsulates the generated dataset across all tables and export utilities."""
    data: Dict[str, List[Dict[str, Any]]]
    topological_order: List[str]
    generation_mode: GenerationMode
    total_records: int

    def to_dict(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.data

    def export_json(self, target_path: str | Path, indent: int = 2) -> Path:
        """Export all generated data to a single consolidated JSON file."""
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=indent, default=str), encoding="utf-8")
        return path

    def export_csv_dir(self, dir_path: str | Path) -> Path:
        """Export each table into its own CSV file inside the specified directory."""
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)

        for table_name, rows in self.data.items():
            if not rows:
                continue
            file_path = path / f"{table_name}.csv"
            headers = list(rows[0].keys())
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: ("" if v is None else str(v)) for k, v in row.items()})

        return path

    def export_sql_inserts(self, target_path: str | Path) -> Path:
        """
        Export generated records as SQL INSERT statements ordered topologically
        so child records can be safely inserted after parent records.
        """
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = [
            "-- Samia Synthetic Data Generation Output",
            "-- Topologically ordered INSERT statements",
            "BEGIN TRANSACTION;",
            "",
        ]

        for table_name in self.topological_order:
            rows = self.data.get(table_name, [])
            if not rows:
                continue

            lines.append(f"-- Table: {table_name} ({len(rows)} records)")
            headers = list(rows[0].keys())
            cols_clause = ", ".join(f'"{col}"' for col in headers)

            for row in rows:
                vals = []
                for col in headers:
                    val = row[col]
                    if val is None:
                        vals.append("NULL")
                    elif isinstance(val, (int, float)):
                        vals.append(str(val))
                    elif isinstance(val, bool):
                        vals.append("TRUE" if val else "FALSE")
                    else:
                        escaped = str(val).replace("'", "''")
                        vals.append(f"'{escaped}'")
                vals_clause = ", ".join(vals)
                lines.append(f"INSERT INTO \"{table_name}\" ({cols_clause}) VALUES ({vals_clause});")
            lines.append("")

        lines.append("COMMIT;")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path


class GenerationOrchestrator:
    """
    Coordinates multi-table synthetic data generation following topological order.
    Ensures primary-to-foreign key relational referential integrity across dependencies.
    """

    def __init__(
        self,
        schema_graph: SchemaGraph,
        seed: Optional[int] = None,
        locale: str = "en_US",
    ) -> None:
        self.schema_graph = schema_graph
        self.seed = seed
        self.happy = HappyPathGenerator(seed=seed, locale=locale)
        self.stress = StressGenerator(seed=seed, happy_generator=self.happy)
        self.context = RelationalContext()

    def generate(
        self,
        mode: Union[GenerationMode, str] = GenerationMode.HAPPY,
        default_count: int = 10,
        table_counts: Optional[Dict[str, int]] = None,
        mutation_rate: float = 0.3,
        mixed_stress_ratio: float = 0.2,
    ) -> GenerationResult:
        """
        Generate synthetic records for all tables in topological order.

        Args:
            mode: "happy", "stress", or "mixed"
            default_count: Default number of rows per table if not specified in table_counts
            table_counts: Optional mapping of table_name -> row count
            mutation_rate: Probability of mutating an eligible field during stress generation
            mixed_stress_ratio: Proportion of rows that will be mutated in "mixed" mode (e.g. 0.2 = 20%)
        """
        if isinstance(mode, str):
            mode = GenerationMode(mode.lower())

        table_counts = table_counts or {}
        # Compute topological order
        order = self.schema_graph.get_topological_order()

        dataset: Dict[str, List[Dict[str, Any]]] = {}
        total_records = 0

        for table_name in order:
            table_schema = self.schema_graph.tables[table_name]
            count = table_counts.get(table_name, default_count)

            if mode == GenerationMode.HAPPY:
                rows = self.happy.generate_table_records(
                    table=table_schema,
                    count=count,
                    context=self.context,
                )
            elif mode == GenerationMode.STRESS:
                rows = self.stress.generate_table_records(
                    table=table_schema,
                    count=count,
                    context=self.context,
                    mutation_rate=mutation_rate,
                )
            elif mode == GenerationMode.TARGETED_STRESS:
                rows = self.stress.generate_targeted_15_rows(
                    table=table_schema,
                    context=self.context,
                )
            elif mode == GenerationMode.MIXED:
                # Part happy, part stress
                stress_count = int(count * mixed_stress_ratio)
                happy_count = count - stress_count

                happy_rows = self.happy.generate_table_records(
                    table=table_schema,
                    count=happy_count,
                    context=self.context,
                )
                stress_rows = self.stress.generate_table_records(
                    table=table_schema,
                    count=stress_count,
                    context=self.context,
                    mutation_rate=mutation_rate,
                )
                rows = happy_rows + stress_rows
            else:
                raise ValueError(f"Unsupported generation mode: {mode}")

            dataset[table_name] = rows
            total_records += len(rows)

        return GenerationResult(
            data=dataset,
            topological_order=order,
            generation_mode=mode,
            total_records=total_records,
        )
