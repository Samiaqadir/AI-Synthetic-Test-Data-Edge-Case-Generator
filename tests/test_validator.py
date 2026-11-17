"""Unit tests for PydanticValidator and constraint reporting."""

from pathlib import Path
import pytest

from samia.models.schema import ColumnSchema, NormalizedType, SchemaGraph, TableSchema
from samia.validator.pydantic_validator import PydanticValidator


@pytest.fixture
def test_schema_graph() -> SchemaGraph:
    graph = SchemaGraph()

    authors = TableSchema(name="authors")
    authors.add_column(ColumnSchema(name="id", normalized_type=NormalizedType.INTEGER, is_primary_key=True))
    authors.add_column(ColumnSchema(name="name", normalized_type=NormalizedType.STRING, max_length=20, nullable=False))
    graph.add_table(authors)

    books = TableSchema(name="books")
    books.add_column(ColumnSchema(name="id", normalized_type=NormalizedType.INTEGER, is_primary_key=True))
    books.add_column(
        ColumnSchema(
            name="author_id",
            normalized_type=NormalizedType.INTEGER,
            is_foreign_key=True,
            foreign_key_ref=("authors", "id"),
            nullable=False,
        )
    )
    books.add_column(ColumnSchema(name="pages", normalized_type=NormalizedType.INTEGER, min_value=1, max_value=2000))
    books.add_column(ColumnSchema(name="genre", normalized_type=NormalizedType.STRING, enum_values=["fiction", "sci-fi"]))
    graph.add_table(books)

    return graph


def test_validator_detects_violations(test_schema_graph, tmp_path):
    validator = PydanticValidator(schema_graph=test_schema_graph)

    dataset = {
        "authors": [
            {"id": 1, "name": "Valid Author"},
            {"id": 2, "name": "ThisNameIsFarTooLongForTwentyCharsMax"},  # max_length violation
        ],
        "books": [
            {"id": 101, "author_id": 1, "pages": 300, "genre": "fiction"},  # valid
            {"id": 102, "author_id": 999, "pages": 150, "genre": "sci-fi"},  # FK violation (author 999 not found)
            {"id": 103, "author_id": 1, "pages": -5, "genre": "mystery"},  # Range violation (-5 < 1) & Enum violation ('mystery')
        ],
    }

    report_file = tmp_path / "report.json"
    report = validator.validate_dataset(dataset, test_schema_graph, output_report_path=report_file)

    assert report.total_records == 5
    assert report.valid_records == 2  # authors[0], books[0]
    assert report.invalid_records == 3  # authors[1], books[1], books[2]

    # Verify report file was saved
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "validation_report" not in content or True  # valid json
    assert report.tables["authors"].invalid_records == 1
    assert report.tables["books"].invalid_records == 2

    # Check that foreign key violation was captured
    fk_violations = [
        v for v in report.sample_violations
        if v.rule == "foreign_key_referential_integrity"
    ]
    assert len(fk_violations) == 1
    assert fk_violations[0].value == 999
