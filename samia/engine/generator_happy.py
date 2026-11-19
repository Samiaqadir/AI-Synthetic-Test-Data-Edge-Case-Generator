"""Realistic test data generator utilizing Faker and statistical distributions."""

from __future__ import annotations

import datetime
import random
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from faker import Faker

from samia.engine.distributions import (
    sample_categorical,
    sample_exponential,
    sample_lognormal,
    sample_normal,
    sample_uniform,
)
from samia.models.schema import ColumnSchema, NormalizedType, TableSchema


class RelationalContext:
    """Stores generated primary key values and complete rows per table to resolve foreign key constraints."""

    def __init__(self) -> None:
        # Map: table_name -> column_name -> list of generated values
        self._pool: Dict[str, Dict[str, List[Any]]] = {}
        # Auto-increment sequences: table_name -> column_name -> current_int
        self._sequences: Dict[str, Dict[str, int]] = {}
        # Map: table_name -> list of row dicts
        self._rows: Dict[str, List[Dict[str, Any]]] = {}

    def register_row(self, table_name: str, row: Dict[str, Any], table_schema: Optional[TableSchema] = None) -> None:
        """Record generated primary key values and rows for downstream foreign key references."""
        tbl = table_name.lower()
        if tbl not in self._pool:
            self._pool[tbl] = {}
        if tbl not in self._rows:
            self._rows[tbl] = []

        self._rows[tbl].append(dict(row))

        if table_schema:
            for pk_col in table_schema.primary_keys:
                if pk_col in row and row[pk_col] is not None:
                    if pk_col not in self._pool[tbl]:
                        self._pool[tbl][pk_col] = []
                    self._pool[tbl][pk_col].append(row[pk_col])
        else:
            if "id" in row and row["id"] is not None:
                if "id" not in self._pool[tbl]:
                    self._pool[tbl]["id"] = []
                self._pool[tbl]["id"].append(row["id"])

    def get_parent_rows(self, target_table: str) -> List[Dict[str, Any]]:
        """Fetch all generated rows for target table."""
        tbl = target_table.lower()
        for t, rows in self._rows.items():
            if t.lower() == tbl:
                return rows
        return []

    def get_foreign_key_value(self, target_table: str, target_column: str) -> Optional[Any]:
        """Fetch an existing parent primary key value to satisfy foreign key constraint."""
        tbl = target_table.lower()
        col = target_column.lower()

        # Lookup case-insensitively
        table_matches = [t for t in self._pool if t.lower() == tbl]
        if not table_matches:
            return None

        tbl_key = table_matches[0]
        col_matches = [c for c in self._pool[tbl_key] if c.lower() == col]
        if not col_matches:
            return None

        candidates = self._pool[tbl_key][col_matches[0]]
        if not candidates:
            return None
        return random.choice(candidates)

    def get_foreign_key_tuple(self, target_table: str, target_columns: List[str]) -> Optional[Dict[str, Any]]:
        """Fetch values for a tuple of target columns from the same parent row."""
        rows = self.get_parent_rows(target_table)
        if not rows:
            return None
        parent_row = random.choice(rows)
        # Check that parent_row has all target columns
        if all(c in parent_row for c in target_columns):
            return {c: parent_row[c] for c in target_columns}
        # Case-insensitive column match fallback
        res = {}
        for tc in target_columns:
            matched_key = next((k for k in parent_row if k.lower() == tc.lower()), None)
            if matched_key is None:
                return None
            res[tc] = parent_row[matched_key]
        return res

    def next_sequence_value(self, table_name: str, column_name: str, start: int = 1) -> int:
        """Generate next sequence integer for auto-increment primary keys."""
        tbl = table_name.lower()
        if tbl not in self._sequences:
            self._sequences[tbl] = {}
        curr = self._sequences[tbl].get(column_name, start)
        self._sequences[tbl][column_name] = curr + 1
        return curr


