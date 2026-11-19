"""Comprehensive negative input and malformed schema tests.

Validates that invalid SQL syntax, cyclic foreign key dependencies,
empty tables, and unsupported column types produce clean, descriptive,
non-crashing error messages and well-defined exception types.
"""

from __future__ import annotations

import tempfile
import pytest
from click.testing import CliRunner

from samia.cli import cli
from samia.engine.orchestrator import GenerationMode, GenerationOrchestrator
from samia.models.schema import (
    ColumnSchema,
    CyclicDependencyError,
    NormalizedType,
    SchemaGraph,
    SchemaParseError,
    TableSchema,
)
from samia.parsers.sql_parser import SQLDDLParser
from samia.validator.pydantic_validator import PydanticValidator


class TestMalformedSQLSyntax:
    """Tests parser resilience against invalid or malformed SQL inputs."""

    def test_unbalanced_parentheses_raises_parse_error(self):
        sql = """
        CREATE TABLE broken (
            id INT PRIMARY KEY,
            name VARCHAR(50)
        -- Missing closing parenthesis
        """
        parser = SQLDDLParser()
        with pytest.raises(SchemaParseError) as exc_info:
            parser.parse(sql)
        assert "Unbalanced parentheses" in str(exc_info.value)

    def test_invalid_table_identifier_raises_parse_error(self):
        sql = "CREATE TABLE ; (id INT);"
        parser = SQLDDLParser()
        with pytest.raises(SchemaParseError) as exc_info:
            parser.parse(sql)
        assert "Invalid table identifier" in str(exc_info.value)

    def test_empty_table_body_raises_parse_error(self):
        sql = "CREATE TABLE empty_table ();"
        parser = SQLDDLParser()
        with pytest.raises(SchemaParseError) as exc_info:
            parser.parse(sql)
        assert "does not contain any valid column definitions" in str(exc_info.value) or "empty or unclosed" in str(exc_info.value)

    def test_non_sql_gibberish_strict_mode_raises_parse_error(self):
        sql = "SELECT * FROM somewhere; NOT A DDL DEFINITION;"
        parser = SQLDDLParser()
        with pytest.raises(SchemaParseError) as exc_info:
            parser.parse(sql, strict=True)
        assert "No valid CREATE TABLE statements found" in str(exc_info.value)

    def test_completely_empty_string_returns_empty_graph(self):
        parser = SQLDDLParser()
        graph = parser.parse("")
        assert len(graph.tables) == 0


class TestCyclicDependencyDetection:
    """Tests detection of direct and indirect circular foreign key graphs."""

    def test_direct_two_table_circular_dependency(self):
        sql = """
        CREATE TABLE authors (
            id INT PRIMARY KEY,
            favorite_book_id INT REFERENCES books(id)
        );
        CREATE TABLE books (
            id INT PRIMARY KEY,
            author_id INT NOT NULL REFERENCES authors(id)
        );
        """
        parser = SQLDDLParser()
        graph = parser.parse(sql)
        with pytest.raises(CyclicDependencyError) as exc_info:
            graph.get_topological_order()
        assert "Circular dependency detected" in str(exc_info.value)
        assert set(exc_info.value.cycle_tables) == {"authors", "books"}

    def test_three_table_cycle(self):
        sql = """
        CREATE TABLE node_a (
            id INT PRIMARY KEY,
            ref_b INT REFERENCES node_b(id)
        );
        CREATE TABLE node_b (
            id INT PRIMARY KEY,
            ref_c INT REFERENCES node_c(id)
        );
        CREATE TABLE node_c (
            id INT PRIMARY KEY,
            ref_a INT REFERENCES node_a(id)
        );
        """
        parser = SQLDDLParser()
        graph = parser.parse(sql)
        with pytest.raises(CyclicDependencyError) as exc_info:
            graph.get_topological_order()
        assert "Circular dependency detected" in str(exc_info.value)
        assert set(exc_info.value.cycle_tables) == {"node_a", "node_b", "node_c"}


class TestUnsupportedColumnTypesAndWarnings:
    """Tests graceful handling and warnings for dialect-specific or exotic SQL types."""

    def test_unsupported_column_types_fallback_and_warning(self):
        sql = """
        CREATE TABLE geo_features (
            id INT PRIMARY KEY,
            boundary GEOMETRY(Polygon, 4326),
            time_window INTERVAL DAY TO SECOND,
            custom_payload BYTEA
        );
        """
        parser = SQLDDLParser()
        graph = parser.parse(sql)
        assert "geo_features" in graph.tables
        table = graph.tables["geo_features"]

        # All exotic types map safely to UNKNOWN normalized type without crashing
        assert table.columns["boundary"].normalized_type == NormalizedType.UNKNOWN
        assert table.columns["time_window"].normalized_type == NormalizedType.UNKNOWN
        assert table.columns["custom_payload"].normalized_type == NormalizedType.UNKNOWN

        # Parser registered clean, actionable warnings
        assert len(parser.warnings) >= 3
        assert any("GEOMETRY" in w for w in parser.warnings)

        # Happy-path generator generates string fallback values without crashing
        result = GenerationOrchestrator(graph, seed=123).generate(mode=GenerationMode.HAPPY, default_count=5)
        rows = result.data["geo_features"]
        assert len(rows) == 5
        assert isinstance(rows[0]["boundary"], str)


class TestCLINegativeInputResilience:
    """Tests CLI exit behavior on invalid schemas without raw Python tracebacks."""

    def test_cli_handles_cyclic_schema_cleanly(self):
        with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
            f.write("""
            CREATE TABLE alpha (id INT PRIMARY KEY, beta_id INT REFERENCES beta(id));
            CREATE TABLE beta (id INT PRIMARY KEY, alpha_id INT REFERENCES alpha(id));
            """)
            f.flush()

            runner = CliRunner()
            result = runner.invoke(cli, ["generate", "-s", f.name])
            assert result.exit_code != 0
            assert "Circular foreign key dependency detected" in result.output

    def test_cli_handles_malformed_ddl_cleanly(self):
        with tempfile.NamedTemporaryFile(suffix=".sql", mode="w", delete=False) as f:
            f.write("CREATE TABLE broken (id INT PRIMARY KEY, name VARCHAR(50)")
            f.flush()

            runner = CliRunner()
            result = runner.invoke(cli, ["generate", "-s", f.name])
            assert result.exit_code != 0
            assert "DDL Schema parsing failed" in result.output
