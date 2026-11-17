"""Unit tests for HappyPathGenerator, StressGenerator, and statistical distributions."""

import pytest

from samia.engine.distributions import (
    sample_categorical,
    sample_exponential,
    sample_lognormal,
    sample_normal,
    sample_poisson,
    sample_uniform,
)
from samia.engine.generator_happy import HappyPathGenerator, RelationalContext
from samia.engine.generator_stress import (
    INT_BOUNDARY_VALUES,
    SQLI_PAYLOADS,
    UNICODE_EMOJI_PAYLOADS,
    XSS_PAYLOADS,
    StressGenerator,
)
from samia.models.schema import ColumnSchema, NormalizedType, TableSchema


def test_statistical_distributions():
    # Uniform
    u = sample_uniform(10.0, 20.0)
    assert 10.0 <= u <= 20.0

    # Normal truncated
    n = sample_normal(mean=50, std_dev=5, min_val=40, max_val=60)
    assert 40 <= n <= 60

    # Lognormal
    ln = sample_lognormal(mean=2.0, sigma=0.5, min_val=1.0)
    assert ln >= 1.0

    # Categorical
    item = sample_categorical(["A", "B", "C"], weights=[1.0, 0.0, 0.0])
    assert item == "A"

    # Poisson
    p = sample_poisson(lam=5.0)
    assert p >= 0


def test_happy_path_generator_reproducibility():
    table = TableSchema(name="users")
    table.add_column(ColumnSchema(name="id", normalized_type=NormalizedType.INTEGER, is_primary_key=True))
    table.add_column(ColumnSchema(name="email", normalized_type=NormalizedType.EMAIL, nullable=False))
    table.add_column(ColumnSchema(name="age", normalized_type=NormalizedType.INTEGER, min_value=18, max_value=80))

    gen1 = HappyPathGenerator(seed=123)
    rows1 = gen1.generate_table_records(table, count=5)

    gen2 = HappyPathGenerator(seed=123)
    rows2 = gen2.generate_table_records(table, count=5)

    assert rows1 == rows2
    assert len(rows1) == 5
    for r in rows1:
        assert "@" in r["email"]
        assert 18 <= r["age"] <= 80


def test_stress_generator_adversarial_values():
    table = TableSchema(name="test_adversarial")
    int_col = ColumnSchema(name="score", normalized_type=NormalizedType.INTEGER, min_value=0, max_value=100)
    str_col = ColumnSchema(name="bio", normalized_type=NormalizedType.STRING, max_length=50)
    table.add_column(int_col)
    table.add_column(str_col)

    stress = StressGenerator(seed=42)

    # Test adversarial integer generation
    adversarial_ints = [stress.generate_adversarial_value(int_col) for _ in range(30)]
    assert any(val in INT_BOUNDARY_VALUES or val in [-1, 101] for val in adversarial_ints)

    # Test adversarial string generation
    adversarial_strs = [stress.generate_adversarial_value(str_col) for _ in range(50)]
    has_sqli = any(val in SQLI_PAYLOADS for val in adversarial_strs)
    has_xss = any(val in XSS_PAYLOADS for val in adversarial_strs)
    has_unicode = any(val in UNICODE_EMOJI_PAYLOADS for val in adversarial_strs)
    has_overflow = any(isinstance(val, str) and len(val) > 50 for val in adversarial_strs)

    assert has_sqli or has_xss or has_unicode or has_overflow


def test_foreign_key_preservation_in_stress_mutation():
    table = TableSchema(name="child")
    table.add_column(ColumnSchema(name="id", normalized_type=NormalizedType.INTEGER, is_primary_key=True))
    table.add_column(
        ColumnSchema(
            name="parent_id",
            normalized_type=NormalizedType.INTEGER,
            is_foreign_key=True,
            foreign_key_ref=("parent", "id"),
        )
    )
    table.add_column(ColumnSchema(name="notes", normalized_type=NormalizedType.STRING))

    stress = StressGenerator(seed=99)
    base_row = {"id": 1, "parent_id": 42, "notes": "normal note"}

    # With corrupt_foreign_keys=False, parent_id must NEVER be corrupted
    for _ in range(20):
        mutated = stress.mutate_row(base_row, table, mutation_rate=1.0, corrupt_foreign_keys=False)
        assert mutated["parent_id"] == 42
        assert mutated["id"] == 1  # Primary keys are also preserved


def test_generate_targeted_15_rows():
    table = TableSchema(name="users")
    table.add_column(ColumnSchema(name="id", normalized_type=NormalizedType.INTEGER, is_primary_key=True))
    table.add_column(ColumnSchema(name="username", normalized_type=NormalizedType.STRING, nullable=False))
    table.add_column(ColumnSchema(name="email", normalized_type=NormalizedType.EMAIL, nullable=False))
    table.add_column(ColumnSchema(name="age", normalized_type=NormalizedType.INTEGER, min_value=18, max_value=100))
    table.add_column(ColumnSchema(name="created_at", normalized_type=NormalizedType.TIMESTAMP, nullable=False))

    stress = StressGenerator(seed=123)
    rows = stress.generate_targeted_15_rows(table)

    assert len(rows) == 15
    # Verify primary key presence across all 15 rows
    assert all("id" in r for r in rows)
    # Check null injection
    assert any(r["username"] is None or r["email"] is None for r in rows)
    # Check int overflow
    assert any(r["age"] == 2147483648 for r in rows)
    # Check negative violation
    assert any(r["age"] == -999 for r in rows)
    # Check SQLi
    assert any("' OR '1'='1" in str(r.values()) for r in rows)
    # Check XSS
    assert any("<script>" in str(r.values()) for r in rows)
    # Check Unicode emojis
    assert any(any("🔥" in str(v) for v in r.values()) for r in rows)
    # Check Zalgo combining diacritics
    assert any(any("\u0336" in str(v) for v in r.values()) for r in rows)
    # Check Temporal
    assert any(any("2038" in str(v) for v in r.values()) for r in rows)
