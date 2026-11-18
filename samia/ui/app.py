"""
Streamlit Web UI for Samia AI Synthetic Test Data & Edge-Case Generator.
Allows QA engineers to upload schemas, configure row counts, toggle Happy-Path vs Adversarial QA modes,
inspect constraint validation pass/fail badges, review row-level violation highlights, and download multi-format export bundles.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from samia.engine.orchestrator import (
    GenerationMode,
    GenerationOrchestrator,
    GenerationResult,
)
from samia.models.report import ValidationReport
from samia.models.schema import NormalizedType, SchemaGraph, TableSchema
from samia.parsers.json_parser import JSONSchemaParser
from samia.parsers.sql_parser import SQLDDLParser
from samia.validator.pydantic_validator import PydanticValidator

# Preloaded Example Schemas
SAMPLE_ECOMMERCE_SQL = """-- E-Commerce Multi-Table Relational Schema with Constraints
-- Models: Users -> Categories -> Products -> Orders -> Order_Items -> Reviews

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
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
    sku VARCHAR(50) NOT NULL UNIQUE,
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

SAMPLE_HEALTHCARE_SQL = """-- Healthcare Clinical & Diagnostic Records Schema
CREATE TABLE patients (
    id SERIAL PRIMARY KEY,
    mrn VARCHAR(20) NOT NULL UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(10) CHECK (gender IN ('male', 'female', 'other')),
    email VARCHAR(255) NOT NULL UNIQUE,
    emergency_phone VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE doctors (
    id SERIAL PRIMARY KEY,
    license_id VARCHAR(30) NOT NULL UNIQUE,
    doctor_name VARCHAR(100) NOT NULL,
    specialty VARCHAR(50) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE appointments (
    id SERIAL PRIMARY KEY,
    patient_id INT NOT NULL REFERENCES patients(id),
    doctor_id INT NOT NULL REFERENCES doctors(id),
    appointment_time TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('scheduled', 'completed', 'cancelled', 'no_show')),
    copay_amount DECIMAL(8, 2) NOT NULL CHECK (copay_amount >= 0.00 AND copay_amount <= 500.00)
);

CREATE TABLE prescriptions (
    id SERIAL PRIMARY KEY,
    appointment_id INT NOT NULL REFERENCES appointments(id),
    medication_name VARCHAR(100) NOT NULL,
    dosage_mg INT NOT NULL CHECK (dosage_mg >= 1 AND dosage_mg <= 2000),
    refills_allowed INT NOT NULL CHECK (refills_allowed >= 0 AND refills_allowed <= 12)
);
"""

SAMPLE_USER_EVENT_JSON = """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UserEvent",
  "type": "object",
  "required": ["event_id", "user_id", "event_type", "timestamp", "session_duration"],
  "properties": {
    "event_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier for the telemetry event"
    },
    "user_id": {
      "type": "integer",
      "minimum": 1,
      "description": "Identifier of the actor user"
    },
    "event_type": {
      "type": "string",
      "enum": ["login", "page_view", "checkout", "logout", "error_triggered"],
      "description": "Categorical event type"
    },
    "ip_address": {
      "type": "string",
      "pattern": "^(?:[0-9]{1,3}\\\\.){3}[0-9]{1,3}$",
      "description": "IPv4 address"
    },
    "user_email": {
      "type": "string",
      "format": "email",
      "maxLength": 100,
      "description": "User email address"
    },
    "session_duration": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 86400.0,
      "description": "Session duration in seconds"
    },
    "device_platform": {
      "type": "string",
      "enum": ["ios", "android", "web", "desktop"]
    },
    "is_premium": {
      "type": "boolean",
      "default": false
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    }
  }
}"""


