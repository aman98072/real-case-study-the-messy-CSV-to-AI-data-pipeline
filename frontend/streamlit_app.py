"""
Streamlit UI for the logistics NL query system.

Run (with the FastAPI backend already running on :8000):
    streamlit run frontend/streamlit_app.py
"""

import requests
import streamlit as st

API_URL = "http://localhost:8000/ask"

st.set_page_config(page_title="Logistics Q&A", page_icon="🚚")
st.title("🚚 Ask your shipment data")
st.caption("Ask a business question in plain English. The system translates it to SQL, runs it, and answers.")

example_questions = [
    "Which route had the highest delay rate?",
    "How many shipments are still in transit?",
    "What is the average delay in days for the MUM-DEL route?",
    "Which origin city has the most shipments?",
]

question = st.selectbox("Try an example, or type your own below:", [""] + example_questions)
question = st.text_input("Your question", value=question)

if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Translating to SQL and running the query..."):
        try:
            resp = requests.post(API_URL, json={"question": question}, timeout=30)
        except requests.exceptions.ConnectionError:
            st.error("Could not reach the backend. Is `uvicorn backend.main:app` running on port 8000?")
            st.stop()

    if resp.status_code == 200:
        data = resp.json()
        st.success(data["answer"])
        with st.expander("Show generated SQL"):
            st.code(data["sql"], language="sql")
        if data["rows"]:
            st.dataframe(data["rows"], use_container_width=True)
    else:
        st.error(resp.json().get("detail", "Something went wrong."))
