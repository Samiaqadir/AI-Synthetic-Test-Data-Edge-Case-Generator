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
    authors.add_column(ColumnSchema(name="email", normalized_type=NormalizedType.EMAIL, is_unique=True))
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
            {"id": 1, "name": "Valid Author", "email": "valid@example.com"},
            {"id": 2, "name": "ThisNameIsFarTooLongForTwentyCharsMax", "email": "bad-email-no-at"},  # max_length & regex
        ],
        "books": [
            {"id": 101, "author_id": 1, "pages": 300, "genre": "fiction"},  # valid
            {"id": 102, "author_id": 999, "pages": 150, "genre": "sci-fi"},  # FK violation (author 999 not found)
            {"id": 103, "author_id": 1, "pages": -5, "genre": "mystery"},  # Range violation & Enum violation
        ],
    }

    report_file = tmp_path / "report.json"
    report = validator.validate_dataset(dataset, test_schema_graph, output_report_path=report_file)

    assert report.total_records == 5
    assert report.valid_records == 2  # authors[0], books[0]
    assert report.invalid_records == 3  # authors[1], books[1], books[2]

    # Verify report file was saved
    assert report_file.exists()
    assert report.tables["authors"].invalid_records == 1
    assert report.tables["books"].invalid_records == 2

    # Check category badges
    assert "Data Types" in report.category_badges
    assert "Regex Formats" in report.category_badges
    assert "Uniqueness Constraints" in report.category_badges
    assert "Foreign-Key Integrity" in report.category_badges

    assert report.category_badges["Regex Formats"]["status"] == "FAIL"
    assert report.category_badges["Foreign-Key Integrity"]["status"] == "FAIL"

    # Check row-level violation tracking
    assert 1 in report.tables["authors"].row_violations
    assert 1 in report.tables["books"].row_violations
    assert 2 in report.tables["books"].row_violations

    # Check markdown summary generation
    md_summary = report.to_markdown_summary()
    assert "# QA Validation Report" in md_summary
    assert "Automated QA Category Verification Badges" in md_summary


def test_validator_clean_happy_path(test_schema_graph):
    validator = PydanticValidator(schema_graph=test_schema_graph)
    clean_dataset = {
        "authors": [
            {"id": 1, "name": "Alice", "email": "alice@test.com"},
            {"id": 2, "name": "Bob", "email": "bob@test.com"},
        ],
        "books": [
            {"id": 10, "author_id": 1, "pages": 250, "genre": "fiction"},
            {"id": 11, "author_id": 2, "pages": 180, "genre": "sci-fi"},
        ],
    }

    report = validator.validate_dataset(clean_dataset, test_schema_graph)
    assert report.total_records == 4
    assert report.valid_records == 4
    assert report.invalid_records == 0
    assert report.pass_rate == 100.0

    # All category badges should PASS
    for cat, info in report.category_badges.items():
        assert info["status"] == "PASS"
        assert "🟢 PASS" in info["badge"]