class HappyPathGenerator:
    """Generates realistic synthetic data satisfying schema types, boundaries, and semantics."""

    def __init__(self, seed: Optional[int] = None, locale: str = "en_US") -> None:
        self.faker = Faker(locale)
        if seed is not None:
            self.seed(seed)

    def seed(self, seed: int) -> None:
        """Seed random number generators for deterministic reproducibility."""
        random.seed(seed)
        Faker.seed(seed)

    def generate_table_records(
        self,
        table: TableSchema,
        count: int,
        context: Optional[RelationalContext] = None,
    ) -> List[Dict[str, Any]]:
        """Generate multiple rows of realistic data for a table schema."""
        records: List[Dict[str, Any]] = []
        seen_uniques: Dict[str, Set[Any]] = defaultdict(set)
        seen_composite_pks: Set[Tuple[Any, ...]] = set()

        for row_idx in range(count):
            row = self.generate_row(
                table,
                context=context,
                seen_uniques=seen_uniques,
                seen_composite_pks=seen_composite_pks,
                row_idx=row_idx,
            )
            records.append(row)
            if context:
                context.register_row(table.name, row, table)
        return records

    def generate_row(
        self,
        table: TableSchema,
        context: Optional[RelationalContext] = None,
        seen_uniques: Optional[Dict[str, Set[Any]]] = None,
        seen_composite_pks: Optional[Set[Tuple[Any, ...]]] = None,
        row_idx: int = 0,
    ) -> Dict[str, Any]:
        """Generate a single realistic row for a table schema."""
        row: Dict[str, Any] = {}

        # 1. Resolve composite foreign key constraints first (drawn from the same parent row)
        if context and getattr(table, "foreign_key_constraints", None):
            for fk_c in table.foreign_key_constraints:
                if len(fk_c.child_columns) > 1:
                    if fk_c.parent_table.lower() == table.name.lower():
                        # Self-referencing composite FK
                        parent_rows = context.get_parent_rows(table.name)
                        if parent_rows:
                            p_row = random.choice(parent_rows)
                            for cc, pc in zip(fk_c.child_columns, fk_c.parent_columns):
                                row[cc] = p_row.get(pc)
                        else:
                            for cc in fk_c.child_columns:
                                row[cc] = None if table.columns[cc].nullable else 1
                    else:
                        tuple_val = context.get_foreign_key_tuple(fk_c.parent_table, fk_c.parent_columns)
                        if tuple_val:
                            for cc, pc in zip(fk_c.child_columns, fk_c.parent_columns):
                                row[cc] = tuple_val.get(pc)

        # 2. Generate remaining column values
        is_single_pk = len(table.primary_keys) == 1
        for col_name, col_schema in table.columns.items():
            if col_name in row:
                continue

            val = self.generate_column_value(col_schema, table.name, context, row_idx=row_idx)

            # Enforce max_length bound for generated string values
            if isinstance(val, str) and col_schema.max_length is not None and len(val) > col_schema.max_length:
                val = val[: col_schema.max_length]

            # Ensure uniqueness for unique / single primary key columns at scale
            is_col_unique = col_schema.is_unique or (col_schema.is_primary_key and is_single_pk)
            if seen_uniques is not None and is_col_unique and val is not None:
                if val in seen_uniques[col_name]:
                    if col_schema.is_integer:
                        val = (max(seen_uniques[col_name]) + 1) if seen_uniques[col_name] else (row_idx + 1)
                    elif col_schema.normalized_type == NormalizedType.EMAIL or "email" in col_name.lower():
                        parts = str(val).split("@")
                        val = f"{parts[0]}_{row_idx+1}@{parts[1] if len(parts) > 1 else 'example.com'}"
                    elif col_schema.normalized_type == NormalizedType.UUID:
                        val = str(uuid.uuid4())
                    else:
                        suffix = f"_{row_idx+1}"
                        max_len = col_schema.max_length or 100
                        s_val = str(val)
                        if len(s_val) + len(suffix) > max_len:
                            s_val = s_val[: max(1, max_len - len(suffix))]
                        val = f"{s_val}{suffix}"

                seen_uniques[col_name].add(val)

            row[col_name] = val

        # 3. Ensure composite primary key uniqueness
        if len(table.primary_keys) > 1 and seen_composite_pks is not None:
            pk_tuple = tuple(row.get(k) for k in table.primary_keys)
            if pk_tuple in seen_composite_pks:
                # Find a non-FK primary key column to increment, or the last primary key column
                target_pk_col = next(
                    (k for k in reversed(table.primary_keys) if not table.columns[k].is_foreign_key),
                    table.primary_keys[-1],
                )
                curr_v = row.get(target_pk_col, 0)
                if isinstance(curr_v, int):
                    while pk_tuple in seen_composite_pks:
                        curr_v += 1
                        row[target_pk_col] = curr_v
                        pk_tuple = tuple(row.get(k) for k in table.primary_keys)
            seen_composite_pks.add(pk_tuple)

        return row

    def generate_column_value(
        self,
        col: ColumnSchema,
        table_name: str = "",
        context: Optional[RelationalContext] = None,
        row_idx: int = 0,
    ) -> Any:
        """Generate a single realistic value matching the column's specifications."""
        # 1. Foreign Key Reference
        if col.is_foreign_key and col.foreign_key_ref and context:
            parent_table, parent_col = col.foreign_key_ref
            is_self_ref = parent_table.lower() == table_name.lower()
            if is_self_ref:
                existing_ids = context._pool.get(table_name.lower(), {}).get(parent_col.lower(), [])
                if not existing_ids:
                    if col.nullable:
                        return None
                    return 1
                else:
                    if col.nullable and random.random() < 0.20:
                        return None
                    return random.choice(existing_ids)
            else:
                fk_val = context.get_foreign_key_value(parent_table, parent_col)
                if fk_val is not None:
                    return fk_val
                if col.nullable:
                    return None

        # 2. Primary Key Handling
        if col.is_primary_key:
            if col.is_integer:
                if context:
                    return context.next_sequence_value(table_name, col.name)
                return random.randint(1, 1_000_000)
            if col.normalized_type == NormalizedType.UUID:
                return str(uuid.uuid4())
            if col.is_string:
                return f"{col.name}_{uuid.uuid4().hex[:8]}"

        # 3. Enum Values
        if col.enum_values:
            return random.choice(col.enum_values)

        # 4. Semantic field heuristics by column name
        name_lower = col.name.lower()

        # Email (plausible corporate/personal domains)
        if "email" in name_lower or col.normalized_type == NormalizedType.EMAIL:
            domain = random.choice(["example.com", "apex-cloud.io", "techpulse.net", "lumina-retail.com"])
            return f"{self.faker.user_name()}@{domain}"

        # SKUs (plausible retail/warehouse format)
        if "sku" in name_lower:
            prefix = self.faker.lexify("???").upper()
            return f"SKU-{prefix}-{random.randint(1000, 9999)}"

        # Order Numbers / Transaction IDs
        if "order_number" in name_lower or "order_no" in name_lower:
            return f"ORD-2026-{random.randint(100000, 999999)}"

        # Product Names / Items
        if any(k in name_lower for k in ("product_name", "product_title", "item_name")):
            adjectives = ["Wireless", "Ergonomic", "Smart", "Ultra HD", "Compact", "Pro Series", "Eco-friendly", "Premium"]
            nouns = ["Headphones", "Office Chair", "Mechanical Keyboard", "Monitor", "Power Bank", "Backpack", "Smartwatch", "Desk Lamp"]
            return f"{random.choice(adjectives)} {random.choice(nouns)}"

        # Names
        if name_lower in ("first_name", "firstname", "fname"):
            return self.faker.first_name()
        if name_lower in ("last_name", "lastname", "lname"):
            return self.faker.last_name()
        if any(k in name_lower for k in ("full_name", "customer_name", "user_name", "username")):
            return self.faker.user_name()
        if name_lower in ("name", "author", "creator"):
            return self.faker.name()

        # Phone numbers
        if any(k in name_lower for k in ("phone", "mobile", "tel")):
            return self.faker.phone_number()

        # Addresses
        if "street" in name_lower or name_lower == "address":
            return self.faker.street_address()
        if "city" in name_lower:
            return self.faker.city()
        if "state" in name_lower:
            return self.faker.state()
        if "country" in name_lower:
            return self.faker.country()
        if any(k in name_lower for k in ("postal_code", "zip", "zipcode")):
            return self.faker.postcode()

        # URLs & IPs
        if any(k in name_lower for k in ("url", "website", "link")):
            return self.faker.url()
        if "ipv4" in name_lower or "ip_address" in name_lower:
            return self.faker.ipv4()

        # Company / Job
        if "company" in name_lower or "organization" in name_lower:
            return self.faker.company()
        if "job" in name_lower or "role" in name_lower or "title" in name_lower:
            return self.faker.job()

        # UUID
        if col.normalized_type == NormalizedType.UUID or "uuid" in name_lower or "guid" in name_lower:
            return str(uuid.uuid4())

        # Dates and Timestamps
        if col.is_datetime or any(k in name_lower for k in ("created_at", "updated_at", "timestamp", "datetime", "date")):
            if col.nullable and not col.is_primary_key:
                if any(k in name_lower for k in ("deleted_at", "archived_at", "cancelled_at")):
                    if random.random() < 0.85:
                        return None
                elif any(k in name_lower for k in ("completed_at", "resolved_at", "shipped_at", "end_date")):
                    if random.random() < 0.35:
                        return None
                elif random.random() < 0.15:
                    return None

            dt = self.faker.date_time_between(start_date="-2y", end_date="now")
            if col.normalized_type == NormalizedType.DATE or name_lower.endswith("_date"):
                return dt.date().isoformat()
            return dt.isoformat()

        # Account Numbers / Identifiers
        if any(k in name_lower for k in ("account_number", "account_no", "acct_no", "acct_num")):
            return f"ACCT-{random.randint(10000000, 99999999)}"

        # Numeric: Price / Amount / Balance (Log-normal skewed) - Only if column is numeric
        if col.is_numeric and any(k in name_lower for k in ("price", "amount", "total", "balance", "cost", "salary")):
            val = sample_lognormal(mean=3.5, sigma=0.8, min_val=col.min_value or 1.0, max_val=col.max_value or 50000.0)
            if col.is_integer:
                return int(round(val))
            return round(val, col.scale or 2)

        # Numeric: Age / Count / Quantity - Only if column is numeric
        if col.is_numeric:
            if "age" in name_lower:
                return int(sample_normal(mean=35, std_dev=12, min_val=col.min_value or 18, max_val=col.max_value or 95))
            if any(k in name_lower for k in ("quantity", "qty", "count", "items")) and not any(k in name_lower for k in ("account", "discount")):
                return int(sample_uniform(low=col.min_value or 1, high=col.max_value or 20))
            if any(k in name_lower for k in ("rating", "score")):
                val = sample_uniform(low=col.min_value or 1.0, high=col.max_value or 5.0)
                if col.is_integer:
                    return int(round(val))
                return round(val, 1)

        # 5. Type-driven fallbacks
        if col.is_integer:
            low = int(col.min_value) if col.min_value is not None else 1
            high = int(col.max_value) if col.max_value is not None else 1000
            if high < low:
                high = low + 10
            return random.randint(low, high)

        if col.normalized_type in (NormalizedType.FLOAT, NormalizedType.DECIMAL):
            low = col.min_value if col.min_value is not None else 0.0
            high = col.max_value if col.max_value is not None else 1000.0
            if high < low:
                high = low + 10.0
            scale = col.scale if col.scale is not None else 2
            return round(random.uniform(low, high), scale)

        if col.normalized_type == NormalizedType.BOOLEAN or name_lower.startswith(("is_", "has_", "can_")):
            return sample_categorical([True, False], weights=[0.8, 0.2])

        if col.normalized_type == NormalizedType.TEXT:
            return self.faker.paragraph(nb_sentences=3)

        if col.normalized_type == NormalizedType.JSON:
            return {
                "source": "samia_synthetic",
                "tag": self.faker.word(),
                "active": True,
                "score": random.randint(1, 100),
            }

        if col.normalized_type == NormalizedType.ARRAY:
            return [self.faker.word() for _ in range(random.randint(1, 4))]

        # Generic String
        length = col.max_length or 30
        if length <= 10:
            val = self.faker.lexify(text="?" * length)
        else:
            val = self.faker.sentence(nb_words=4).rstrip(".")
            if len(val) > length:
                val = val[:length]
        return val
