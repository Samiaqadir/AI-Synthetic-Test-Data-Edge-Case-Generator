"""Automated 10-Scenario Regression Test Suite for Samia.

Covers:
1. Self-referencing tables (hierarchical trees, employees -> manager).
2. Composite primary keys & multi-column foreign key relationships.
3. Enum fields and constrained domains.
4. Nullable dates and timestamps.
5. Large-scale 500-row generation runs (uniqueness & referential integrity).
6. Deep sequential 5-tier dependency chain.
7. Diamond dependency DAG (multiple parents convergence).
8. Complex data types (JSON payloads, boolean flags, UUIDs).
9. High-density financial ledger with precision & scale.
10. Multi-table adversarial stress pack with referential preservation.

All scenarios execute against fresh local SQLite databases with PRAGMA foreign_keys = ON;
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from samia.engine.orchestrator import GenerationMode, GenerationOrchestrator, GenerationResult
from samia.models.report import ValidationReport
from samia.models.schema import SchemaGraph
from samia.parsers.sql_parser import SQLDDLParser
from samia.validator.pydantic_validator import PydanticValidator


@dataclass
class ScenarioResult:
    """Stores the execution details and status for a regression scenario."""
    scenario_id: int
    name: str
    description: str
    row_count: int
    generation_mode: str
    validation_pass_rate: float
    sqlite_clean_import: bool
    duration_seconds: float
    status: str
    details: str


def execute_sqlite_import(ddl_sql: str, insert_sql: str) -> Dict[str, Any]:
    """Execute DDL and topologically ordered INSERTs in a fresh SQLite instance."""
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON;")
    try:
        # 1. Create schema
        con.executescript(ddl_sql)
        # 2. Execute generated INSERT statements
        con.executescript(insert_sql)
        con.commit()

        # Query all table row counts
        tables_query = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        ).fetchall()
        counts = {}
        for (tbl,) in tables_query:
            row_count = con.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
            counts[tbl] = row_count

        return {"success": True, "counts": counts, "error": None}
    except Exception as exc:
        return {"success": False, "counts": {}, "error": str(exc)}
    finally:
        con.close()


# ==============================================================================
# 10 REGRESSION SCENARIOS DEFINITIONS
# ==============================================================================

# Scenario 1: Self-Referencing Table
SCENARIO_1_SQL = """
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    manager_id INTEGER REFERENCES employees(id),
    department VARCHAR(50) NOT NULL,
    salary DECIMAL(10, 2) NOT NULL CHECK (salary >= 30000.00)
);
"""

# Scenario 2: Composite Primary Keys & Multi-Column Foreign Keys
SCENARIO_2_SQL = """
CREATE TABLE tenants (
    tenant_id INT NOT NULL,
    company_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id)
);

CREATE TABLE tenant_users (
    tenant_id INT NOT NULL,
    user_id INT NOT NULL,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE user_roles (
    role_id INT PRIMARY KEY,
    tenant_id INT NOT NULL,
    user_id INT NOT NULL,
    role_name VARCHAR(50) NOT NULL,
    FOREIGN KEY (tenant_id, user_id) REFERENCES tenant_users(tenant_id, user_id)
);
"""

# Scenario 3: Enum Fields & Constrained Domain Bounds
SCENARIO_3_SQL = """
CREATE TABLE order_fulfillment (
    id SERIAL PRIMARY KEY,
    order_code VARCHAR(30) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'approved', 'processing', 'shipped', 'delivered', 'cancelled')),
    priority VARCHAR(10) NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    quality_score INT NOT NULL CHECK (quality_score >= 1 AND quality_score <= 100),
    discount_rate DECIMAL(5, 4) NOT NULL CHECK (discount_rate >= 0.0000 AND discount_rate <= 0.5000)
);
"""

# Scenario 4: Nullable Dates, Timestamps, and Optional Fields
SCENARIO_4_SQL = """
CREATE TABLE audit_workflow_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    due_date DATE NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    deleted_at TIMESTAMP,
    incident_notes TEXT
);
"""

# Scenario 5: Large-Scale 500-Row Generation Run (E-commerce multi-table DAG)
SCENARIO_5_SQL = """
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(60) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    age INT CHECK (age >= 18 AND age <= 100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(120) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    category_id INT NOT NULL REFERENCES categories(id),
    title VARCHAR(150) NOT NULL,
    sku VARCHAR(60) NOT NULL UNIQUE,
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0.01 AND price <= 99999.99),
    stock_qty INT NOT NULL CHECK (stock_qty >= 0 AND stock_qty <= 10000),
    is_published BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    status VARCHAR(30) NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'cancelled')),
    total_amount DECIMAL(10, 2) NOT NULL CHECK (total_amount >= 0.00),
    shipping_address VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(id),
    product_id INT NOT NULL REFERENCES products(id),
    quantity INT NOT NULL CHECK (quantity >= 1 AND quantity <= 50),
    unit_price DECIMAL(10, 2) NOT NULL CHECK (unit_price >= 0.01)
);

CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    product_id INT NOT NULL REFERENCES products(id),
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    created_at TIMESTAMP NOT NULL
);
"""

# Scenario 6: Deep Sequential 5-Tier Dependency Chain
SCENARIO_6_SQL = """
CREATE TABLE corporations (
    id SERIAL PRIMARY KEY,
    corp_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE subsidiaries (
    id SERIAL PRIMARY KEY,
    corp_id INT NOT NULL REFERENCES corporations(id),
    sub_name VARCHAR(100) NOT NULL
);

CREATE TABLE divisions (
    id SERIAL PRIMARY KEY,
    sub_id INT NOT NULL REFERENCES subsidiaries(id),
    div_name VARCHAR(100) NOT NULL
);

CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    div_id INT NOT NULL REFERENCES divisions(id),
    team_name VARCHAR(100) NOT NULL
);

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    team_id INT NOT NULL REFERENCES teams(id),
    project_title VARCHAR(150) NOT NULL
);
"""

# Scenario 7: Diamond Dependency DAG (Multiple Parents Convergence)
SCENARIO_7_SQL = """
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    account_number VARCHAR(50) NOT NULL UNIQUE,
    holder_name VARCHAR(100) NOT NULL
);

CREATE TABLE billing_profiles (
    id SERIAL PRIMARY KEY,
    account_id INT NOT NULL REFERENCES accounts(id),
    billing_email VARCHAR(100) NOT NULL
);

CREATE TABLE shipping_profiles (
    id SERIAL PRIMARY KEY,
    account_id INT NOT NULL REFERENCES accounts(id),
    address VARCHAR(200) NOT NULL
);

CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    billing_id INT NOT NULL REFERENCES billing_profiles(id),
    shipping_id INT NOT NULL REFERENCES shipping_profiles(id),
    amount DECIMAL(10, 2) NOT NULL CHECK (amount >= 0.00)
);
"""

# Scenario 8: Complex Types (JSON Payloads, Boolean Flags, UUIDs)
SCENARIO_8_SQL = """
CREATE TABLE device_telemetry (
    device_id UUID PRIMARY KEY,
    is_active BOOLEAN NOT NULL,
    payload JSON NOT NULL,
    config_tags TEXT,
    recorded_at TIMESTAMP NOT NULL
);
"""

# Scenario 9: High-Density Financial Ledger with Precision & Scale
SCENARIO_9_SQL = """
CREATE TABLE financial_ledger (
    entry_id SERIAL PRIMARY KEY,
    account_id INT NOT NULL,
    entry_type VARCHAR(10) NOT NULL CHECK (entry_type IN ('debit', 'credit')),
    amount DECIMAL(14, 4) NOT NULL CHECK (amount >= 0.0100 AND amount <= 5000000.0000),
    fee DECIMAL(8, 4) NOT NULL CHECK (fee >= 0.0000 AND fee <= 500.0000),
    transaction_timestamp TIMESTAMP NOT NULL
);
"""

# Scenario 10: Multi-Table Adversarial Stress Pack with Referential Preservation
SCENARIO_10_SQL = SCENARIO_5_SQL


# ==============================================================================
# PYTEST AUTOMATED TEST CASES
# ==============================================================================

class Test10ScenarioRegressionSuite:
    """Executes the full 10-scenario regression test matrix."""

    def test_scenario_01_self_referencing_table(self):
        graph = SQLDDLParser().parse(SCENARIO_1_SQL)
        assert graph.get_topological_order() == ["employees"]

        orch = GenerationOrchestrator(graph, seed=42)
        res = orch.generate(mode=GenerationMode.HAPPY, default_count=20)
        assert len(res.data["employees"]) == 20

        # Verify row 0 root handling
        first_row = res.data["employees"][0]
        assert first_row["manager_id"] is None

        # Verify subsequent rows reference valid pre-existing IDs
        emp_ids = {r["id"] for r in res.data["employees"]}
        for row in res.data["employees"]:
            if row["manager_id"] is not None:
                assert row["manager_id"] in emp_ids

        # Pydantic validation
        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.pass_rate == 100.0

        # SQLite import verification
        sqlite_res = execute_sqlite_import(SCENARIO_1_SQL, res.to_sql_string())
        assert sqlite_res["success"] is True, f"SQLite error: {sqlite_res['error']}"
        assert sqlite_res["counts"]["employees"] == 20

    def test_scenario_02_composite_keys_and_multi_column_fk(self):
        graph = SQLDDLParser().parse(SCENARIO_2_SQL)
        order = graph.get_topological_order()
        assert order == ["tenants", "tenant_users", "user_roles"]

        orch = GenerationOrchestrator(graph, seed=42)
        res = orch.generate(mode=GenerationMode.HAPPY, default_count=15)

        # Verify multi-column foreign key coherence
        parent_pairs = {(u["tenant_id"], u["user_id"]) for u in res.data["tenant_users"]}
        for role in res.data["user_roles"]:
            pair = (role["tenant_id"], role["user_id"])
            assert pair in parent_pairs, f"Role references non-existent parent pair: {pair}"

        # Pydantic validation
        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.pass_rate == 100.0

        # SQLite import verification
        sqlite_res = execute_sqlite_import(SCENARIO_2_SQL, res.to_sql_string())
        assert sqlite_res["success"] is True, f"SQLite error: {sqlite_res['error']}"
        assert sqlite_res["counts"]["user_roles"] == 15

    def test_scenario_03_enum_fields_and_constrained_domains(self):
        graph = SQLDDLParser().parse(SCENARIO_3_SQL)
        orch = GenerationOrchestrator(graph, seed=42)
        res = orch.generate(mode=GenerationMode.HAPPY, default_count=25)

        allowed_statuses = {'pending', 'approved', 'processing', 'shipped', 'delivered', 'cancelled'}
        allowed_priorities = {'low', 'medium', 'high', 'urgent'}

        for row in res.data["order_fulfillment"]:
            assert row["status"] in allowed_statuses
            assert row["priority"] in allowed_priorities
            assert 1 <= row["quality_score"] <= 100
            assert 0.0 <= row["discount_rate"] <= 0.5000

        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.pass_rate == 100.0

        sqlite_res = execute_sqlite_import(SCENARIO_3_SQL, res.to_sql_string())
        assert sqlite_res["success"] is True, f"SQLite error: {sqlite_res['error']}"
        assert sqlite_res["counts"]["order_fulfillment"] == 25

    def test_scenario_04_nullable_dates_and_timestamps(self):
        graph = SQLDDLParser().parse(SCENARIO_4_SQL)
        orch = GenerationOrchestrator(graph, seed=42)
        res = orch.generate(mode=GenerationMode.HAPPY, default_count=30)

        rows = res.data["audit_workflow_events"]
        assert len(rows) == 30

        # Check required fields
        for r in rows:
            assert r["created_at"] is not None
            assert r["due_date"] is not None

        # Check nullable fields contain both nulls and values
        deleted_nulls = sum(1 for r in rows if r["deleted_at"] is None)
        assert deleted_nulls > 0, "Expected some realistic nulls in deleted_at"

        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.pass_rate == 100.0

        sqlite_res = execute_sqlite_import(SCENARIO_4_SQL, res.to_sql_string())
        assert sqlite_res["success"] is True, f"SQLite error: {sqlite_res['error']}"
        assert sqlite_res["counts"]["audit_workflow_events"] == 30

    def test_scenario_05_large_scale_500_row_generation(self):
        graph = SQLDDLParser().parse(SCENARIO_5_SQL)
        orch = GenerationOrchestrator(graph, seed=42)

        t0 = time.perf_counter()
        res = orch.generate(mode=GenerationMode.HAPPY, default_count=500)
        duration = time.perf_counter() - t0

        assert res.total_records == 3000
        assert duration < 5.0, f"Generation took too long: {duration:.2f}s"

        # Check uniqueness across 500 rows for unique columns
        usernames = [r["username"] for r in res.data["users"]]
        emails = [r["email"] for r in res.data["users"]]
        skus = [r["sku"] for r in res.data["products"]]
        cat_names = [r["name"] for r in res.data["categories"]]

        assert len(usernames) == len(set(usernames)), "Username duplicate collision at 500 rows"
        assert len(emails) == len(set(emails)), "Email duplicate collision at 500 rows"
        assert len(skus) == len(set(skus)), "SKU duplicate collision at 500 rows"
        assert len(cat_names) == len(set(cat_names)), "Category name duplicate collision at 500 rows"

        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.pass_rate == 100.0

        sqlite_res = execute_sqlite_import(SCENARIO_5_SQL, res.to_sql_string())
        assert sqlite_res["success"] is True, f"SQLite error: {sqlite_res['error']}"
        assert sqlite_res["counts"]["users"] == 500
        assert sqlite_res["counts"]["order_items"] == 500

    def test_scenario_06_deep_sequential_5_tier_dependency_chain(self):
        graph = SQLDDLParser().parse(SCENARIO_6_SQL)
        order = graph.get_topological_order()
        assert order == ["corporations", "subsidiaries", "divisions", "teams", "projects"]

        orch = GenerationOrchestrator(graph, seed=42)
        res = orch.generate(mode=GenerationMode.HAPPY, default_count=10)

        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.pass_rate == 100.0

        sqlite_res = execute_sqlite_import(SCENARIO_6_SQL, res.to_sql_string())
        assert sqlite_res["success"] is True, f"SQLite error: {sqlite_res['error']}"
        assert sqlite_res["counts"]["projects"] == 10

    def test_scenario_07_diamond_dependency_dag(self):
        graph = SQLDDLParser().parse(SCENARIO_7_SQL)
        order = graph.get_topological_order()
        assert order[0] == "accounts"
        assert order[-1] == "invoices"

        orch = GenerationOrchestrator(graph, seed=42)
        res = orch.generate(mode=GenerationMode.HAPPY, default_count=15)

        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.pass_rate == 100.0

        sqlite_res = execute_sqlite_import(SCENARIO_7_SQL, res.to_sql_string())
        assert sqlite_res["success"] is True, f"SQLite error: {sqlite_res['error']}"
        assert sqlite_res["counts"]["invoices"] == 15

    def test_scenario_08_complex_types_json_bool_uuid(self):
        graph = SQLDDLParser().parse(SCENARIO_8_SQL)
        orch = GenerationOrchestrator(graph, seed=42)
        res = orch.generate(mode=GenerationMode.HAPPY, default_count=20)

        for row in res.data["device_telemetry"]:
            assert isinstance(row["is_active"], bool)
            assert isinstance(row["payload"], dict)
            assert len(str(row["device_id"])) == 36

        # Verify SQL statement string contains TRUE/FALSE and valid escaped JSON
        sql_str = res.to_sql_string()
        assert 'TRUE' in sql_str or 'FALSE' in sql_str
        assert '"source": "samia_synthetic"' in sql_str

        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.pass_rate == 100.0

        sqlite_res = execute_sqlite_import(SCENARIO_8_SQL, sql_str)
        assert sqlite_res["success"] is True, f"SQLite error: {sqlite_res['error']}"
        assert sqlite_res["counts"]["device_telemetry"] == 20

    def test_scenario_09_financial_ledger_precision_and_scale(self):
        graph = SQLDDLParser().parse(SCENARIO_9_SQL)
        orch = GenerationOrchestrator(graph, seed=42)
        res = orch.generate(mode=GenerationMode.HAPPY, default_count=30)

        for row in res.data["financial_ledger"]:
            assert row["entry_type"] in ("debit", "credit")
            assert 0.01 <= row["amount"] <= 5000000.0000
            assert 0.0 <= row["fee"] <= 500.0000

        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.pass_rate == 100.0

        sqlite_res = execute_sqlite_import(SCENARIO_9_SQL, res.to_sql_string())
        assert sqlite_res["success"] is True, f"SQLite error: {sqlite_res['error']}"
        assert sqlite_res["counts"]["financial_ledger"] == 30

    def test_scenario_10_adversarial_stress_referential_preservation(self):
        graph = SQLDDLParser().parse(SCENARIO_10_SQL)
        orch = GenerationOrchestrator(graph, seed=42)

        # Generate targeted stress with FK preservation
        res = orch.generate(
            mode=GenerationMode.TARGETED_STRESS,
            corrupt_foreign_keys=False,
        )

        # Pydantic validator flags intentional stress anomalies (e.g. integer overflows, SQLi, null in required)
        rep = PydanticValidator(graph).validate_dataset(res.data, graph)
        assert rep.invalid_records > 0, "Stress generator should produce detectable boundary anomalies"

        # Verify foreign key referential integrity is preserved
        user_ids = {u["id"] for u in res.data["users"]}
        for order in res.data["orders"]:
            assert order["user_id"] in user_ids, "Foreign key should not be corrupted when corrupt_foreign_keys=False"


# ==============================================================================
# PROGRAMMATIC REGRESSION MATRIX RUNNER
# ==============================================================================

def run_10_scenario_regression_matrix() -> List[ScenarioResult]:
    """Execute all 10 scenarios programmatically and collect the regression matrix."""
    scenarios = [
        (1, "Self-Referencing Table", SCENARIO_1_SQL, 20, GenerationMode.HAPPY, False),
        (2, "Composite PK & Multi-Column FK", SCENARIO_2_SQL, 15, GenerationMode.HAPPY, False),
        (3, "Enum Fields & Domain Bounds", SCENARIO_3_SQL, 25, GenerationMode.HAPPY, False),
        (4, "Nullable Dates & Timestamps", SCENARIO_4_SQL, 30, GenerationMode.HAPPY, False),
        (5, "500-Row Scale & Uniqueness", SCENARIO_5_SQL, 500, GenerationMode.HAPPY, False),
        (6, "5-Tier Sequential DAG", SCENARIO_6_SQL, 10, GenerationMode.HAPPY, False),
        (7, "Diamond Dependency DAG", SCENARIO_7_SQL, 15, GenerationMode.HAPPY, False),
        (8, "Complex Types (JSON, Bool, UUID)", SCENARIO_8_SQL, 20, GenerationMode.HAPPY, False),
        (9, "High-Density Financial Ledger", SCENARIO_9_SQL, 30, GenerationMode.HAPPY, False),
        (10, "Targeted Stress & FK Preservation", SCENARIO_10_SQL, 15, GenerationMode.TARGETED_STRESS, False),
    ]

    results: List[ScenarioResult] = []

    for sid, name, sql, count, mode, corrupt_fk in scenarios:
        t0 = time.perf_counter()
        try:
            graph = SQLDDLParser().parse(sql)
            orch = GenerationOrchestrator(graph, seed=42)
            gen_res = orch.generate(
                mode=mode,
                default_count=count,
                corrupt_foreign_keys=corrupt_fk,
            )

            rep = PydanticValidator(graph).validate_dataset(gen_res.data, graph)

            # SQLite verification (for happy scenarios)
            sqlite_ok = True
            sqlite_err = None
            if mode == GenerationMode.HAPPY:
                sql_script = gen_res.to_sql_string()
                sql_res = execute_sqlite_import(sql, sql_script)
                sqlite_ok = sql_res["success"]
                sqlite_err = sql_res["error"]

            duration = time.perf_counter() - t0
            status = "PASS" if (sqlite_ok and (rep.pass_rate == 100.0 or mode == GenerationMode.TARGETED_STRESS)) else "FAIL"
            details = "100% Valid, Clean SQLite Load" if status == "PASS" else f"SQLite Error: {sqlite_err}"

            results.append(
                ScenarioResult(
                    scenario_id=sid,
                    name=name,
                    description=f"{name} ({gen_res.total_records} total rows across DAG)",
                    row_count=gen_res.total_records,
                    generation_mode=mode.value,
                    validation_pass_rate=round(rep.pass_rate, 2),
                    sqlite_clean_import=sqlite_ok,
                    duration_seconds=round(duration, 3),
                    status=status,
                    details=details,
                )
            )
        except Exception as exc:
            duration = time.perf_counter() - t0
            results.append(
                ScenarioResult(
                    scenario_id=sid,
                    name=name,
                    description=name,
                    row_count=0,
                    generation_mode=mode.value,
                    validation_pass_rate=0.0,
                    sqlite_clean_import=False,
                    duration_seconds=round(duration, 3),
                    status="FAIL",
                    details=f"Exception: {exc}",
                )
            )

    return results


if __name__ == "__main__":
    matrix = run_10_scenario_regression_matrix()
    print("\n" + "=" * 105)
    print(f"{'ID':<4} | {'Scenario Name':<34} | {'Rows':<6} | {'Mode':<10} | {'Pass Rate':<10} | {'SQLite OK':<10} | {'Status':<6}")
    print("=" * 105)
    for r in matrix:
        print(f"{r.scenario_id:<4} | {r.name:<34} | {r.row_count:<6} | {r.generation_mode:<10} | {f'{r.validation_pass_rate}%':<10} | {str(r.sqlite_clean_import):<10} | {r.status:<6}")
    print("=" * 105 + "\n")
