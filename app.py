"""Streamlit dashboard for the Extraction Agent POC.

Run with:
    streamlit run app.py
"""

import inspect
import json
import logging
import sys
from pathlib import Path
from typing import Type

import streamlit as st
from pydantic import BaseModel

import models as _models_module
from chat_loader import list_chat_files, load_chat_file
from db import get_by_id, get_history, init_db
from extractor import ExtractionEngine
from utils import BEDROCK_ANTHROPIC_MODELS

# Logging setup
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

# Schema discovery — find all concrete Pydantic models in models.py

def _discover_schemas() -> dict[str, Type[BaseModel]]:
    schemas: dict[str, Type[BaseModel]] = {}
    for name, obj in inspect.getmembers(_models_module, inspect.isclass):
        if issubclass(obj, BaseModel) and obj is not BaseModel:
            schemas[name] = obj
    return schemas


# Page config

st.set_page_config(
    page_title="Extraction Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Extraction Agent")
st.caption("Structured data extraction via AWS Bedrock · Claude · instructor · Pydantic")

init_db()

# Sidebar — configuration

with st.sidebar:
    st.header("Configuration")

    schemas = _discover_schemas()
    schema_names = list(schemas.keys())

    if not schema_names:
        st.error("No Pydantic schemas found in models.py")
        st.stop()

    selected_schema_name = st.selectbox("Target Schema", schema_names)
    selected_schema = schemas[selected_schema_name]

    model_options = list(BEDROCK_ANTHROPIC_MODELS.keys())
    selected_model = st.selectbox("Bedrock Model", model_options, index=0)

    st.divider()
    st.subheader("Schema Preview")
    st.json(selected_schema.model_json_schema(), expanded=False)


# Helper: render extraction result into a column

def _render_result(result, container, reference_json: dict | None = None) -> None:
    """Render an ExtractionResult into `container`."""
    with container:
        if result.status == "success":
            st.success(f"Extraction succeeded in {result.attempts} attempt(s)")
            try:
                extracted = json.loads(result.output_json)
            except Exception:
                st.code(result.output_json, language="json")
                return

            if reference_json:
                tab_extracted, tab_diff = st.tabs(["Extracted", "vs. Reference"])
                with tab_extracted:
                    st.json(extracted)
                with tab_diff:
                    st.caption("Reference (field_data from file)")
                    st.json(reference_json)
            else:
                st.json(extracted)
        else:
            st.error(f"Extraction failed after {result.attempts} attempt(s)")
            st.code(result.error or "Unknown error", language="text")


# Main input area — two tabs

tab_paste, tab_file = st.tabs(["Paste Text", "Load Chat File"])

input_text: str = ""
reference_json: dict | None = None
run_btn = False

# ── Tab 1: paste raw text ──────────────────────────────────────────────────
with tab_paste:
    col_input, col_output = st.columns([1, 1], gap="large")

    with col_input:
        st.subheader("Input Text")
        paste_text = st.text_area(
            label="Paste unstructured text here",
            height=350,
            placeholder="e.g. chat messages, emails, documents…",
            label_visibility="collapsed",
            key="paste_input",
        )
        paste_run = st.button("⚡ Extract", type="primary", use_container_width=True, key="paste_run")

    with col_output:
        st.subheader("Extracted Output")
        paste_output = st.container()

    if paste_run:
        if not paste_text.strip():
            st.warning("Please enter some text before extracting.")
        else:
            with st.spinner("Running extraction pipeline…"):
                engine = ExtractionEngine(model_key=selected_model)
                result = engine.run(paste_text, selected_schema)
            _render_result(result, paste_output)


# ── Tab 2: load from chat files ────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _peek_created_at(path_str: str) -> str:
    """Return the created_at string from a chat JSON file without full parsing."""
    import json as _json
    try:
        with open(path_str, encoding="utf-8") as fh:
            data = _json.load(fh)
        return data.get("created_at", "") or ""
    except Exception:
        return ""


