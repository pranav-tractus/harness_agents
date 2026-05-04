"""Streamlit dashboard for the Extraction Agent POC.

Run with:
    streamlit run app.py
"""

import json
from pathlib import Path

import streamlit as st

from chat_loader import (
    build_extraction_few_shot_from_paths,
    labeled_raw_chat_paths,
    list_chat_files,
    load_chat_file,
)
from db import (
    SavedSummary,
    get_history,
    get_summary_chain,
    init_db,
    save_summary,
)
from extractor import ExtractionEngine
from models import SOExtractContractList, SOUpdateContractList
from utils import BEDROCK_ANTHROPIC_MODELS, setup_streamlit_console_logfile

setup_streamlit_console_logfile()


INITIAL_SCHEMA = SOExtractContractList
UPDATE_SCHEMA = SOUpdateContractList


st.set_page_config(
    page_title="Extraction Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Extraction Agent")
st.caption(
    "Structured contract extraction with human-in-the-loop summary updates · "
    f"initial schema = `{INITIAL_SCHEMA.__name__}` · update schema = `{UPDATE_SCHEMA.__name__}`"
)

init_db()


# Session state defaults

def _ss_default(key: str, value):
    if key not in st.session_state:
        st.session_state[key] = value


_ss_default("draft_summary", None)            # dict | None — current in-memory summary
_ss_default("draft_kind", None)               # 'initial' | 'update' | None
_ss_default("draft_attempts", 0)
_ss_default("draft_prompt_text", None)
_ss_default("draft_input_text", "")           # original chat text the draft is based on
_ss_default("draft_source_chat", None)        # filename or 'pasted'
_ss_default("draft_parent_summary_id", None)  # the saved id of the previous version (if any)
_ss_default("draft_update_instruction", None) # the instruction that produced the current draft
_ss_default("draft_history", [])              # list of dicts shown to the user as a timeline


# Sidebar

with st.sidebar:
    st.header("Configuration")

    model_options = list(BEDROCK_ANTHROPIC_MODELS.keys())
    selected_model = st.selectbox("Bedrock Model", model_options, index=0)

    st.divider()
    st.subheader("Locked schemas")
    with st.expander(f"Initial: {INITIAL_SCHEMA.__name__}", expanded=False):
        st.json(INITIAL_SCHEMA.model_json_schema(), expanded=False)
    with st.expander(f"Update: {UPDATE_SCHEMA.__name__}", expanded=False):
        st.json(UPDATE_SCHEMA.model_json_schema(), expanded=False)

    st.divider()
    st.subheader("Few-shot sources")

    st.checkbox(
        "Include database examples for initial extraction",
        value=True,
        help=(
            "Use recent saved **initial** summaries from the database as few-shot "
            "examples (same as before). Turn off to rely only on raw JSON files below."
        ),
        key="fs_include_db_initial",
    )

    _lbl_paths = labeled_raw_chat_paths()
    _fs_options = [lbl for lbl, _ in _lbl_paths]
    st.multiselect(
        "Raw JSON files for initial extraction few-shot",
        options=_fs_options,
        default=[],
        help=(
            "Pick any mix of `raw_data/chats/`, `raw_data/downloaded_chats/`, and "
            "`raw_data/chats/updates/`. Gold JSON is taken from `field_data` or "
            "`generated_summary`; files without those are skipped."
        ),
        key="fs_initial_raw_paths",
    )

    st.checkbox(
        "Include synthetic update chats as few-shot examples",
        help=(
            "When applying an LLM summary update, prepend few-shot pairs from "
            "`raw_data/chats/updates/` (before examples from saved summaries)."
        ),
        key="include_syn_update_fewshot",
    )

    _upd_files = list_chat_files().get("updates", [])
    _upd_names = [p.name for p in _upd_files]
    st.multiselect(
        "Limit update few-shot to these files (optional)",
        options=_upd_names,
        default=[],
        help=(
            "When synthetic update few-shot is enabled: leave empty to use **all** "
            "JSON files under `raw_data/chats/updates/`. Otherwise only the selected "
            "files contribute chained examples."
        ),
        key="fs_update_raw_names",
    )


# Helpers

def _reset_draft() -> None:
    st.session_state.draft_summary = None
    st.session_state.draft_kind = None
    st.session_state.draft_attempts = 0
    st.session_state.draft_prompt_text = None
    st.session_state.draft_input_text = ""
    st.session_state.draft_source_chat = None
    st.session_state.draft_parent_summary_id = None
    st.session_state.draft_update_instruction = None
    st.session_state.draft_history = []


