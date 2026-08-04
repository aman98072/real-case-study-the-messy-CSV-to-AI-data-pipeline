"""
FastAPI backend.

Run:
    uvicorn backend.main:app --reload --port 8000

Endpoint:
    POST /ask   { "question": "Which route had the highest delay rate last quarter?" }
    -> { "question": ..., "sql": ..., "answer": ..., "rows": [...] }
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.nl2sql import ask, SQLGuardError

DB_PATH = "data/shipments.db"

app = FastAPI(title="Logistics NL Query API")


class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    question: str
    sql: str
    answer: str
    columns: list
    rows: list


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AnswerResponse)
def ask_question(req: QuestionRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        result = ask(req.question, db_path=DB_PATH)
    except SQLGuardError as e:
        # Guardrail tripped -> surface as a client error, never execute the SQL
        raise HTTPException(status_code=400, detail=f"Query rejected by guardrails: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return AnswerResponse(
        question=req.question,
        sql=result.sql,
        answer=result.answer_text,
        columns=result.columns,
        rows=[list(r) for r in result.rows],
    )
