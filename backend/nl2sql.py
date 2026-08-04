import os
import re
import sqlite3
from dataclasses import dataclass
from openai import OpenAI

from backend.schema import ALLOWED_COLUMNS, TABLE_NAME, schema_prompt_block

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "replace", "truncate"
}

SYSTEM_PROMPT = f"""You translate a business question into a single read-only SQLite SELECT query.

{schema_prompt_block()}

Rules:
- Output ONLY the SQL query. No markdown fences, no explanation, no semicolon-separated extra statements.
- Only use columns listed above. Never invent a column name.
- Only SELECT statements are allowed - never modify data.
- Use the exact table name '{TABLE_NAME}'.
"""


class SQLGuardError(Exception):
    """Raised when generated SQL fails a safety/validity check."""


@dataclass
class QueryResult:
    sql: str
    columns: list
    rows: list
    answer_text: str


def _call_llm_for_sql(question: str) -> str:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,  # we want deterministic SQL, not creative writing
        max_tokens=300,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
    )
    raw_sql = response.choices[0].message.content or ""

    # Models sometimes wrap the query in a ```sql fence even when told not to,
    # so we strip that off before it hits the guardrails.
    cleaned = raw_sql.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("sql\n", "", 1) if cleaned.lower().startswith("sql\n") else cleaned
    return cleaned.strip()


def _extract_identifiers(sql: str) -> set:
    """Very lightweight identifier extraction: pulls bare words that look like
    column references, ignoring SQL keywords, the table name, aliases, and numbers."""
    # Aliases defined via "AS <alias>" are new names WE define (e.g. AS avg_delay) -
    # they're legitimate even though they aren't real columns, so track and allow them.
    defined_aliases = {a.lower() for a in re.findall(r"(?i)\bas\s+([A-Za-z_][A-Za-z0-9_]*)", sql)}

    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", sql)
    sql_keywords = {
        "select", "from", "where", "and", "or", "not", "in", "as", "group", "by",
        "order", "limit", "having", "count", "sum", "avg", "min", "max", "asc",
        "desc", "distinct", "is", "null", "like", "between", "on", "join",
        "left", "right", "inner", "case", "when", "then", "else", "end",
        TABLE_NAME,
    }
    referenced = {w.lower() for w in words if w.lower() not in sql_keywords}
    return referenced - defined_aliases


def validate_sql(sql: str) -> None:
    """Raises SQLGuardError if `sql` violates any safety rule."""
    if not sql or not sql.strip():
        raise SQLGuardError("Empty SQL generated.")

    lowered = sql.strip().lower()

    # must start with select
    if not lowered.startswith("select"):
        raise SQLGuardError("Only SELECT statements are permitted.")

    # forbidden keywords anywhere
    tokens = set(re.findall(r"[a-zA-Z_]+", lowered))
    hit = tokens & FORBIDDEN_KEYWORDS
    if hit:
        raise SQLGuardError(f"Query contains forbidden keyword(s): {', '.join(hit)}")

    # no stacked statements (a second statement after a semicolon)
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise SQLGuardError("Multiple statements are not allowed.")

    # hallucinated column check
    referenced = _extract_identifiers(stripped)
    unknown = referenced - ALLOWED_COLUMNS
    if unknown:
        raise SQLGuardError(f"Unknown column(s) referenced: {', '.join(unknown)}")


def run_query(sql: str, db_path: str) -> tuple:
    """Executes `sql` against a READ-ONLY connection to db_path."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return columns, rows
    finally:
        conn.close()


def format_answer(question: str, columns: list, rows: list) -> str:
    """Turns raw rows into a short human-readable answer."""
    if not rows:
        return "No matching records were found for that question."
    if len(rows) == 1 and len(columns) == 1:
        return f"{columns[0]}: {rows[0][0]}"

    lines = [" | ".join(columns)]
    for row in rows[:10]:
        lines.append(" | ".join(str(v) for v in row))
    suffix = f"\n(showing first 10 of {len(rows)} rows)" if len(rows) > 10 else ""
    return "\n".join(lines) + suffix


def ask(question: str, db_path: str, use_llm: bool = True, forced_sql: str = None) -> QueryResult:
    """
    Full pipeline: question -> SQL -> validate -> execute -> formatted answer.

    `forced_sql` lets tests bypass the LLM call and inject a specific SQL
    string directly into the guardrail + execution path (used by the evals).
    """
    sql = forced_sql if forced_sql is not None else _call_llm_for_sql(question)

    validate_sql(sql)  # raises SQLGuardError on violation

    columns, rows = run_query(sql, db_path)
    answer_text = format_answer(question, columns, rows)

    return QueryResult(sql=sql, columns=columns, rows=rows, answer_text=answer_text)