def _set_initial_draft(result, source_chat: str | None, input_text: str) -> None:
    if result.status != "success" or not result.output_json:
        st.session_state.draft_summary = None
        return
    parsed = json.loads(result.output_json)
    st.session_state.draft_summary = parsed
    st.session_state.draft_kind = "initial"
    st.session_state.draft_attempts = result.attempts
    st.session_state.draft_prompt_text = result.prompt_text
    st.session_state.draft_input_text = input_text
    st.session_state.draft_source_chat = source_chat
    st.session_state.draft_parent_summary_id = None
    st.session_state.draft_update_instruction = None
    st.session_state.draft_history = [
        {"step": "initial", "schema": result.schema_name, "attempts": result.attempts}
    ]


def _set_update_draft(result, instruction: str) -> None:
    if result.status != "success" or not result.output_json:
        return
    parsed = json.loads(result.output_json)
    st.session_state.draft_summary = parsed
    st.session_state.draft_kind = "update"
    st.session_state.draft_attempts = result.attempts
    st.session_state.draft_prompt_text = result.prompt_text
    st.session_state.draft_update_instruction = instruction
    st.session_state.draft_history.append({
        "step": "update",
        "schema": result.schema_name,
        "attempts": result.attempts,
        "instruction": instruction,
    })


def _persist_current_draft() -> int | None:
    """Persist the in-memory draft as a row in the ``summaries`` table.

    Initial drafts are saved with ``kind='initial'`` and ``parent_summary_id=None``.
    Update drafts are saved with ``kind='update'`` and the parent linked to the most
    recently saved version of the same chain. After saving, the new row's id becomes
    the ``parent_summary_id`` for any subsequent update saved in this session.
    """
    if not st.session_state.draft_summary:
        st.warning("Nothing to save yet. Run an extraction first.")
        return None

    output_json = json.dumps(st.session_state.draft_summary, indent=2, ensure_ascii=False)

    if st.session_state.draft_kind == "initial":
        schema_name = INITIAL_SCHEMA.__name__
    else:
        schema_name = UPDATE_SCHEMA.__name__

    summary = SavedSummary(
        kind=st.session_state.draft_kind or "initial",
        schema_name=schema_name,
        input_text=st.session_state.draft_input_text or "",
        output_json=output_json,
        parent_summary_id=st.session_state.draft_parent_summary_id,
        source_chat=st.session_state.draft_source_chat,
        prompt_text=st.session_state.draft_prompt_text,
        update_instruction=st.session_state.draft_update_instruction,
        attempts=st.session_state.draft_attempts or 1,
    )
    new_id = save_summary(summary)

    st.session_state.draft_parent_summary_id = new_id
    st.session_state.draft_kind = "update"
    return new_id


