"""Unit tests for GenerationOrchestrator and relational resolution."""

from pathlib import Path
import zipfile
import pytest

from samia.engine.orchestrator import GenerationMode, GenerationOrchestrator
from samia.models.schema import ColumnSchema, NormalizedType, SchemaGraph, TableSchema
from samia.validator.pydantic_validator import PydanticValidator


@pytest.fixture
def ecommerce_graph() -> SchemaGraph:
    graph = SchemaGraph()

    # Users
    users = TableSchema(name="users")
    users.add_column(ColumnSchema(name="id", normalized_type=NormalizedType.INTEGER, is_primary_key=True))
    users.add_column(ColumnSchema(name="username", normalized_type=NormalizedType.STRING, nullable=False))
    users.add_column(ColumnSchema(name="email", normalized_type=NormalizedType.EMAIL, nullable=False))
    graph.add_table(users)

    # Orders (depends on Users)
    orders = TableSchema(name="orders")
    orders.add_column(ColumnSchema(name="id", normalized_type=NormalizedType.INTEGER, is_primary_key=True))
    orders.add_column(
        ColumnSchema(
            name="user_id",
            normalized_type=NormalizedType.INTEGER,
            is_foreign_key=True,
            foreign_key_ref=("users", "id"),
        )
    )
    orders.add_column(ColumnSchema(name="amount", normalized_type=NormalizedType.FLOAT))
    graph.add_table(orders)

    return graph


def test_orchestrator_topological_generation(ecommerce_graph):
    orchestrator = GenerationOrchestrator(ecommerce_graph, seed=42)
    result = orchestrator.generate(
        mode=GenerationMode.HAPPY,
        default_count=10,
    )

    assert result.topological_order == ["users", "orders"]
    assert len(result.data["users"]) == 10
    assert len(result.data["orders"]) == 10

    # Verify that all orders.user_id belong to the generated users.id pool
    user_ids = {u["id"] for u in result.data["users"]}
    for order in result.data["orders"]:
        assert order["user_id"] in user_ids


def test_orchestrator_export_formats(ecommerce_graph, tmp_path):
    orchestrator = GenerationOrchestrator(ecommerce_graph, seed=42)
    result = orchestrator.generate(mode=GenerationMode.HAPPY, default_count=5)

    # Export JSON
    json_path = tmp_path / "data.json"
    result.export_json(json_path)
    assert json_path.exists()
    assert json_path.stat().st_size > 0

    # Export CSVs
    csv_dir = tmp_path / "csv"
    result.export_csv_dir(csv_dir)
    assert (csv_dir / "users.csv").exists()
    assert (csv_dir / "orders.csv").exists()

    # Export SQL inserts
    sql_path = tmp_path / "inserts.sql"
    result.export_sql_inserts(sql_path)
    assert sql_path.exists()
    sql_content = sql_path.read_text(encoding="utf-8")
    assert 'INSERT INTO "users"' in sql_content
    assert 'INSERT INTO "orders"' in sql_content
    # Users insert must appear before orders insert
    users_pos = sql_content.find('INSERT INTO "users"')
    orders_pos = sql_content.find('INSERT INTO "orders"')
    assert users_pos < orders_pos

    # Export ZIP bundle
    validator = PydanticValidator(schema_graph=ecommerce_graph)
    report = validator.validate_dataset(result.data, ecommerce_graph)
    zip_path = tmp_path / "seed_bundle.zip"
    result.export_zip(zip_path, validation_report=report, schema_content="-- Schema", schema_filename="test.sql")
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert "sql/seed.sql" in namelist
        assert "json/full_dataset.json" in namelist
        assert "csv/users.csv" in namelist
        assert "csv/orders.csv" in namelist
        assert "reports/validation_report.json" in namelist
        assert "reports/qa_validation_summary.md" in namelist
        assert "schema/test.sql" in namelist
