# Samia: Known Limitations, Dialect Constraints & Architectural Boundaries

This document provides a comprehensive technical reference detailing the supported features, dialect-specific limitations, relational DAG boundaries, and known edge cases in the **Samia AI Synthetic Test Data & Edge-Case Generator** engine.

---

## 1. Architectural Scope & Purpose

Samia is designed as an agentic, relational-aware synthetic test data generator and adversarial stress testing harness. It parses SQL DDL schemas and JSON Schema specifications into a Directed Acyclic Graph (DAG) and generates topologically ordered, referentially coherent dataset packs across multi-table relational models.

While Samia supports standard ANSI SQL, PostgreSQL, SQLite, and MySQL dialect conventions, certain specialized database features and non-relational constructs are outside the scope of synthetic row generation or require specific schema modeling considerations.

---

## 2. Unsupported DDL Constructs & Dialect Constraints

| Category | Construct / Feature | Engine Behavior | Recommended Workaround / Remediation |
| :--- | :--- | :--- | :--- |
| **Programmable Objects** | `CREATE PROCEDURE`, `CREATE FUNCTION`, `CREATE TRIGGER` | Ignored by parser; non-fatal | Separate DDL schema definitions from procedural business logic scripts before passing to Samia. |
| **Views & Materialized Views** | `CREATE VIEW`, `CREATE MATERIALIZED VIEW` | Bypassed; only base relational tables (`CREATE TABLE`) are parsed | Generate data for the underlying physical source tables; views will compute dynamically when querying the target database. |
| **Spatial / GIS Types** | PostgreSQL PostGIS `GEOMETRY`, `GEOGRAPHY`, MySQL `POINT`, `POLYGON` | Mapped to `NormalizedType.UNKNOWN`; logged as parser warning; string fallback generated | Define column as `TEXT` with regex pattern or GeoJSON string if spatial validation is required. |
| **Temporal Intervals** | `INTERVAL DAY TO SECOND`, `INTERVAL YEAR TO MONTH` | Mapped to `NormalizedType.UNKNOWN`; logged as warning | Use integer seconds/minutes or standard ISO-8601 duration strings in `VARCHAR`. |
| **Custom Composite Types** | `CREATE TYPE name AS (...)` | Structured composite types not parsed; falls back to text | Model custom composite types as JSON objects (`JSON` / `JSONB`) or separate normalized child tables. |
| **Table Partitioning** | `PARTITION BY RANGE`, `PARTITION BY HASH`, `PARTITION BY LIST` | Base table schema is extracted; partition clauses are ignored | Data generates into the logical root table; the target DBMS will route inserts into underlying physical partitions automatically. |
| **Conditional / Partial Indexes** | `CREATE INDEX idx ON tbl (col) WHERE col IS NOT NULL;` | Bypassed; Samia parses primary keys and unique constraints | Define uniqueness rules using `UNIQUE` table or column constraints rather than external partial indexes. |
| **Dynamic Polymorphic FKs** | Rails-style `commentable_type` + `commentable_id` | Cannot be inferred statically from standard SQL DDL `REFERENCES` | Model explicit foreign keys per entity or use separate association junction tables. |

---

## 3. Relational DAG & Dependency Ordering Boundaries

### 3.1 Cyclic Foreign Key Dependencies
* **Condition**: Two or more tables directly or indirectly reference each other (e.g. Table A $\rightarrow$ Table B and Table B $\rightarrow$ Table A, or $A \rightarrow B \rightarrow C \rightarrow A$).
* **Engine Behavior**: Kahn's topological sort algorithm detects the cycle and raises `CyclicDependencyError` listing the participating cycle tables.
* **Why**: In relational databases enforcing foreign keys (`PRAGMA foreign_keys = ON;`), neither table can be inserted first without deferred transaction constraints (`DEFERRABLE INITIALLY DEFERRED`).
* **Remediation**:
  1. Break the circular dependency by making at least one foreign key column nullable and establishing a hierarchical insertion order.
  2. Split the circular reference into a separate junction / association table.