with tab_file:
    chat_files = list_chat_files()
    all_files: dict[str, Path] = {}
    for folder, paths in chat_files.items():
        for p in paths:
            date_str = _peek_created_at(str(p))
            date_suffix = f"  ·  {date_str}" if date_str else ""
            all_files[f"[{folder}] {p.name}{date_suffix}"] = p

    if not all_files:
        st.info("No chat files found in raw_data/chats/ or raw_data/downloaded_chats/")
    else:
        col_file, col_chat_output = st.columns([1, 1], gap="large")

        with col_file:
            st.subheader("Select Chat File")
            selected_label = st.selectbox(
                "Chat file",
                list(all_files.keys()),
                label_visibility="collapsed",
            )
            selected_path = all_files[selected_label]

            # Load and preview the chat
            chat_data = load_chat_file(selected_path)

            # Metadata pills
            meta = chat_data["meta"]
            if meta.get("chat_name"):
                st.caption(f"Chat: **{meta['chat_name']}**")
            if meta.get("created_at"):
                st.caption(f"Date: {meta['created_at']}")
            if meta.get("customer_id"):
                st.caption(f"Customer: `{meta['customer_id']}`")

            st.subheader("Chat Preview")
            chat_text = chat_data["text"]
            st.text_area(
                "chat_preview",
                value=chat_text,
                height=300,
                disabled=True,
                label_visibility="collapsed",
            )

            # Show reference field_data if available
            if chat_data["field_data"]:
                with st.expander("Reference extraction (field_data)", expanded=False):
                    st.json(chat_data["field_data"])

            file_run = st.button(
                "Extract from this chat",
                type="primary",
                use_container_width=True,
                key="file_run",
            )

        with col_chat_output:
            st.subheader("Extracted Output")
            file_output = st.container()

        if file_run:
            if not chat_text.strip():
                st.warning("Selected chat file produced no text — cannot extract.")
            else:
                with st.spinner(f"Extracting from {selected_path.name}…"):
                    engine = ExtractionEngine(model_key=selected_model)
                    result = engine.run(chat_text, selected_schema)
                _render_result(result, file_output, reference_json=chat_data["field_data"])


# History table

st.divider()
st.subheader("Extraction History")

col_refresh, col_limit, _ = st.columns([1, 1, 4])
with col_refresh:
    st.button("🔄 Refresh", use_container_width=True, key="refresh_history")
with col_limit:
    history_limit = st.number_input("Rows", min_value=5, max_value=200, value=20, step=5)

rows = get_history(limit=int(history_limit))

if not rows:
    st.info("No extractions yet. Run one above!")
else:
    display_rows = [
        {
            "ID": r["id"],
            "Schema": r["schema_name"],
            "Status": r["status"],
            "Attempts": r["attempts"],
            "Created": r["created_at"],
            "Input (preview)": (r["input_text"] or "")[:80].replace("\n", " "),
            "Error": (r["error"] or "")[:120],
        }
        for r in rows
    ]

    st.dataframe(
        display_rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn("Status", help="success or failed"),
        },
    )

    st.subheader("Row Detail")
    detail_id = st.number_input(
        "Enter row ID to inspect", min_value=1, step=1, value=rows[0]["id"]
    )
    if st.button("Load Detail", key="load_detail"):
        row = get_by_id(int(detail_id))
        if row:
            st.write(
                f"**Schema:** {row['schema_name']}  |  "
                f"**Status:** {row['status']}  |  "
                f"**Attempts:** {row['attempts']}"
            )
            st.write(f"**Created:** {row['created_at']}")
            with st.expander("Input Text", expanded=False):
                st.text(row["input_text"])
            if row["output_json"] is not None:
                with st.expander("Extracted JSON", expanded=True):
                    st.json(json.loads(row["output_json"]))
            if row["error"]:
                with st.expander("Error", expanded=True):
                    st.code(row["error"], language="text")
        else:
            st.warning(f"No row found with ID {detail_id}")
