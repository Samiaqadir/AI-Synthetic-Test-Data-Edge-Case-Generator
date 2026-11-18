"""CLI entrypoint for Samia AI Synthetic Test Data & Edge-Case Generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from samia.engine.orchestrator import (
    GenerationMode,
    GenerationOrchestrator,
)
from samia.models.schema import SchemaGraph
from samia.parsers.json_parser import JSONSchemaParser
from samia.parsers.sql_parser import SQLDDLParser
from samia.validator.pydantic_validator import PydanticValidator

console = Console()


def load_config_file(config_path: Optional[str | Path]) -> Dict[str, Any]:
    """Load configuration from a YAML or JSON file."""
    if not config_path:
        return {}
    path = Path(config_path)
    if not path.is_file():
        raise click.BadParameter(f"Configuration file not found: {path}")

    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        return yaml.safe_load(content) or {}
    return json.loads(content)


def resolve_schema(
    schema_sql: Optional[str] = None,
    schema_json: Optional[str] = None,
    entity_name: str = "entity",
) -> SchemaGraph:
    """Parse SQL DDL or JSON Schema into a unified SchemaGraph."""
    if schema_sql:
        path = Path(schema_sql)
        if not path.exists():
            raise click.ClickException(f"SQL schema file not found: {path}")
        return SQLDDLParser().parse_file(path)

    if schema_json:
        path = Path(schema_json)
        if not path.exists():
            raise click.ClickException(f"JSON schema file not found: {path}")
        parser = JSONSchemaParser()
        table_schema = parser.to_table_schema(entity_name=entity_name, schema=path.read_text(encoding="utf-8"))
        graph = SchemaGraph()
        graph.add_table(table_schema)
        return graph

    raise click.ClickException("Must specify either --schema-sql or --schema-json (or define in config)")


@click.group()
@click.version_option(version="0.1.0", prog_name="samia")
def cli() -> None:
    """Samia: AI Synthetic Test Data & Edge-Case Generator CLI."""
    pass


@cli.command("generate")
@click.option("--config", "-c", type=click.Path(exists=False), help="Path to samia_config.yaml")
@click.option("--schema-sql", "-s", type=click.Path(exists=False), help="Path to SQL DDL schema file")
@click.option("--schema-json", "-j", type=click.Path(exists=False), help="Path to JSON Schema file")
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["happy", "stress", "mixed", "targeted_stress"], case_sensitive=False),
    default=None,
    help="Generation mode (happy, stress, mixed, or targeted_stress)",
)
@click.option("--count", "-n", type=int, default=None, help="Default number of rows per table")
@click.option("--output-dir", "-o", type=click.Path(), default=None, help="Output directory for generated files")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["json", "csv", "sql", "all"], case_sensitive=False),
    default=None,
    help="Export format (json, csv, sql, all)",
)
@click.option("--seed", type=int, default=None, help="Random seed for deterministic generation")
@click.option("--validate/--no-validate", default=None, help="Validate output using Pydantic constraint validator")
@click.option("--report", "report_path", type=click.Path(), default=None, help="Custom path for validation_report.json")
def generate_command(
    config: Optional[str],
    schema_sql: Optional[str],
    schema_json: Optional[str],
    mode: Optional[str],
    count: Optional[int],
    output_dir: Optional[str],
    output_format: Optional[str],
    seed: Optional[int],
    validate: Optional[bool],
    report_path: Optional[str],
) -> None:
    """Generate synthetic test data and edge cases from SQL or JSON schemas."""
    # 1. Load configuration file if provided
    cfg = load_config_file(config)

    # 2. Merge options (CLI flags take precedence over config)
    gen_cfg = cfg.get("generation", {})
    schema_cfg = cfg.get("schema", {})
    output_cfg = cfg.get("output", {})
    val_cfg = cfg.get("validation", {})
    tables_cfg = cfg.get("tables", {})

    effective_sql = schema_sql or (schema_cfg.get("path") if schema_cfg.get("type") == "sql" else None)
    effective_json = schema_json or (schema_cfg.get("path") if schema_cfg.get("type") == "json" else None)

    effective_mode = mode or gen_cfg.get("mode", "happy")
    effective_count = count or gen_cfg.get("default_count", 10)
    effective_seed = seed if seed is not None else gen_cfg.get("seed")
    effective_out_dir = Path(output_dir or output_cfg.get("directory", "output"))

    formats = []
    if output_format:
        formats = ["json", "csv", "sql"] if output_format.lower() == "all" else [output_format.lower()]
    elif "formats" in output_cfg:
        formats = [f.lower() for f in output_cfg["formats"]]
    else:
        formats = ["json"]

    effective_validate = validate if validate is not None else val_cfg.get("enabled", True)
    effective_report = Path(report_path or val_cfg.get("report_path", effective_out_dir / "validation_report.json"))

    mutation_rate = float(gen_cfg.get("mutation_rate", 0.35))
    mixed_stress_ratio = float(gen_cfg.get("mixed_stress_ratio", 0.25))

    # Per-table counts
    table_counts: Dict[str, int] = {}
    for tbl, tcfg in tables_cfg.items():
        if isinstance(tcfg, dict) and "count" in tcfg:
            table_counts[tbl] = int(tcfg["count"])
        elif isinstance(tcfg, int):
            table_counts[tbl] = tcfg

    console.print(Panel(
        f"[bold cyan]Samia AI Synthetic Test Data & Edge-Case Generator[/bold cyan]\n"
        f"Mode: [green]{effective_mode.upper()}[/green] | Seed: {effective_seed} | Default Rows: {effective_count}",
        border_style="cyan",
    ))

    # 3. Resolve Schema and DAG
    graph = resolve_schema(effective_sql, effective_json)
    order = graph.get_topological_order()

    order_display = " -> ".join([f"[bold]{t}[/bold]" for t in order])
    console.print(f"[bold blue]Topological Generation Order:[/bold blue] {order_display}\n")

    # 4. Orchestrate Generation
    orchestrator = GenerationOrchestrator(
        schema_graph=graph,
        seed=effective_seed,
    )

    with console.status("[bold green]Generating synthetic records...[/bold green]"):
        result = orchestrator.generate(
            mode=effective_mode,
            default_count=effective_count,
            table_counts=table_counts,
            mutation_rate=mutation_rate,
            mixed_stress_ratio=mixed_stress_ratio,
        )

    # 5. Export generated data
    effective_out_dir.mkdir(parents=True, exist_ok=True)
    exported_files = []

    if "json" in formats:
        p = result.export_json(effective_out_dir / "synthetic_data.json")
        exported_files.append(str(p))

    if "csv" in formats:
        p = result.export_csv_dir(effective_out_dir / "csv")
        exported_files.append(str(p))

    if "sql" in formats:
        p = result.export_sql_inserts(effective_out_dir / "inserts.sql")
        exported_files.append(str(p))

    # 6. Display Generation Summary
    table = Table(title="Generated Dataset Summary", header_style="bold magenta")
    table.add_column("Table Name", style="cyan")
    table.add_column("Rows Generated", justify="right", style="green")
    table.add_column("Columns", justify="right")
    table.add_column("Foreign Key Dependencies", style="yellow")

    for tbl_name in order:
        tbl_schema = graph.tables[tbl_name]
        rows = result.data.get(tbl_name, [])
        deps = ", ".join(tbl_schema.dependencies) if tbl_schema.dependencies else "None"
        table.add_row(tbl_name, str(len(rows)), str(len(tbl_schema.columns)), deps)

    console.print(table)
    console.print(f"\n[green]✓[/green] Successfully generated [bold]{result.total_records}[/bold] records.")
    console.print(f"[green]✓[/green] Exported files to: [underline]{effective_out_dir}[/underline]\n")

    # 7. Constraint Validation
    if effective_validate:
        console.print("[bold yellow]Running Pydantic Constraint & Referential Validation...[/bold yellow]")
        validator = PydanticValidator(schema_graph=graph)
        report = validator.validate_dataset(
            dataset=result.data,
            schema_graph=graph,
            output_report_path=effective_report,
        )

        val_table = Table(title="Validation Report Summary", header_style="bold cyan")
        val_table.add_column("Table Name", style="cyan")
        val_table.add_column("Total Rows", justify="right")
        val_table.add_column("Passed", justify="right", style="green")
        val_table.add_column("Failed", justify="right", style="red")
        val_table.add_column("Pass Rate (%)", justify="right", style="bold")

        for name, summary in report.tables.items():
            rate_style = "green" if summary.pass_rate >= 90 else ("yellow" if summary.pass_rate >= 50 else "red")
            val_table.add_row(
                name,
                str(summary.total_records),
                str(summary.valid_records),
                str(summary.invalid_records),
                f"[{rate_style}]{summary.pass_rate:.1f}%[/{rate_style}]",
            )

        console.print(val_table)
        console.print(
            f"Overall Pass Rate: [bold]{report.pass_rate:.2f}%[/bold] "
            f"([green]{report.valid_records} passed[/green], [red]{report.invalid_records} failed[/red])"
        )
        console.print(f"[green]✓[/green] Validation report saved: [underline]{effective_report}[/underline]\n")


@cli.command("inspect")
@click.option("--schema-sql", "-s", type=click.Path(exists=False), help="Path to SQL DDL schema file")
@click.option("--schema-json", "-j", type=click.Path(exists=False), help="Path to JSON Schema file")
def inspect_command(
    schema_sql: Optional[str],
    schema_json: Optional[str],
) -> None:
    """Inspect schema metadata, extracted constraints, and dependency DAG."""
    graph = resolve_schema(schema_sql, schema_json)
    order = graph.get_topological_order()

    console.print(Panel("[bold cyan]Schema Architecture & Dependency DAG[/bold cyan]", border_style="cyan"))
    console.print(f"[bold blue]Topological Generation Order:[/bold blue] {' -> '.join(order)}\n")

    for table_name in order:
        tbl = graph.tables[table_name]
        t = Table(title=f"Table: {table_name}", header_style="bold green")
        t.add_column("Column", style="cyan")
        t.add_column("Type", style="yellow")
        t.add_column("Nullable")
        t.add_column("PK / Unique")
        t.add_column("Foreign Key Target", style="magenta")
        t.add_column("Constraints / Rules", style="blue")

        for col_name, col in tbl.columns.items():
            pk_uq = []
            if col.is_primary_key:
                pk_uq.append("PK")
            if col.is_unique:
                pk_uq.append("UQ")
            pk_uq_str = ", ".join(pk_uq) if pk_uq else "-"

            fk_str = f"{col.foreign_key_ref[0]}.{col.foreign_key_ref[1]}" if col.foreign_key_ref else "-"

            rules = []
            if col.min_value is not None or col.max_value is not None:
                rules.append(f"range: [{col.min_value}, {col.max_value}]")
            if col.max_length is not None:
                rules.append(f"max_len: {col.max_length}")
            if col.enum_values:
                rules.append(f"enum: {col.enum_values}")
            if col.pattern:
                rules.append(f"regex: {col.pattern}")
            rules_str = "; ".join(rules) if rules else "-"

            t.add_row(
                col_name,
                col.raw_type,
                "YES" if col.nullable else "NO",
                pk_uq_str,
                fk_str,
                rules_str,
            )

        console.print(t)
        console.print()


@cli.command("validate")
@click.option("--data", "-d", type=click.Path(exists=True), required=True, help="Path to synthetic_data.json")
@click.option("--schema-sql", "-s", type=click.Path(exists=False), help="Path to SQL DDL schema file")
@click.option("--schema-json", "-j", type=click.Path(exists=False), help="Path to JSON Schema file")
@click.option("--report", "-r", type=click.Path(), default="validation_report.json", help="Path to output report")
def validate_command(
    data: str,
    schema_sql: Optional[str],
    schema_json: Optional[str],
    report: str,
) -> None:
    """Validate an existing generated dataset against schema constraints."""
    graph = resolve_schema(schema_sql, schema_json)
    dataset = json.loads(Path(data).read_text(encoding="utf-8"))

    validator = PydanticValidator(schema_graph=graph)
    rep = validator.validate_dataset(
        dataset=dataset,
        schema_graph=graph,
        output_report_path=report,
    )

    console.print(Panel(
        f"[bold]Validation Results[/bold]\n"
        f"Total Records: {rep.total_records} | Valid: [green]{rep.valid_records}[/green] | "
        f"Invalid: [red]{rep.invalid_records}[/red] | Pass Rate: [bold]{rep.pass_rate:.2f}%[/bold]",
        border_style="green" if rep.pass_rate >= 90 else "red",
    ))
    console.print(f"[green]✓[/green] Full report written to: [underline]{report}[/underline]")


@cli.command("ui")
@click.option("--port", "-p", type=int, default=8501, help="Port to run Streamlit Web UI on")
@click.option("--host", "-h", type=str, default="localhost", help="Host address to bind Web UI")
def ui_command(port: int, host: str) -> None:
    """Launch the interactive Samia Streamlit Web UI workbench."""
    import subprocess
    app_path = Path(__file__).parent / "ui" / "app.py"
    console.print(Panel(
        f"[bold cyan]Launching Samia QA Test Data Generator Web UI[/bold cyan]\n"
        f"Server binding: [bold]http://{host}:{port}[/bold]\n"
        f"Press Ctrl+C to terminate the UI server.",
        border_style="cyan",
    ))
    subprocess.run([
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(port),
        "--server.address",
        host,
    ])


def main() -> None:
    """Main program entrypoint."""
    cli()


if __name__ == "__main__":
    main()
