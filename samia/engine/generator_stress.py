"""Adversarial stress generator and edge-case mutator injection engine."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Sequence

from samia.engine.generator_happy import HappyPathGenerator, RelationalContext
from samia.models.schema import ColumnSchema, NormalizedType, TableSchema


# --- Catalogues of Edge-Case and Adversarial Values ---

INT_BOUNDARY_VALUES: List[int] = [
    0,
    1,
    -1,
    2147483647,               # INT32_MAX
    -2147483648,              # INT32_MIN
    9223372036854775807,      # INT64_MAX
    -9223372036854775808,     # INT64_MIN
    4294967295,               # UINT32_MAX
]

FLOAT_BOUNDARY_VALUES: List[Any] = [
    0.0,
    -0.0,
    1e-323,                   # Subnormal float min
    1.7976931348623157e+308,  # Float max
    -1.7976931348623157e+308,
    float("inf"),
    float("-inf"),
    float("nan"),
    99999999999.9999,         # Precision overflow
]

SQLI_PAYLOADS: List[str] = [
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "admin' --",
    "1' UNION SELECT NULL, username, password FROM users --",
    "1; EXEC xp_cmdshell('dir')",
    "' OR 1=1#",
    "' UNION ALL SELECT 1, 'admin', 'pass'--",
    "\" OR \"\"=\"",
    "1' AND SLEEP(5)--",
    "{\"$gt\": \"\"}",          # NoSQL injection
]

XSS_PAYLOADS: List[str] = [
    "<script>alert('xss')</script>",
    "<img src=x onerror=alert(1)>",
    "\"><script>alert(document.cookie)</script>",
    "<svg/onload=alert('XSS')>",
    "javascript:alert(1)",
    "{{7*7}}",                 # Template Injection (SSTI)
    "${7*7}",                  # Expression Language Injection
    "<iframe src=\"javascript:alert(1)\"></iframe>",
    "<details open ontoggle=alert(1)>",
]

UNICODE_EMOJI_PAYLOADS: List[str] = [
    "👨‍👩‍👧‍👦",                   # Complex ZWJ sequence emoji
    "👩🏽‍💻",                   # Skin-tone modifier emoji
    "🏴󠁧󠁢󠁳󠁣󠁴󠁿",                  # Sub-flag tag sequence
    "H̶e̶l̶l̶o̶ ̶Z̶a̶l̶g̶o̶",           # Zalgo text (combining diacritics)
    "𝓤𝓷𝓲𝓬𝓸𝓭𝓮 𝒯𝑒𝓈𝓉",           # High plane mathematical alphanumeric
    "日本語・한국어・العربية",      # Multilingual CJK & RTL
    "\u202Ereversed_text",     # Right-To-Left Override (Trojan Source)
    "\u200B\u200C\u200Dhidden",# Zero-width spaces & joiners
    "test\x00user",            # Null byte injection
    "",                        # Empty string
    "   ",                     # Whitespace only
    "\t\r\n",                  # Control characters
    "A" * 4096,                # Extreme length string
]

DATE_EDGE_CASES: List[str] = [
    "1970-01-01T00:00:00Z",    # Unix Epoch
    "1969-12-31T23:59:59Z",    # Negative Unix Epoch
    "2038-01-19T03:14:07Z",    # Year 2038 32-bit rollover
    "2000-02-29T12:00:00Z",    # Leap Year (century leap)
    "2024-02-29T23:59:59Z",    # Modern Leap Year
    "1900-02-28T12:00:00Z",    # Century non-leap boundary
    "9999-12-31T23:59:59Z",    # Maximum ISO timestamp
    "0001-01-01T00:00:00Z",    # Minimum ISO timestamp
    "2024-03-10T02:30:00Z",    # US DST transition gap
]


class StressGenerator:
    """
    Adversarial edge-case test data generator and mutator.
    Injects boundary numbers, SQLi/XSS payloads, Unicode/emojis,
    and temporal anomalies into record streams.
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        happy_generator: Optional[HappyPathGenerator] = None,
    ) -> None:
        self.happy = happy_generator or HappyPathGenerator(seed=seed)
        if seed is not None:
            random.seed(seed)

    def generate_adversarial_value(self, col: ColumnSchema) -> Any:
        """Generate a single adversarial / edge-case value suited for the column type."""
        # Boundaries based on column configuration
        if col.is_integer:
            candidates: List[Any] = list(INT_BOUNDARY_VALUES)
            if col.min_value is not None:
                candidates.extend([int(col.min_value), int(col.min_value) - 1, int(col.min_value) + 1])
            if col.max_value is not None:
                candidates.extend([int(col.max_value), int(col.max_value) + 1, int(col.max_value) - 1])
            return random.choice(candidates)

        if col.normalized_type in (NormalizedType.FLOAT, NormalizedType.DECIMAL):
            candidates = list(FLOAT_BOUNDARY_VALUES)
            if col.min_value is not None:
                candidates.extend([col.min_value, col.min_value - 0.001])
            if col.max_value is not None:
                candidates.extend([col.max_value, col.max_value + 0.001])
            return random.choice(candidates)

        if col.is_datetime:
            return random.choice(DATE_EDGE_CASES)

        if col.normalized_type == NormalizedType.BOOLEAN:
            # Mutate with non-standard boolean representations
            return random.choice([None, "", "null", 0, 1, "TRUE", "FALSE"])

        # String / Text / Varchar columns: inject SQLi, XSS, or Unicode
        payload_category = random.choice(["sqli", "xss", "unicode", "length"])
        if payload_category == "sqli":
            val = random.choice(SQLI_PAYLOADS)
        elif payload_category == "xss":
            val = random.choice(XSS_PAYLOADS)
        elif payload_category == "unicode":
            val = random.choice(UNICODE_EMOJI_PAYLOADS)
        else:
            # Exceed max_length boundary if defined
            target_len = (col.max_length + 50) if col.max_length else 5000
            val = "OVERFLOW_" + ("X" * target_len)

        return val

    def mutate_row(
        self,
        row: Dict[str, Any],
        table: TableSchema,
        mutation_rate: float = 0.3,
        corrupt_foreign_keys: bool = False,
    ) -> Dict[str, Any]:
        """
        Takes a valid row and mutates a fraction of its fields with adversarial values.
        By default, preserves foreign key integrity so downstream relations don't orphan.
        """
        mutated = dict(row)
        for col_name, col in table.columns.items():
            # Skip primary keys to prevent unintentional PK duplicate collisions
            if col.is_primary_key:
                continue

            # Respect foreign keys unless specifically testing orphan/broken FKs
            if col.is_foreign_key and not corrupt_foreign_keys:
                continue

            if random.random() < mutation_rate:
                mutated[col_name] = self.generate_adversarial_value(col)

        return mutated

    def generate_targeted_15_rows(
        self,
        table: TableSchema,
        context: Optional[RelationalContext] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate exactly 15 targeted adversarial edge-case rows testing specific
        vulnerability vectors, boundary violations, and malformed inputs while
        preserving foreign key referential integrity with parent tables.
        """
        # Define the 15 targeted edge-case specifications
        specs = [
            # 1. Null in non-nullable field
            {
                "id": 1,
                "name": "NULL_IN_REQUIRED",
                "category": "Nullability Constraint",
                "target_type": "non_nullable",
                "generator": lambda col: None,
            },
            # 2. 32-bit signed integer overflow
            {
                "id": 2,
                "name": "INT32_MAX_OVERFLOW",
                "category": "Numeric Boundary Overflow",
                "target_type": "integer",
                "generator": lambda col: 2147483648,
            },
            # 3. Negative value violating domain / CHECK constraint
            {
                "id": 3,
                "name": "INT_NEGATIVE_VIOLATION",
                "category": "Negative Domain Violation",
                "target_type": "integer",
                "generator": lambda col: -999,
            },
            # 4. Malformed email (missing domain)
            {
                "id": 4,
                "name": "MALFORMED_EMAIL_NO_DOMAIN",
                "category": "RFC 5322 Syntax Error",
                "target_type": "email_or_string",
                "generator": lambda col: "malformed.user@broken",
            },
            # 5. Malformed email with control characters / multiple @
            {
                "id": 5,
                "name": "MALFORMED_EMAIL_INJECTION",
                "category": "Header / Email Injection",
                "target_type": "email_or_string",
                "generator": lambda col: "admin<script>@evil.com\x00",
            },
            # 6. SQLi WHERE tautology
            {
                "id": 6,
                "name": "SQLI_TAUTOLOGY_BYPASS",
                "category": "SQL Injection",
                "target_type": "string",
                "generator": lambda col: "' OR '1'='1",
            },
            # 7. SQLi Stacked query DDL drop
            {
                "id": 7,
                "name": "SQLI_STACKED_DROP_TABLE",
                "category": "SQL Injection",
                "target_type": "string",
                "generator": lambda col: "'; DROP TABLE test_data; --",
            },
            # 8. SQLi UNION data exfiltration
            {
                "id": 8,
                "name": "SQLI_UNION_EXFILTRATION",
                "category": "SQL Injection",
                "target_type": "string",
                "generator": lambda col: "1' UNION SELECT NULL, username, password FROM users --",
            },
            # 9. Stored XSS script payload
            {
                "id": 9,
                "name": "XSS_STORED_SCRIPT",
                "category": "Cross-Site Scripting (XSS)",
                "target_type": "string",
                "generator": lambda col: "<script>alert('samia_xss')</script>",
            },
            # 10. XSS HTML event handler exploit
            {
                "id": 10,
                "name": "XSS_IMG_EVENT_HANDLER",
                "category": "Cross-Site Scripting (XSS)",
                "target_type": "string",
                "generator": lambda col: "<img src=x onerror=alert(document.cookie)>",
            },
            # 11. XSS Polyglot SVG
            {
                "id": 11,
                "name": "XSS_POLYGLOT_SVG",
                "category": "Cross-Site Scripting (XSS)",
                "target_type": "string",
                "generator": lambda col: "\"><svg/onload=alert('XSS_POLYGLOT')>",
            },
            # 12. Complex ZWJ Unicode Emojis
            {
                "id": 12,
                "name": "UNICODE_ZWJ_EMOJIS",
                "category": "Unicode & UTF-8mb4 Stress",
                "target_type": "string",
                "generator": lambda col: "👨‍👩‍👧‍👦🔥🚀💯✨",
            },
            # 13. Zalgo combining text diacritics
            {
                "id": 13,
                "name": "UNICODE_ZALGO_DIACRITICS",
                "category": "Unicode Corruption Stress",
                "target_type": "string",
                "generator": lambda col: "H̶e̶l̶l̶o̶ ̶Z̶a̶l̶g̶o̶ ̶S̶t̶r̶e̶s̶s̶",
            },
            # 14. Trojan Source BiDi RTL override
            {
                "id": 14,
                "name": "UNICODE_BIDI_RTL_OVERRIDE",
                "category": "Trojan Source / RTL Override",
                "target_type": "string",
                "generator": lambda col: "\u202Ereversed_admin_payload\u202D",
            },
            # 15. Year 2038 / Leap Year temporal edge-case
            {
                "id": 15,
                "name": "DATE_Y2038_OR_LEAP_YEAR",
                "category": "Temporal Boundary",
                "target_type": "datetime",
                "generator": lambda col: "2038-01-19T03:14:07Z",
            },
        ]

        records: List[Dict[str, Any]] = []

        for spec in specs:
            # Start with a valid baseline row to guarantee structure & FK validity
            base_row = self.happy.generate_row(table, context=context)

            # Determine the best candidate column for this spec
            target_col_name = None
            target_col_schema = None

            t_type = spec["target_type"]
            for col_name, col in table.columns.items():
                if col.is_primary_key or col.is_foreign_key:
                    continue

                if t_type == "non_nullable" and not col.nullable:
                    target_col_name = col_name
                    target_col_schema = col
                    break
                elif t_type == "integer" and col.is_integer:
                    target_col_name = col_name
                    target_col_schema = col
                    break
                elif t_type == "email_or_string" and ("email" in col.name.lower() or col.is_string):
                    target_col_name = col_name
                    target_col_schema = col
                    break
                elif t_type == "string" and col.is_string:
                    target_col_name = col_name
                    target_col_schema = col
                    break
                elif t_type == "datetime" and (col.is_datetime or "date" in col.name.lower() or "created" in col.name.lower()):
                    target_col_name = col_name
                    target_col_schema = col
                    break

            # Fallback if specific type column not found
            if not target_col_name:
                non_pks = [c for c, s in table.columns.items() if not s.is_primary_key and not s.is_foreign_key]
                target_col_name = non_pks[0] if non_pks else list(table.columns.keys())[-1]
                target_col_schema = table.columns[target_col_name]

            # Inject the adversarial value
            injected_val = spec["generator"](target_col_schema)
            base_row[target_col_name] = injected_val

            records.append(base_row)

            # Register in context if it contains a valid PK
            if context:
                context.register_row(table.name, base_row, table)

        return records

    def generate_table_records(
        self,
        table: TableSchema,
        count: int,
        context: Optional[RelationalContext] = None,
        mutation_rate: float = 0.5,
        corrupt_foreign_keys: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple rows of stress-tested data.
        Starts from valid baseline rows and applies adversarial mutator injection.
        """
        records: List[Dict[str, Any]] = []
        for _ in range(count):
            base_row = self.happy.generate_row(table, context=context)
            mutated_row = self.mutate_row(
                base_row,
                table,
                mutation_rate=mutation_rate,
                corrupt_foreign_keys=corrupt_foreign_keys,
            )
            records.append(mutated_row)
            if context:
                context.register_row(table.name, mutated_row, table)
        return records