def parse_input_schema(
    schema_text: str,
    schema_format: str,
    entity_name: str = "entity",
) -> Tuple[Optional[SchemaGraph], Optional[str]]:
    """Parse schema text into a SchemaGraph or return an error message."""
    schema_text = schema_text.strip()
    if not schema_text:
        return None, "Schema input is empty. Please paste or upload a schema."

    try:
        if schema_format.startswith("SQL"):
            parser = SQLDDLParser()
            graph = parser.parse(schema_text)
            if not graph.tables:
                return None, "No CREATE TABLE statements found in SQL input."
            return graph, None
        else:
            parser = JSONSchemaParser()
            table = parser.to_table_schema(entity_name=entity_name, schema=schema_text)
            graph = SchemaGraph()
            graph.add_table(table)
            return graph, None
    except Exception as exc:
        return None, f"Schema Parse Error: {str(exc)}"


def style_preview_table(
    df: pd.DataFrame,
    table_name: str,
    table_summary: Optional[Any],
) -> Any:
    """Apply row-level and cell-level highlight styling to dataframe violations."""
    if table_summary is None or not table_summary.row_violations:
        return df

    def apply_styles(row: pd.Series) -> List[str]:
        r_idx = row.name
        if r_idx in table_summary.row_violations:
            violating_cols = {v.column_name for v in table_summary.row_violations[r_idx]}
            styles = []
            for col_name in row.index:
                if col_name in violating_cols:
                    styles.append(
                        "background-color: #ffcdd2; color: #b71c1c; font-weight: bold; border: 1px solid #e53935;"
                    )
                else:
                    styles.append("background-color: #ffebee; color: #37474f;")
            return styles
        return ["" for _ in row.index]

    return df.style.apply(apply_styles, axis=1)