### 3.2 Non-Nullable Self-Referencing Hierarchy Paradox
* **Condition**: A table references itself where the foreign key column is marked `NOT NULL` (e.g. `manager_id INTEGER NOT NULL REFERENCES employees(id)`).
* **Engine Behavior**: For `nullable` self-referencing keys, Samia seeds root records (e.g. CEO or top-level categories) with `NULL` and links subsequent rows to pre-existing generated IDs. However, if the self-referencing column is `NOT NULL`, inserting row 0 into an empty database creates an unsolvable relational paradox.
* **Remediation**:
  Ensure root hierarchy columns are nullable (`manager_id INT REFERENCES employees(id)` without `NOT NULL`), allowing root tree nodes to exist.

### 3.3 Composite Primary & Foreign Key Alignment
* **Supported**: Multi-column primary keys (e.g., `PRIMARY KEY (tenant_id, user_id)`) and composite foreign keys (`FOREIGN KEY (tenant_id, user_id) REFERENCES tenants(tenant_id, user_id)`).
* **Constraint**: Child tables referencing a composite parent must define identical column counts and compatible types in the matching order. Child rows are sampled as atomic tuples from identical parent rows to guarantee zero foreign key mismatch errors.

---

## 4. Scale, Domain Exhaustion & Uniqueness Limits

### 4.1 Domain Exhaustion on Constrained Unique Columns
* **Condition**: A column is constrained by both a finite discrete domain (e.g. `CHECK (code >= 1 AND code <= 10)` or `CHECK (status IN ('A', 'B', 'C'))`) and a `UNIQUE` constraint.
* **Limit**: Requesting more rows than the domain cardinality ($N > 10$ or $N > 3$) is mathematically impossible without violating uniqueness or range boundaries.
* **Engine Behavior**: Once the domain pool is exhausted, the disambiguator will attempt sequence offsetting, which will eventually be flagged by the validator as a domain bound violation.

### 4.2 In-Memory Generation Scale
* **Tested Limits**:
  * 1 to 5,000 rows per table: Highly optimized in-memory generation ($< 0.5$ seconds for 3,000 multi-table rows).
  * Datasets $\ge 100,000$ rows: Will consume significant host RAM if generated in a single batch. For extreme enterprise scale ($> 1,000,000$ rows), streaming export or batch chunking is recommended.

---

## 5. Dialect Compatibility Matrix

| SQL Dialect | DDL Parsing Support | Data Generation Support | Export Format Compatibility |
| :--- | :--- | :--- | :--- |
| **SQLite 3.x** | Full (`SERIAL`, `INT`, `TEXT`, `CHECK`, `FK`) | Full (Zero constraint violations with `PRAGMA foreign_keys = ON;`) | Native SQL `INSERT`, JSON, CSV, ZIP |
| **PostgreSQL 14+** | Full (`SERIAL`, `BIGSERIAL`, `UUID`, `TIMESTAMP`, `JSONB`, `NUMERIC`) | Full (Supports RFC 5322 email, UUID v4, timestamps) | PostgreSQL compatible SQL statements |
| **MySQL 8.x** | Full (`AUTO_INCREMENT`, `VARCHAR`, `DECIMAL`, `ENUM(...)`) | Full (Supports column-level ENUM and check domains) | MySQL compatible backtick / double-quote SQL |

---

## 6. Best Practices for Samia Schema Definitions

1. **Always Specify Primary Keys**: Ensure each table has an explicit primary key (single or composite) so downstream foreign keys can resolve parent values.
2. **Use Clear Nullability Semantics**: Mark required attributes as `NOT NULL` and optional attributes (such as `completed_at`, `deleted_at`, `notes`) as nullable to produce realistic synthetic distributions.
3. **Declare Enums & Checks**: Use `CHECK (col IN ('val1', 'val2'))` or `ENUM('val1', 'val2')` to instruct Samia to generate exact categorical values.
4. **Deterministic Reproducibility**: Always supply `--seed <int>` when generating datasets for automated QA regression suites to guarantee deterministic row reproduction.
