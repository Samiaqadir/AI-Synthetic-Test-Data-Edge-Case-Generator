"""Realistic test data generator utilizing Faker and statistical distributions."""

from __future__ import annotations

import datetime
import random
import uuid
from typing import Any, Dict, List, Optional, Set

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
    """Stores generated primary key values per table to resolve foreign key constraints."""

    def __init__(self) -> None:
        # Map: table_name -> column_name -> list of generated values
        self._pool: Dict[str, Dict[str, List[Any]]] = {}
        # Auto-increment sequences: table_name -> column_name -> current_int
        self._sequences: Dict[str, Dict[str, int]] = {}

    def register_row(self, table_name: str, row: Dict[str, Any], table_schema: TableSchema) -> None:
        """Record generated primary key values for downstream foreign key references."""
        tbl = table_name.lower()
        if tbl not in self._pool:
            self._pool[tbl] = {}

        for pk_col in table_schema.primary_keys:
            if pk_col in row:
                if pk_col not in self._pool[tbl]:
                    self._pool[tbl][pk_col] = []
                self._pool[tbl][pk_col].append(row[pk_col])

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
        for _ in range(count):
            row = self.generate_row(table, context=context)
            records.append(row)
            if context:
                context.register_row(table.name, row, table)
        return records

    def generate_row(
        self,
        table: TableSchema,
        context: Optional[RelationalContext] = None,
    ) -> Dict[str, Any]:
        """Generate a single realistic row for a table schema."""
        row: Dict[str, Any] = {}
        for col_name, col_schema in table.columns.items():
            row[col_name] = self.generate_column_value(col_schema, table.name, context)
        return row

    def generate_column_value(
        self,
        col: ColumnSchema,
        table_name: str = "",
        context: Optional[RelationalContext] = None,
    ) -> Any:
        """Generate a single realistic value matching the column's specifications."""
        # 1. Foreign Key Reference
        if col.is_foreign_key and col.foreign_key_ref and context:
            parent_table, parent_col = col.foreign_key_ref
            fk_val = context.get_foreign_key_value(parent_table, parent_col)
            if fk_val is not None:
                return fk_val

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
            dt = self.faker.date_time_between(start_date="-2y", end_date="now")
            if col.normalized_type == NormalizedType.DATE or name_lower.endswith("_date"):
                return dt.date().isoformat()
            return dt.isoformat()

        # Numeric: Price / Amount / Balance (Log-normal skewed)
        if any(k in name_lower for k in ("price", "amount", "total", "balance", "cost", "salary")):
            val = sample_lognormal(mean=3.5, sigma=0.8, min_val=col.min_value or 1.0, max_val=col.max_value or 50000.0)
            if col.is_integer:
                return int(round(val))
            return round(val, col.scale or 2)

        # Numeric: Age / Count / Quantity
        if "age" in name_lower:
            return int(sample_normal(mean=35, std_dev=12, min_val=col.min_value or 18, max_val=col.max_value or 95))
        if any(k in name_lower for k in ("quantity", "qty", "count", "items")):
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
