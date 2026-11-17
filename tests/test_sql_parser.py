"""Unit tests for SQL DDL Parser and dependency DAG construction."""

import pytest

from samia.models.schema import CyclicDependencyError, NormalizedType
from samia.parsers.sql_parser import SQLDDLParser


def test_parse_single_table_with_constraints():
    sql = """
    CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        age INT CHECK (age >= 18 AND age <= 65),
        status VARCHAR(20) CHECK (status IN ('active', 'suspended')),
        created_at TIMESTAMP NOT NULL
    );
    """
    parser = SQLDDLParser()
    graph = parser.parse(sql)

    assert "users" in graph.tables
    table = graph.tables["users"]

    assert table.name == "users"
    assert "id" in table.columns
    assert table.columns["id"].is_primary_key is True
    assert table.columns["id"].is_unique is True
    assert table.columns["id"].nullable is False

    assert "email" in table.columns
    assert table.columns["email"].is_unique is True
    assert table.columns["email"].nullable is False
    assert table.columns["email"].max_length == 255

    assert "age" in table.columns
    assert table.columns["age"].min_value == 18.0
    assert table.columns["age"].max_value == 65.0

    assert "status" in table.columns
    assert table.columns["status"].enum_values == ["active", "suspended"]


def test_parse_multi_table_foreign_keys_and_dag():
    sql = """
    CREATE TABLE customers (
        id INT PRIMARY KEY,
        name VARCHAR(100) NOT NULL
    );

    CREATE TABLE orders (
        id INT PRIMARY KEY,
        customer_id INT NOT NULL REFERENCES customers(id),
        amount DECIMAL(10, 2) NOT NULL
    );

    CREATE TABLE order_lines (
        id INT PRIMARY KEY,
        order_id INT NOT NULL,
        line_item VARCHAR(50) NOT NULL,
        CONSTRAINT fk_lines_orders FOREIGN KEY (order_id) REFERENCES orders(id)
    );
    """
    parser = SQLDDLParser()
    graph = parser.parse(sql)

    assert set(graph.tables.keys()) == {"customers", "orders", "order_lines"}

    # Check dependencies
    assert graph.tables["customers"].dependencies == set()
    assert graph.tables["orders"].dependencies == {"customers"}
    assert graph.tables["order_lines"].dependencies == {"orders"}

    # Check topological order
    order = graph.get_topological_order()
    assert order == ["customers", "orders", "order_lines"]


def test_cycle_detection():
    sql = """
    CREATE TABLE table_a (
        id INT PRIMARY KEY,
        b_id INT REFERENCES table_b(id)
    );

    CREATE TABLE table_b (
        id INT PRIMARY KEY,
        a_id INT REFERENCES table_a(id)
    );
    """
    parser = SQLDDLParser()
    graph = parser.parse(sql)

    with pytest.raises(CyclicDependencyError) as exc_info:
        graph.get_topological_order()

    assert "Circular dependency detected" in str(exc_info.value)
