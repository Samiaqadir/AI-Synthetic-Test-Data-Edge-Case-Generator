# QA Validation Report

**Overall Status:** 🔴 FAIL (42 Violations Found)  
**Total Records Inspected:** 60  
**Valid Records:** 18  
**Invalid Records:** 42  
**Pass Rate:** 30.0%  
**Validation Duration:** 0.002s  

## Automated QA Category Verification Badges

| QA Category | Status | Badge | Violations Detected |
| :--- | :---: | :---: | :---: |
| **Data Types** | `FAIL` | 🔴 FAIL (19) | 19 |
| **Regex Formats** | `FAIL` | 🔴 FAIL (3) | 3 |
| **Uniqueness Constraints** | `FAIL` | 🔴 FAIL (3) | 3 |
| **Foreign-Key Integrity** | `FAIL` | 🔴 FAIL (21) | 21 |

## Table-by-Table Breakdown

| Table Name | Records | Valid | Invalid | Pass Rate | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `users` | 10 | 2 | 8 | 20.0% | 🔴 FAIL (8) |
| `categories` | 10 | 5 | 5 | 50.0% | 🔴 FAIL (5) |
| `orders` | 10 | 5 | 5 | 50.0% | 🔴 FAIL (5) |
| `products` | 10 | 2 | 8 | 20.0% | 🔴 FAIL (8) |
| `order_items` | 10 | 3 | 7 | 30.0% | 🔴 FAIL (7) |
| `reviews` | 10 | 1 | 9 | 10.0% | 🔴 FAIL (9) |

## Detected Sample Violations (First 15)

| Table | Row | Column | Category | Rule | Offending Value | Diagnostic Message |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| `users` | 0 | `age` | Bounds & Nullability | `bounds_greater_than_equal` | `-9223372036854775808` | Input should be greater than or equal to 18 |
| `users` | 1 | `full_name` | Data Types | `string_too_long` | `OVERFLOW_XXXXXXXXXXXXXXXXXXXXX` | String should have at most 100 characters |
| `users` | 2 | `email` | Regex Formats | `email_regex_mismatch` | `` | Value '' does not match standard RFC 5322 email regex format |
| `users` | 3 | `is_active` | Data Types | `type_error_bool_parsing` | `` | Input should be a valid boolean, unable to interpret input |
| `users` | 4 | `email` | Regex Formats | `email_regex_mismatch` | `javascript:alert(1)` | Value 'javascript:alert(1)' does not match standard RFC 5322 email regex format |
| `users` | 5 | `age` | Bounds & Nullability | `bounds_greater_than_equal` | `0` | Input should be greater than or equal to 18 |
| `users` | 6 | `username` | Data Types | `string_too_long` | `OVERFLOW_XXXXXXXXXXXXXXXXXXXXX` | String should have at most 50 characters |
| `users` | 6 | `email` | Data Types | `string_too_long` | `OVERFLOW_XXXXXXXXXXXXXXXXXXXXX` | String should have at most 255 characters |
| `users` | 6 | `email` | Regex Formats | `email_regex_mismatch` | `OVERFLOW_XXXXXXXXXXXXXXXXXXXXX` | Value 'OVERFLOW_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX' does not match standard RFC 5322 email regex format |
| `users` | 7 | `age` | Bounds & Nullability | `bounds_greater_than_equal` | `-1` | Input should be greater than or equal to 18 |
| `categories` | 0 | `name` | Data Types | `string_too_long` | `AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` | String should have at most 100 characters |
| `categories` | 3 | `name` | Data Types | `string_too_long` | `OVERFLOW_XXXXXXXXXXXXXXXXXXXXX` | String should have at most 100 characters |
| `categories` | 4 | `slug` | Data Types | `string_too_long` | `OVERFLOW_XXXXXXXXXXXXXXXXXXXXX` | String should have at most 120 characters |
| `categories` | 5 | `name` | Data Types | `string_too_long` | `OVERFLOW_XXXXXXXXXXXXXXXXXXXXX` | String should have at most 100 characters |
| `categories` | 5 | `name` | Uniqueness Constraints | `unique_constraint` | `OVERFLOW_XXXXXXXXXXXXXXXXXXXXX` | Duplicate value 'OVERFLOW_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX' violates unique constraint on column 'name' |