def main() -> None:
    st.set_page_config(
        page_title="Samia QA Test Data Generator",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS for styling
    st.markdown(
        """
        <style>
        .main-header {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(90deg, #1976d2, #7b1fa2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.2rem;
        }
        .sub-header {
            color: #546e7a;
            font-size: 1.05rem;
            margin-bottom: 1.5rem;
        }
        .badge-card {
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            border-left: 6px solid #ccc;
        }
        .badge-pass {
            background-color: #e8f5e9;
            border-left-color: #2e7d32;
        }
        .badge-fail {
            background-color: #ffebee;
            border-left-color: #c62828;
        }
        .metric-title {
            font-size: 0.85rem;
            font-weight: 700;
            color: #455a64;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .metric-val {
            font-size: 1.8rem;
            font-weight: 800;
            margin-top: 4px;
        }
        .tag-pill {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.78rem;
            font-weight: 600;
            margin: 2px 4px 2px 0;
        }
        .tag-pk { background-color: #e3f2fd; color: #1565c0; border: 1px solid #bbdefb; }
        .tag-fk { background-color: #ede7f6; color: #512da8; border: 1px solid #d1c4e9; }
        .tag-uq { background-color: #fff3e0; color: #e65100; border: 1px solid #ffe0b2; }
        .tag-chk { background-color: #f1f8e9; color: #33691e; border: 1px solid #dcedc8; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="main-header">⚡ Samia: AI Synthetic Test Data & Edge-Case Generator</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Automated Schema-Driven QA Test Data Engine: Topological DAG, Adversarial Stress Vectors, Pydantic Constraint Validator & Multi-Format Seed Bundler</div>', unsafe_allow_html=True)

    # Initialize Session State
    if "generation_result" not in st.session_state:
        st.session_state.generation_result = None
    if "validation_report" not in st.session_state:
        st.session_state.validation_report = None
    if "active_schema_graph" not in st.session_state:
        st.session_state.active_schema_graph = None
    if "schema_content" not in st.session_state:
        st.session_state.schema_content = SAMPLE_ECOMMERCE_SQL
    if "schema_format" not in st.session_state:
        st.session_state.schema_format = "SQL DDL (.sql)"
    if "schema_filename" not in st.session_state:
        st.session_state.schema_filename = "ecommerce.sql"

    # --- SIDEBAR CONFIGURATION ---
    with st.sidebar:
        st.header("⚙️ Configuration & Controls")

        # 1. Schema Input Mode
        st.subheader("1. Schema Definition")
        schema_format = st.radio(
            "Schema Type",
            ["SQL DDL (.sql)", "JSON Schema (.json)"],
            index=0 if "SQL" in st.session_state.schema_format else 1,
            key="cfg_schema_format",
        )

        template_choice = st.selectbox(
            "Load Quick Template",
            [
                "Custom / As-Is",
                "🛒 E-Commerce Relational (6 Tables, FKs, Checks)",
                "🏥 Healthcare Records (Patients, Doctors, Prescriptions)",
                "📊 User Analytics Event (JSON Schema, UUID, Email, IPv4)",
            ],
            key="cfg_template_choice",
        )

        if template_choice.startswith("🛒"):
            st.session_state.schema_content = SAMPLE_ECOMMERCE_SQL
            st.session_state.schema_format = "SQL DDL (.sql)"
            st.session_state.schema_filename = "ecommerce.sql"
        elif template_choice.startswith("🏥"):
            st.session_state.schema_content = SAMPLE_HEALTHCARE_SQL
            st.session_state.schema_format = "SQL DDL (.sql)"
            st.session_state.schema_filename = "healthcare.sql"
        elif template_choice.startswith("📊"):
            st.session_state.schema_content = SAMPLE_USER_EVENT_JSON
            st.session_state.schema_format = "JSON Schema (.json)"
            st.session_state.schema_filename = "user_event.json"

        uploaded_file = st.file_uploader(
            "Upload Schema File",
            type=["sql", "json", "yaml", "yml"],
            help="Upload a SQL DDL file or standard JSON Schema file",
        )
        if uploaded_file is not None:
            uploaded_bytes = uploaded_file.read()
            st.session_state.schema_content = uploaded_bytes.decode("utf-8")
            st.session_state.schema_filename = uploaded_file.name
            if uploaded_file.name.endswith((".json", ".yaml", ".yml")):
                st.session_state.schema_format = "JSON Schema (.json)"
            else:
                st.session_state.schema_format = "SQL DDL (.sql)"
            st.success(f"Uploaded: {uploaded_file.name}")

        schema_text = st.text_area(
            "Schema Source Code",
            value=st.session_state.schema_content,
            height=200,
            help="Directly edit or paste SQL DDL or JSON Schema",
            key="cfg_schema_text",
        )
        st.session_state.schema_content = schema_text

        st.divider()

        # 2. Generation Mode & Row Counts
        st.subheader("2. Generation Strategy")
        mode_choice = st.radio(
            "QA Execution Mode",
            [
                "🟢 Happy-Path (100% Valid & Realistic)",
                "🔴 Adversarial QA (Stress Edge-Cases & Exploits)",
                "🟡 Mixed QA (Configurable Ratio)",
                "🎯 Targeted Stress (15 High-Risk Vectors)",
            ],
            index=1,
            help="Toggle between clean data generation vs adversarial stress testing (SQLi, XSS, INT32/64 overflow, boundary dates, RFC 5322 regex stress)",
        )

        global_row_count = st.slider(
            "Rows per Table",
            min_value=3,
            max_value=100,
            value=10,
            step=1,
            help="Default number of synthetic records generated per table",
        )

        mutation_rate = 0.35
        corrupt_fk = False
        mixed_ratio = 0.30

        if "Mixed QA" in mode_choice:
            mixed_ratio = st.slider(
                "Adversarial Stress Ratio",
                min_value=0.05,
                max_value=0.95,
                value=0.30,
                step=0.05,
                format="%.0f%%",
                help="Proportion of generated rows that will be mutated with adversarial edge cases",
            )
            mutation_rate = st.slider(
                "Field Mutation Rate",
                min_value=0.1,
                max_value=0.9,
                value=0.35,
                step=0.05,
                help="Probability of mutating an eligible non-key field in stress rows",
            )
            corrupt_fk = st.checkbox(
                "Corrupt Foreign Keys (Orphan Test)",
                value=False,
                help="If checked, mutates foreign keys to test detection of orphaned child records",
            )
        elif "Adversarial QA" in mode_choice:
            mutation_rate = st.slider(
                "Field Mutation Rate",
                min_value=0.1,
                max_value=0.9,
                value=0.40,
                step=0.05,
                help="Probability of mutating an eligible field with boundary / exploit payloads",
            )
            corrupt_fk = st.checkbox(
                "Corrupt Foreign Keys (Orphan Test)",
                value=False,
                help="If checked, mutates foreign keys to test detection of orphaned child records",
            )

        with st.expander("🛠️ Advanced Settings", expanded=False):
            use_seed = st.checkbox("Deterministic Random Seed", value=True)
            seed_val = st.number_input("Seed Value", value=42, step=1) if use_seed else None
            entity_name = st.text_input("JSON Root Entity Name", value="UserEvent")

        st.divider()

        # 3. Action Buttons
        generate_clicked = st.button("🚀 Generate & Validate Dataset", type="primary", use_container_width=True)
        parse_only_clicked = st.button("🔍 Parse Schema Only", use_container_width=True)

    # --- EXECUTE ACTIONS ---
    if generate_clicked or parse_only_clicked:
        graph, err = parse_input_schema(
            schema_text=schema_text,
            schema_format=schema_format,
            entity_name=entity_name,
        )
        if err:
            st.error(f"❌ {err}")
        else:
            st.session_state.active_schema_graph = graph

            if generate_clicked:
                with st.spinner("Generating synthetic data and running automated QA validation..."):
                    # Map UI selection to GenerationMode
                    if "Happy-Path" in mode_choice:
                        gen_mode = GenerationMode.HAPPY
                    elif "Targeted Stress" in mode_choice:
                        gen_mode = GenerationMode.TARGETED_STRESS
                    elif "Mixed QA" in mode_choice:
                        gen_mode = GenerationMode.MIXED
                    else:
                        gen_mode = GenerationMode.STRESS

                    orchestrator = GenerationOrchestrator(
                        schema_graph=graph,
                        seed=seed_val,
                    )
                    gen_result = orchestrator.generate(
                        mode=gen_mode,
                        default_count=global_row_count,
                        mutation_rate=mutation_rate,
                        mixed_stress_ratio=mixed_ratio,
                        corrupt_foreign_keys=corrupt_fk,
                    )
                    st.session_state.generation_result = gen_result

                    # Automated QA Validation
                    validator = PydanticValidator(schema_graph=graph)
                    report = validator.validate_dataset(
                        dataset=gen_result.data,
                        schema_graph=graph,
                    )
                    st.session_state.validation_report = report

                st.success("🎉 Data generation and automated QA constraint validation complete!")

    # --- MAIN VIEW TABS ---
    tab_qa, tab_preview, tab_export, tab_schema = st.tabs([
        "📊 Automated QA Validator & Badges",
        "🔍 Data Preview & Constraint Highlights",
        "📦 One-Click Multi-Format Export",
        "📐 Schema & Topological DAG",
    ])

    result: Optional[GenerationResult] = st.session_state.generation_result
    report: Optional[ValidationReport] = st.session_state.validation_report
    graph: Optional[SchemaGraph] = st.session_state.active_schema_graph

    # ==========================================
    # TAB 1: AUTOMATED QA VALIDATOR & BADGES
    # ==========================================
    with tab_qa:
        if not report or not result:
            st.info("👈 Configure schema parameters in the sidebar and click **'🚀 Generate & Validate Dataset'** to begin.")
        else:
            st.subheader("🎯 Automated Post-Generation QA Validation")

            # High-level metrics row
            m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
            with m_col1:
                st.metric("Total Records", report.total_records)
            with m_col2:
                st.metric("Valid Records", report.valid_records)
            with m_col3:
                st.metric("Invalid Records", report.invalid_records)
            with m_col4:
                st.metric("Overall Pass Rate", f"{round(report.pass_rate, 1)}%")
            with m_col5:
                st.metric("Validation Time", f"{round(report.duration_seconds, 3)}s")

            st.markdown("### 🛡️ Automated Constraint Verification Badges")
            st.caption("Checks data types, regex formats, uniqueness constraints, and foreign-key integrity:")

            # 4 Core QA Verification Badges Grid
            b_col1, b_col2, b_col3, b_col4 = st.columns(4)

            categories = [
                ("Data Types", b_col1, "Primitive types, numeric boundaries, enum values, and datetime syntax"),
                ("Regex Formats", b_col2, "RFC 5322 Email syntax, UUID 8-4-4-4-12 hex, and custom schema patterns"),
                ("Uniqueness Constraints", b_col3, "Primary key uniqueness and UNIQUE column duplicate collision checks"),
                ("Foreign-Key Integrity", b_col4, "Parent-to-child relational integrity, detecting orphaned foreign keys"),
            ]

            for cat_name, col, cat_desc in categories:
                badge_info = report.category_badges.get(
                    cat_name,
                    {"status": "PASS", "badge": "🟢 PASS", "count": 0},
                )
                is_pass = badge_info.get("status") == "PASS"
                card_class = "badge-pass" if is_pass else "badge-fail"
                badge_text = "🟢 PASS (100%)" if is_pass else f"🔴 FAIL ({badge_info['count']} violations)"

                with col:
                    st.markdown(
                        f"""
                        <div class="badge-card {card_class}">
                            <div class="metric-title">{cat_name}</div>
                            <div class="metric-val" style="color: {'#2e7d32' if is_pass else '#c62828'};">
                                {badge_text}
                            </div>
                            <div style="font-size: 0.8rem; color: #546e7a; margin-top: 6px;">
                                {cat_desc}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            st.divider()

            # Table-level Pass/Fail Breakdown
            st.markdown("### 📋 Table-by-Table Validation Breakdown")
            tbl_rows = []
            for t_name, t_sum in report.tables.items():
                t_badge = "🟢 PASS" if t_sum.invalid_records == 0 else f"🔴 FAIL ({t_sum.invalid_records})"
                tbl_rows.append({
                    "Table Name": t_name,
                    "Total Records": t_sum.total_records,
                    "Valid Records": t_sum.valid_records,
                    "Invalid Records": t_sum.invalid_records,
                    "Pass Rate (%)": f"{round(t_sum.pass_rate, 1)}%",
                    "Status": t_badge,
                    "Data Types": t_sum.category_badges.get("Data Types", {}).get("badge", "🟢 PASS"),
                    "Regex Formats": t_sum.category_badges.get("Regex Formats", {}).get("badge", "🟢 PASS"),
                    "Uniqueness": t_sum.category_badges.get("Uniqueness Constraints", {}).get("badge", "🟢 PASS"),
                    "Foreign Keys": t_sum.category_badges.get("Foreign-Key Integrity", {}).get("badge", "🟢 PASS"),
                })

            st.dataframe(pd.DataFrame(tbl_rows), use_container_width=True, hide_index=True)

            # Quick Export buttons right inside tab
            st.divider()
            st.markdown("### ⚡ Quick One-Click Download")
            d_col1, d_col2, d_col3, d_col4 = st.columns(4)

            zip_bytes = result.to_zip_bytes(
                validation_report=report,
                schema_content=st.session_state.schema_content,
                schema_filename=st.session_state.schema_filename,
            )
            with d_col1:
                st.download_button(
                    label="📦 Download Complete ZIP Bundle",
                    data=zip_bytes,
                    file_name="qa_test_data_seed_bundle.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True,
                )
            with d_col2:
                st.download_button(
                    label="📄 Download SQL INSERTs (seed.sql)",
                    data=result.to_sql_string(),
                    file_name="seed.sql",
                    mime="text/sql",
                    use_container_width=True,
                )
            with d_col3:
                st.download_button(
                    label="📑 Download JSON Dataset",
                    data=result.to_json_string(),
                    file_name="dataset.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with d_col4:
                st.download_button(
                    label="📊 Download Validation Report (.json)",
                    data=report.to_json(),
                    file_name="validation_report.json",
                    mime="application/json",
                    use_container_width=True,
                )

    # ==========================================
    # TAB 2: DATA PREVIEW & CONSTRAINT HIGHLIGHTS
    # ==========================================
    with tab_preview:
        if not result or not report:
            st.info("👈 Generate data from the sidebar to preview tables and inspect highlighted edge cases.")
        else:
            st.subheader("🔍 Data Preview Tables with Constraint Violation Highlights")
            st.caption("Rows with constraint violations are highlighted in red. Violating cells are marked in bold red. QA engineers can inspect edge cases before download.")

            # Table selection tabs or radio
            table_names = list(result.data.keys())
            selected_table = st.selectbox("Select Table to Inspect", table_names)

            if selected_table:
                rows = result.data.get(selected_table, [])
                t_summary = report.tables.get(selected_table)

                if not rows:
                    st.warning(f"No records generated for table '{selected_table}'.")
                else:
                    df = pd.DataFrame(rows)

                    # Build QA Status column
                    status_col = []
                    for idx in range(len(rows)):
                        if t_summary and idx in t_summary.row_violations:
                            v_count = len(t_summary.row_violations[idx])
                            status_col.append(f"❌ {v_count} Violation{'s' if v_count > 1 else ''}")
                        else:
                            status_col.append("✅ Valid")

                    df.insert(0, "QA_STATUS", status_col)

                    # Filter options
                    f_col1, f_col2 = st.columns([1, 2])
                    with f_col1:
                        filter_opt = st.radio(
                            "Filter Displayed Rows",
                            ["All Rows", "Violations Only ❌", "Valid Rows Only ✅"],
                            horizontal=True,
                        )

                    filtered_df = df
                    if filter_opt == "Violations Only ❌":
                        filtered_df = df[df["QA_STATUS"].str.startswith("❌")]
                    elif filter_opt == "Valid Rows Only ✅":
                        filtered_df = df[df["QA_STATUS"] == "✅ Valid"]

                    st.markdown(f"**Showing {len(filtered_df)} of {len(df)} records for `{selected_table}`:**")

                    # Apply Pandas Styler highlighting
                    styled_df = style_preview_table(filtered_df, selected_table, t_summary)
                    st.dataframe(styled_df, use_container_width=True, hide_index=False)

                    # Row-Level Constraint Violation Inspector Table
                    if t_summary and t_summary.row_violations:
                        st.markdown("#### 🚨 Detailed Row-Level Constraint Violation Inspector")
                        violation_records = []
                        for r_idx, v_list in t_summary.row_violations.items():
                            for v in v_list:
                                val_str = str(v.value)
                                if len(val_str) > 60:
                                    val_str = val_str[:60] + "... [truncated]"
                                violation_records.append({
                                    "Row #": r_idx,
                                    "Column": v.column_name,
                                    "QA Category": v.category,
                                    "Violated Rule": v.rule,
                                    "Offending Value": val_str,
                                    "Diagnostic QA Message": v.message,
                                })

                        v_df = pd.DataFrame(violation_records)
                        st.dataframe(v_df, use_container_width=True, hide_index=True)
                    else:
                        st.success(f"✨ 100% Valid! Zero constraint violations detected in `{selected_table}`.")

    # ==========================================
    # TAB 3: ONE-CLICK MULTI-FORMAT EXPORT
    # ==========================================
    with tab_export:
        if not result or not report:
            st.info("👈 Generate data first to enable multi-format exports.")
        else:
            st.subheader("📦 One-Click Multi-Format Export Center")
            st.markdown("Download all datasets packaged for production testing, database seeding, or QA documentation.")

            exp_col1, exp_col2 = st.columns([1, 1])

            zip_bundle_bytes = result.to_zip_bytes(
                validation_report=report,
                schema_content=st.session_state.schema_content,
                schema_filename=st.session_state.schema_filename,
            )

            with exp_col1:
                st.markdown(
                    """
                    #### 🎁 Production Seed Bundle (.ZIP)
                    Contains complete multi-format assets:
                    - **`sql/seed.sql`**: Topologically ordered `INSERT` statements wrapped in transactions.
                    - **`csv/*.csv`**: Independent CSV file per relational table.
                    - **`json/*.json`**: Consolidated `full_dataset.json` and per-table JSON arrays.
                    - **`reports/validation_report.json`**: Machine-readable QA metrics and violation log.
                    - **`reports/qa_validation_summary.md`**: Human-readable QA acceptance report.
                    - **`schema/*`**: Original source schema definition.
                    """
                )
                st.download_button(
                    label="📦 Download Complete Seed Bundle (.ZIP)",
                    data=zip_bundle_bytes,
                    file_name="qa_test_data_seed_bundle.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True,
                )

            with exp_col2:
                st.markdown("#### 🎯 Individual Artifact Downloads")
                st.download_button(
                    label="📄 Ready-to-Run SQL INSERTs (seed.sql)",
                    data=result.to_sql_string(),
                    file_name="seed.sql",
                    mime="text/sql",
                    use_container_width=True,
                )
                st.download_button(
                    label="📑 Consolidated JSON Dataset (dataset.json)",
                    data=result.to_json_string(),
                    file_name="dataset.json",
                    mime="application/json",
                    use_container_width=True,
                )
                st.download_button(
                    label="📊 QA Validation Report (validation_report.json)",
                    data=report.to_json(),
                    file_name="validation_report.json",
                    mime="application/json",
                    use_container_width=True,
                )
                st.download_button(
                    label="📝 QA Acceptance Summary (validation_summary.md)",
                    data=report.to_markdown_summary(),
                    file_name="validation_summary.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

            st.divider()

            # Interactive Viewers
            st.markdown("### 👁️ In-App Artifact Inspection")
            view_choice = st.radio(
                "Select Asset to Inspect",
                ["SQL INSERTs (seed.sql)", "Consolidated JSON", "QA Markdown Summary"],
                horizontal=True,
            )

            if view_choice == "SQL INSERTs (seed.sql)":
                sql_preview = result.to_sql_string()
                st.code(sql_preview[:4000] + ("\n... [truncated for preview]" if len(sql_preview) > 4000 else ""), language="sql")
            elif view_choice == "Consolidated JSON":
                json_preview = result.to_json_string()
                st.code(json_preview[:4000] + ("\n... [truncated for preview]" if len(json_preview) > 4000 else ""), language="json")
            else:
                st.markdown(report.to_markdown_summary())

    # ==========================================
    # TAB 4: SCHEMA & TOPOLOGICAL DAG
    # ==========================================
    with tab_schema:
        active_graph = graph or st.session_state.active_schema_graph
        if not active_graph:
            # Parse current schema
            active_graph, _ = parse_input_schema(
                schema_text=schema_text,
                schema_format=schema_format,
                entity_name=entity_name,
            )

        if not active_graph or not active_graph.tables:
            st.info("No active schema parsed yet. Check your schema definition in the sidebar.")
        else:
            st.subheader("📐 Schema & Relational Dependency DAG")

            # Topological Execution Order
            topological_order = active_graph.get_topological_order()
            st.markdown("#### 🔄 Topological Generation Order")
            st.caption("Child tables depend on parent primary keys and are generated downstream:")

            dag_pills = " ➔ ".join([f"`{t}`" for t in topological_order])
            st.markdown(f"**Execution Flow:** {dag_pills}")

            st.divider()

            # Inspect Table Columns & Constraints
            for t_name in topological_order:
                table = active_graph.tables[t_name]
                with st.expander(f"📁 Table: `{t_name}` ({len(table.columns)} columns)", expanded=True):
                    col_data = []
                    for c_name, col in table.columns.items():
                        tags = []
                        if col.is_primary_key:
                            tags.append("PRIMARY KEY")
                        if col.is_foreign_key and col.foreign_key_ref:
                            tags.append(f"FK ➔ {col.foreign_key_ref[0]}.{col.foreign_key_ref[1]}")
                        if col.is_unique and not col.is_primary_key:
                            tags.append("UNIQUE")
                        if not col.nullable:
                            tags.append("NOT NULL")
                        if col.min_value is not None or col.max_value is not None:
                            tags.append(f"RANGE [{col.min_value}..{col.max_value}]")
                        if col.pattern:
                            tags.append(f"REGEX '{col.pattern}'")
                        if col.enum_values:
                            tags.append(f"ENUM {col.enum_values}")

                        col_data.append({
                            "Column Name": c_name,
                            "Normalized Type": col.normalized_type.value,
                            "Raw Type": col.raw_type,
                            "Nullable": col.nullable,
                            "Constraints / Rules": ", ".join(tags) if tags else "—",
                        })

                    st.dataframe(pd.DataFrame(col_data), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
