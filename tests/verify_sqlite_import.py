"""Local SQLite Execution & Import Verification Runner.

Generates realistic happy-path packs across multiple schemas and scale levels,
exports topological SQL INSERT scripts, and executes them against a local SQLite
database with `PRAGMA foreign_keys = ON;`.
Verifies:
1. Zero syntax errors.
2. Zero foreign key constraint violations (`PRAGMA foreign_key_check`).
3. 100% record count reconciliation between generated and loaded datasets.
Captures and writes a structured audit log to `exports/sqlite_verification.log`.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from samia.engine.orchestrator import GenerationMode, GenerationOrchestrator
from samia.parsers.sql_parser import SQLDDLParser
from samia.validator.pydantic_validator import PydanticValidator


PACKS: List[Tuple[str, str, int]] = [
    (
        "E-Commerce Multi-Table DAG (6 tables)",
        Path("examples/ecommerce.sql").read_text(encoding="utf-8") if Path("examples/ecommerce.sql").exists() else """
CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR(50) NOT NULL UNIQUE, email VARCHAR(255) NOT NULL UNIQUE, full_name VARCHAR(100) NOT NULL, created_at TIMESTAMP NOT NULL);
CREATE TABLE categories (id SERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, slug VARCHAR(120) NOT NULL UNIQUE);
CREATE TABLE products (id SERIAL PRIMARY KEY, category_id INT NOT NULL REFERENCES categories(id), title VARCHAR(150) NOT NULL, sku VARCHAR(50) NOT NULL UNIQUE, price DECIMAL(10, 2) NOT NULL, created_at TIMESTAMP NOT NULL);
CREATE TABLE orders (id SERIAL PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id), status VARCHAR(30) NOT NULL, total_amount DECIMAL(10, 2) NOT NULL, created_at TIMESTAMP NOT NULL);
CREATE TABLE order_items (id SERIAL PRIMARY KEY, order_id INT NOT NULL REFERENCES orders(id), product_id INT NOT NULL REFERENCES products(id), quantity INT NOT NULL, unit_price DECIMAL(10, 2) NOT NULL);
CREATE TABLE reviews (id SERIAL PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id), product_id INT NOT NULL REFERENCES products(id), rating INT NOT NULL, created_at TIMESTAMP NOT NULL);
""",
        50,
    ),
    (
        "Self-Referencing Table (Employees & Managers)",
        """
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    manager_id INTEGER REFERENCES employees(id),
    department VARCHAR(50) NOT NULL,
    salary DECIMAL(10, 2) NOT NULL CHECK (salary >= 30000.00)
);
""",
        40,
    ),
    (
        "Composite Keys & Multi-Column Foreign Keys (Tenants & Roles)",
        """
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
""",
        30,
    ),
    (
        "Deep Sequential 5-Tier Dependency Chain (Corporations to Projects)",
        """
CREATE TABLE corporations (id SERIAL PRIMARY KEY, corp_name VARCHAR(100) NOT NULL UNIQUE);
CREATE TABLE subsidiaries (id SERIAL PRIMARY KEY, corp_id INT NOT NULL REFERENCES corporations(id), sub_name VARCHAR(100) NOT NULL);
CREATE TABLE divisions (id SERIAL PRIMARY KEY, sub_id INT NOT NULL REFERENCES subsidiaries(id), div_name VARCHAR(100) NOT NULL);
CREATE TABLE teams (id SERIAL PRIMARY KEY, div_id INT NOT NULL REFERENCES divisions(id), team_name VARCHAR(100) NOT NULL);
CREATE TABLE projects (id SERIAL PRIMARY KEY, team_id INT NOT NULL REFERENCES teams(id), project_title VARCHAR(150) NOT NULL);
""",
        25,
    ),
    (
        "Financial Transaction Ledger (Precision & Scale)",
        """
