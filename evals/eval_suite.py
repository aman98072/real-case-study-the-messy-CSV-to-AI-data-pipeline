"""
Run:
    python evals/eval_suite.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.nl2sql import ask, SQLGuardError

DB_PATH = "data/shipments.db"


def case_1_valid_query():
    """A normal, well-formed question should succeed and return rows."""
    sql = "SELECT route, AVG(delay_days) as avg_delay FROM shipments GROUP BY route ORDER BY avg_delay DESC LIMIT 1"
    result = ask("Which route had the highest average delay?", DB_PATH, forced_sql=sql)
    assert result.rows, "expected at least one row back"
    return "PASS", result.answer_text


def case_2_blocks_stacked_injection():
    """Classic SQL injection: a second statement stacked after a semicolon."""
    sql = "SELECT * FROM shipments; DROP TABLE shipments;"
    try:
        ask("anything", DB_PATH, forced_sql=sql)
        return "FAIL", "guardrail did not raise, injection would have run"
    except SQLGuardError as e:
        return "PASS", str(e)


def case_3_blocks_dml_keyword():
    """Even a single statement is rejected if it's not a SELECT (e.g. DELETE)."""
    sql = "DELETE FROM shipments WHERE route = 'MUM-DEL'"
    try:
        ask("anything", DB_PATH, forced_sql=sql)
        return "FAIL", "guardrail did not raise, DELETE would have run"
    except SQLGuardError as e:
        return "PASS", str(e)


def case_4_blocks_hallucinated_column():
    """LLM hallucinates a column name that doesn't exist in the schema."""
    sql = "SELECT customer_satisfaction_score FROM shipments"
    try:
        ask("What is the customer satisfaction score?", DB_PATH, forced_sql=sql)
        return "FAIL", "guardrail did not raise, hallucinated column slipped through"
    except SQLGuardError as e:
        return "PASS", str(e)


def case_5_blocks_pragma_probe():
    """Attempt to use PRAGMA to probe/alter DB configuration instead of querying data."""
    sql = "PRAGMA table_info(shipments)"
    try:
        ask("show me the schema", DB_PATH, forced_sql=sql)
        return "FAIL", "guardrail did not raise, PRAGMA probe would have run"
    except SQLGuardError as e:
        return "PASS", str(e)


CASES = [
    ("Valid business question executes normally", case_1_valid_query),
    ("Blocks stacked-statement SQL injection", case_2_blocks_stacked_injection),
    ("Blocks non-SELECT (DELETE) statements", case_3_blocks_dml_keyword),
    ("Blocks hallucinated column names", case_4_blocks_hallucinated_column),
    ("Blocks PRAGMA probing", case_5_blocks_pragma_probe),
]


def main():
    print(f"{'Test':<45} {'Result':<6} Detail")
    print("-" * 100)
    failures = 0
    for name, fn in CASES:
        status, detail = fn()
        if status == "FAIL":
            failures += 1
        print(f"{name:<45} {status:<6} {detail[:60]}")
    print("-" * 100)
    print(f"{len(CASES) - failures}/{len(CASES)} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