def _render_draft_panel(engine: ExtractionEngine) -> None:
    """Render the human-in-the-loop review/update/save panel for the current draft."""
    if st.session_state.draft_summary is None:
        return

    st.divider()
    st.subheader("Human-in-the-loop review")

    kind_label = (st.session_state.draft_kind or "initial").upper()
    parent_label = (
        f"parent #{st.session_state.draft_parent_summary_id}"
        if st.session_state.draft_parent_summary_id
        else "no parent (unsaved initial)"
    )
    st.caption(
        f"Draft kind: **{kind_label}**  ·  Source: `{st.session_state.draft_source_chat or 'pasted'}`  ·  {parent_label}"
    )

    col_summary, col_actions = st.columns([2, 1], gap="large")

    with col_summary:
        st.markdown("**Current summary draft**")
        st.json(st.session_state.draft_summary)

        if st.session_state.draft_history:
            with st.expander("Revision timeline (this session)", expanded=False):
                for i, step in enumerate(st.session_state.draft_history, start=1):
                    line = f"{i}. **{step['step']}** · schema=`{step['schema']}` · attempts={step['attempts']}"
                    if step.get("instruction"):
                        line += f"\n    > _{step['instruction']}_"
                    st.markdown(line)

    with col_actions:
        st.markdown("**Save**")
        if st.button("💾 Save summary", type="primary", width='stretch', key="save_btn"):
            new_id = _persist_current_draft()
            if new_id is not None:
                st.success(f"Saved as summary #{new_id}.")

        st.markdown("**Ask LLM to update**")
        instruction = st.text_area(
            "Update instruction",
            placeholder="e.g. 'Change KNM Coffee quantity to 8 bags and recompute totals.'",
            height=140,
            key="update_instruction_input",
        )
        if st.button(
            "🔁 Apply update",
            width='stretch',
            key="apply_update_btn",
            disabled=not instruction.strip(),
        ):
            with st.spinner("Asking LLM to revise the summary…"):
                _upd_by_name = {p.name: p for p in list_chat_files().get("updates", [])}
                _upd_pick = st.session_state.get("fs_update_raw_names") or []
                _syn_paths = None
                if st.session_state.get("include_syn_update_fewshot", False):
                    if _upd_pick:
                        _syn_paths = [
                            _upd_by_name[n] for n in _upd_pick if n in _upd_by_name
                        ]
                    else:
                        _syn_paths = None
                result = engine.update(
                    previous_summary=st.session_state.draft_summary,
                    update_instruction=instruction.strip(),
                    original_input_text=st.session_state.draft_input_text or None,
                    include_synthetic_update_few_shot=st.session_state.get(
                        "include_syn_update_fewshot", False
                    ),
                    synthetic_update_few_shot_paths=_syn_paths,
                )
            if result.status == "success":
                _set_update_draft(result, instruction.strip())
                st.success(f"Update produced in {result.attempts} attempt(s).")
                st.rerun()
            else:
                st.error(f"Update failed after {result.attempts} attempt(s)")
                st.code(result.error or "Unknown error", language="text")

        st.markdown("---")
        if st.button("🧹 Discard draft", width='stretch', key="discard_btn"):
            _reset_draft()
            st.rerun()


# Main input area — two tabs

tab_file, tab_updates = st.tabs([
    "Load Chat File",
    "Load Update Scenario",
])


# ── Tab 1: load from existing chat files ───────────────────────────────────