CREATE TABLE financial_ledger (
    entry_id SERIAL PRIMARY KEY,
    account_id INT NOT NULL,
    entry_type VARCHAR(10) NOT NULL CHECK (entry_type IN ('debit', 'credit')),
    amount DECIMAL(14, 4) NOT NULL CHECK (amount >= 0.0100 AND amount <= 5000000.0000),
    fee DECIMAL(8, 4) NOT NULL CHECK (fee >= 0.0000 AND fee <= 500.0000),
    transaction_timestamp TIMESTAMP NOT NULL
);
""",
        100,
    ),
    (
        "Large-Scale 500-Row E-Commerce Stress Load (3,000 total records)",
        Path("examples/ecommerce.sql").read_text(encoding="utf-8"),
        500,
    ),
]


def run_sqlite_verification(log_file_path: Optional[Path] = None) -> Tuple[bool, str]:
    """Execute all verification packs and generate a comprehensive verification log."""
    log_lines: List[str] = []
    log_lines.append("=" * 80)
    log_lines.append("SAMIA - LOCAL SQLITE IMPORT & REFERENTIAL INTEGRITY VERIFICATION LOG")
    log_lines.append(f"Timestamp: {datetime.datetime.now().isoformat()}")
    log_lines.append(f"SQLite Version: {sqlite3.sqlite_version}")
    log_lines.append(f"Enforcement Mode: PRAGMA foreign_keys = ON;")
    log_lines.append("=" * 80)
    log_lines.append("")

    all_passed = True
    total_packs = len(PACKS)
    total_records_inserted = 0

    for idx, (pack_name, ddl_sql, row_count) in enumerate(PACKS, 1):
        log_lines.append(f"--- [Pack {idx}/{total_packs}]: {pack_name} ---")
        log_lines.append(f"Target Row Count per Table: {row_count}")

        t0 = time.perf_counter()
        # Parse DDL
        parser = SQLDDLParser()
        graph = parser.parse(ddl_sql)
        topological_order = graph.get_topological_order()
        log_lines.append(f"Topological Execution Order: {' -> '.join(topological_order)}")

        # Orchestrate generation
        orch = GenerationOrchestrator(graph, seed=42)
        gen_res = orch.generate(mode=GenerationMode.HAPPY, default_count=row_count)
        gen_duration = time.perf_counter() - t0
        log_lines.append(f"Generated {gen_res.total_records} records in {gen_duration:.3f}s")

        # Validate with Pydantic
        validator = PydanticValidator(graph)
        report = validator.validate_dataset(gen_res.data, graph)
        log_lines.append(f"Pydantic Constraint Pass Rate: {report.pass_rate:.2f}%")

        # Export SQL INSERT statements
        sql_inserts = gen_res.to_sql_string()

        # Connect to fresh local SQLite DB
        db_path = f":memory:"
        con = sqlite3.connect(db_path)
        con.execute("PRAGMA foreign_keys = ON;")

        t_db0 = time.perf_counter()
        try:
            # 1. Execute DDL
            con.executescript(ddl_sql)

            # 2. Execute Inserts
            con.executescript(sql_inserts)
            con.commit()
            db_duration = time.perf_counter() - t_db0

            # 3. Check for any foreign key violations
            fk_violations = con.execute("PRAGMA foreign_key_check;").fetchall()
            if fk_violations:
                log_lines.append(f"❌ FOREIGN KEY VIOLATIONS DETECTED: {fk_violations}")
                all_passed = False
            else:
                log_lines.append("✓ PRAGMA foreign_key_check: ZERO constraint violations detected.")

            # 4. Reconcile loaded counts
            table_counts = {}
            for tbl in topological_order:
                count = con.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
                expected = len(gen_res.data.get(tbl, []))
                table_counts[tbl] = count
                assert count == expected, f"Count mismatch for {tbl}: expected {expected}, got {count}"
                log_lines.append(f"  • Table `{tbl}`: {count}/{expected} rows loaded successfully.")

            total_records_inserted += sum(table_counts.values())
            log_lines.append(f"✓ SQLite execution succeeded in {db_duration:.3f}s. Zero syntax or integrity errors.")
            log_lines.append(f"Status: PASS\n")
        except Exception as exc:
            all_passed = False
            log_lines.append(f"❌ SQLite Execution Failed: {exc}")
            log_lines.append(f"Status: FAIL\n")
        finally:
            con.close()

    log_lines.append("=" * 80)
    log_lines.append("SUMMARY RESULTS:")
    log_lines.append(f"Total Packs Executed: {total_packs}")
    log_lines.append(f"Total Records Loaded across all Packs: {total_records_inserted}")
    log_lines.append(f"Final Verification Status: {'ALL PACKS PASSED (100% CLEAN)' if all_passed else 'FAILURES DETECTED'}")
    log_lines.append("=" * 80)

    log_text = "\n".join(log_lines)

    if log_file_path:
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        log_file_path.write_text(log_text, encoding="utf-8")

    return all_passed, log_text


if __name__ == "__main__":
    out_file = Path("exports/sqlite_verification.log")
    passed, log_output = run_sqlite_verification(out_file)
    print(log_output)
    print(f"\nLog captured to: {out_file.resolve()}")
    sys.exit(0 if passed else 1)