@st.cache_data(show_spinner=False)
def _peek_created_at(path_str: str) -> str:
    """Return the created_at string from a chat JSON file without full parsing."""
    try:
        with open(path_str, encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("created_at", "") or ""
    except Exception:
        return ""


with tab_file:
    chat_files = list_chat_files()
    all_files: dict[str, Path] = {}
    for folder, paths in chat_files.items():
        if folder == "updates":
            continue
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

            chat_data = load_chat_file(selected_path)
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

            if chat_data["field_data"]:
                with st.expander("Reference extraction (field_data)", expanded=False):
                    st.json(chat_data["field_data"])

            file_run = st.button(
                "Extract from this chat",
                type="primary",
                width='stretch',
                key="file_run",
            )

        with col_chat_output:
            st.subheader("Initial extraction output")
            file_output = st.container()

        if file_run:
            if not chat_text.strip():
                st.warning("Selected chat file produced no text — cannot extract.")
            else:
                with st.spinner(f"Extracting from {selected_path.name}…"):
                    engine = ExtractionEngine(model_key=selected_model)
                    label_to_p = dict(labeled_raw_chat_paths())
                    chosen = st.session_state.get("fs_initial_raw_paths") or []
                    fs_paths = [label_to_p[x] for x in chosen if x in label_to_p]
                    extra_fs = (
                        build_extraction_few_shot_from_paths(fs_paths) if fs_paths else []
                    )
                    db_lim = 5 if st.session_state.get("fs_include_db_initial", True) else 0
                    result = engine.run(
                        chat_text,
                        extra_few_shot_examples=extra_fs or None,
                        db_few_shot_limit=db_lim,
                    )
                with file_output:
                    if result.status == "success":
                        st.success(f"Extraction succeeded in {result.attempts} attempt(s)")
                        _set_initial_draft(result, source_chat=selected_path.name, input_text=chat_text)
                    else:
                        st.error(f"Extraction failed after {result.attempts} attempt(s)")
                        st.code(result.error or "Unknown error", language="text")


# ── Tab 2: load a pre-baked update scenario ────────────────────────────────

with tab_updates:
    update_scenarios = list_chat_files().get("updates", [])
    if not update_scenarios:
        st.info("No update scenarios found in raw_data/chats/updates/")
    else:
        col_scenario, col_actions = st.columns([1, 1], gap="large")

        with col_scenario:
            st.subheader("Select scenario")
            options = {p.name: p for p in update_scenarios}
            selected_name = st.selectbox(
                "Update scenario",
                list(options.keys()),
                key="scenario_select",
            )
            scenario_path = options[selected_name]
            scenario = load_chat_file(scenario_path)

            if scenario["meta"].get("description"):
                st.caption(scenario["meta"]["description"])
            if scenario["meta"].get("source_chat"):
                st.caption(f"Source chat: `{scenario['meta']['source_chat']}`")

            st.markdown("**Chat preview**")
            st.text_area(
                "scenario_preview",
                value=scenario["text"],
                height=200,
                disabled=True,
                label_visibility="collapsed",
            )

            with st.expander("Pre-baked generated summary", expanded=False):
                st.json(scenario["generated_summary"] or {})

            with st.expander("Suggested updates", expanded=False):
                for i, upd in enumerate(scenario.get("updates", []), start=1):
                    st.markdown(f"**Update #{i}** — _{upd.get('instruction', '')}_")
                    st.json(upd.get("expected_summary") or {}, expanded=False)

        with col_actions:
            st.subheader("Load scenario into draft")
            st.write(
                "Loads the pre-baked generated summary as the current draft so you can "
                "iterate on it with real LLM update calls. The draft is **not** persisted "
                "until you click Save."
            )
            if st.button(
                "📥 Load as initial draft",
                type="primary",
                width='stretch',
                key="load_scenario_btn",
                disabled=not scenario.get("generated_summary"),
            ):
                _reset_draft()
                st.session_state.draft_summary = scenario["generated_summary"]
                st.session_state.draft_kind = "initial"
                st.session_state.draft_attempts = 1
                st.session_state.draft_prompt_text = None
                st.session_state.draft_input_text = scenario["text"]
                st.session_state.draft_source_chat = scenario_path.name
                st.session_state.draft_history = [
                    {"step": "initial-loaded", "schema": INITIAL_SCHEMA.__name__, "attempts": 1}
                ]
                st.success("Scenario loaded as initial draft. Scroll down to review/update/save.")


# Active draft panel

engine_for_draft = ExtractionEngine(model_key=selected_model)
_render_draft_panel(engine_for_draft)


# History

st.divider()
st.subheader("Saved summaries")

col_refresh, col_limit, _ = st.columns([1, 1, 4])
with col_refresh:
    st.button("🔄 Refresh", width='stretch', key="refresh_history")
with col_limit:
    history_limit = st.number_input("Rows", min_value=5, max_value=200, value=20, step=5)

rows = get_history(limit=int(history_limit))

if not rows:
    st.info("No saved summaries yet. Run an extraction and click Save.")
else:
    display_rows = [
        {
            "ID": r["id"],
            "Parent": r["parent_summary_id"],
            "Kind": r["kind"],
            "Schema": r["schema_name"],
            "Attempts": r["attempts"],
            "Source": (r["source_chat"] or "pasted")[:40],
            "Created": r["created_at"],
            "Instruction (preview)": (r["update_instruction"] or "")[:80].replace("\n", " "),
        }
        for r in rows
    ]
    st.dataframe(display_rows, width='stretch', hide_index=True)

    st.subheader("Inspect chain")
    detail_id = st.number_input(
        "Enter any summary ID — its full chain (initial -> updates) is shown",
        min_value=1, step=1, value=rows[0]["id"],
    )
    if st.button("Load chain", key="load_chain"):
        # find root by walking parent links
        def _root_id(rid: int) -> int:
            cur = rid
            for _ in range(50):
                row = next((r for r in get_history(limit=500) if r["id"] == cur), None)
                if row is None or row["parent_summary_id"] is None:
                    return cur
                cur = row["parent_summary_id"]
            return cur

        root = _root_id(int(detail_id))
        chain = get_summary_chain(root)
        if not chain:
            st.warning(f"No chain found for ID {detail_id}")
        else:
            for i, step in enumerate(chain):
                header = (
                    f"#{step['id']} · {step['kind']} · schema=`{step['schema_name']}`"
                    f" · created {step['created_at']}"
                )
                with st.expander(header, expanded=(i == len(chain) - 1)):
                    if step["update_instruction"]:
                        st.markdown(f"**Update instruction:** _{step['update_instruction']}_")
                    if step["output_json"]:
                        st.json(json.loads(step["output_json"]))
