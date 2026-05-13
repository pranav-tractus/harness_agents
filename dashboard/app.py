"""Unified Streamlit dashboard.

Tabs:
- Single Run    : run one chat through a chosen agent (HITL panel for SO extraction).
- Bulk Benchmark: configure a sweep and launch via the unified runner.
- Results Browser: combine artifacts from one or more ``results/<run_id>/`` folders.
- Seed Expected : draft new ``expected_results.py`` entries with diff vs current.

Run:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import json
import logging
import pprint
import re
import subprocess
import sys
from pathlib import Path
from statistics import mean
from typing import Any

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.base import RunOptions
from agents.config import load_config
from agents.so_extraction.agent import ChatInput
from core.chat_loader import labeled_chat_paths_for_globs, load_chat_file
from core.db import SavedSummary, get_history, get_summary_chain, init_db, save_summary
from core.utils import DEFAULT_MODEL_KEY, MODEL_CATALOG, setup_streamlit_console_logfile
from harness import artifacts
from harness.report_summary import narrative_to_markdown, summarize_brief
from harness.results_brief import brief_from_slim_records, headline_metrics, leaderboard_by_combo
from harness.scoring import normalize_contract_shape

# Reload the few-shot helper on every Streamlit rerun so edits to
# harness/fewshot.py are picked up without a full server restart. Streamlit's
# hot-reload only re-executes this script; sibling modules cached in
# sys.modules would otherwise stay pinned to an older revision (which is how
# you'd see e.g. ``unexpected keyword argument 'walk_paths'`` after editing the
# planner while the dashboard is still running).
import importlib
from harness import fewshot as _fewshot_module
importlib.reload(_fewshot_module)
plan_few_shot_variants = _fewshot_module.plan_few_shot_variants

setup_streamlit_console_logfile()
logger = logging.getLogger(__name__)

RESULTS_DIR = artifacts.RESULTS_DIR_DEFAULT


@st.cache_resource(show_spinner=False)
def _config():
    return load_config()


@st.cache_data(show_spinner=False)
def _agent_pool_labels(agent_id: str) -> list[tuple[str, str]]:
    cfg = _config()
    agent = cfg.get_agent(agent_id)
    pairs = labeled_chat_paths_for_globs([str(p) for p in []] if False else list(agent._few_shot_globs), agent.repo_root)
    return [(label, str(path)) for label, path in pairs]


@st.cache_data(show_spinner=False)
def _agent_source_labels(agent_id: str) -> list[tuple[str, str, str]]:
    cfg = _config()
    agent = cfg.get_agent(agent_id)
    labels: list[tuple[str, str, str]] = []
    for dataset_id, path in agent.all_source_paths():
        try:
            rel = str(path.relative_to(agent.repo_root))
        except ValueError:
            rel = str(path)
        labels.append((f"[{dataset_id}] {rel}", str(path), dataset_id))
    labels.sort(key=lambda x: x[0].lower())
    return labels


def _list_run_dirs() -> list[Path]:
    if not RESULTS_DIR.exists():
        return []
    out: list[Path] = []
    for p in sorted(RESULTS_DIR.iterdir(), reverse=True):
        if p.is_dir() and (p / "aggregate.json").exists():
            out.append(p)
    return out


def _load_run_records(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "run.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _coerce_paths(strs: list[str]) -> list[Path]:
    return [Path(s) for s in strs if s]


st.set_page_config(page_title="Agent Harness", layout="wide", initial_sidebar_state="expanded")
st.title("Agent Harness Dashboard")
st.caption("Single agent runs, pipelines, bulk benchmarks, and expected-results curation in one place.")

cfg = _config()
init_db()

with st.sidebar:
    st.header("Configuration")
    model_options = list(MODEL_CATALOG.keys())
    default_idx = model_options.index(DEFAULT_MODEL_KEY) if DEFAULT_MODEL_KEY in model_options else 0
    selected_model = st.selectbox(
        "Model",
        model_options,
        index=default_idx,
        format_func=lambda k: MODEL_CATALOG[k]["display_name"],
        key="sidebar_model",
    )
    agent_ids = cfg.agent_ids()
    selected_agent_id = st.selectbox("Agent", agent_ids, key="sidebar_agent")
    selected_pipeline_id = st.selectbox(
        "Pipeline (optional)",
        ["(none)"] + cfg.pipeline_ids(),
        key="sidebar_pipeline",
    )
    db_lim = st.number_input(
        "DB few-shot limit",
        min_value=0,
        max_value=10,
        value=0,
        step=1,
        help="How many DB-backed saved summaries to include as few-shot examples.",
        key="sidebar_db_lim",
    )


tab_single, tab_bulk, tab_results, tab_seed = st.tabs([
    "Single Run",
    "Bulk Benchmark",
    "Results Browser",
    "Seed Expected",
])


# Tab: Single Run -----------------------------------------------------------

with tab_single:
    agent = cfg.get_agent(selected_agent_id)
    pipeline = (
        cfg.build_pipeline(selected_pipeline_id)
        if selected_pipeline_id and selected_pipeline_id != "(none)"
        else None
    )

    sources = _agent_source_labels(selected_agent_id)
    if not sources:
        st.info("This agent has no source paths declared in agents.json.")
    else:
        col_left, col_right = st.columns([1, 1], gap="large")
        with col_left:
            st.subheader("Pick a source")
            selected_label = st.selectbox(
                "Source path",
                [label for label, *_ in sources],
                key="single_source",
            )
            source_path_str = next(p for label, p, _ in sources if label == selected_label)
            source_path = Path(source_path_str)

            chat_data = load_chat_file(source_path)
            meta = chat_data.get("meta", {})
            if meta.get("chat_name"):
                st.caption(f"Chat: **{meta['chat_name']}**")
            if meta.get("created_at"):
                st.caption(f"Date: {meta['created_at']}")
            if meta.get("realism_flags"):
                st.caption(f"Realism flags: {', '.join(meta['realism_flags'])}")
            st.text_area("Preview", value=chat_data.get("text", ""), height=240, disabled=True, key="single_preview")

            st.subheader("Few-shot examples (cap 10)")
            pool = _agent_pool_labels(selected_agent_id)
            picked = st.multiselect(
                "Pick 0-10 chats from this agent's few-shot pool",
                [label for label, _ in pool],
                default=[],
                key="single_fs",
                max_selections=10,
            )
            fs_paths = [Path(p) for label, p in pool if label in picked]

            run_btn = st.button("Run", type="primary", width="stretch", key="single_run_btn")

        with col_right:
            st.subheader("Output")
            if run_btn:
                with st.spinner(f"Running {agent.id} on {source_path.name}..."):
                    payload = agent.load_input(source_path)
                    opts = RunOptions(
                        model_key=selected_model,
                        few_shot_paths=fs_paths,
                        extra={"db_few_shot_limit": db_lim},
                    )
                    result = agent.run_one(payload, opts)
                st.write(
                    f"**Status:** `{result.status}` | attempts={result.attempts} | "
                    f"elapsed={result.elapsed_sec:.2f}s | mismatches={result.score.mismatch_count}"
                )
                if result.output_json is not None:
                    st.json(result.output_json)
                if result.score.mismatches:
                    with st.expander("Mismatches vs expected"):
                        st.json(result.score.mismatches)
                if result.error:
                    st.error(result.error)
                st.session_state["draft_summary"] = result.output_json
                st.session_state["draft_input_text"] = chat_data.get("text", "")
                st.session_state["draft_source_chat"] = source_path.name
                st.session_state["draft_attempts"] = result.attempts

            if pipeline is not None and run_btn:
                st.divider()
                st.subheader("Pipeline downstream steps")
                if pipeline.agents[0].id != agent.id:
                    st.info(
                        "Selected pipeline does not start with the active agent; "
                        "downstream steps not run."
                    )
                else:
                    upstream_output = (
                        result.output if result.success else None
                    )
                    if upstream_output is None:
                        st.warning("Upstream step did not produce output; skipping downstream.")
                    else:
                        for step_idx, step_agent in enumerate(pipeline.agents[1:], start=1):
                            with st.spinner(f"Running {step_agent.id} (step {step_idx})..."):
                                payload_next = step_agent.load_input(upstream_output)
                                step_opts = RunOptions(
                                    model_key=selected_model,
                                    few_shot_paths=[],
                                    extra={},
                                )
                                step_res = step_agent.run_one(payload_next, step_opts)
                            st.write(
                                f"**{step_agent.id}** -> status=`{step_res.status}` | "
                                f"elapsed={step_res.elapsed_sec:.2f}s"
                            )
                            if step_res.error:
                                st.error(step_res.error)
                            if step_res.output_json is not None:
                                st.json(step_res.output_json)
                            if step_res.output is None:
                                break
                            upstream_output = step_res.output

            if st.session_state.get("draft_summary"):
                st.divider()
                st.subheader("Save to DB")
                if st.button("Save summary to extractions DB", key="single_save_btn"):
                    saved = SavedSummary(
                        kind="initial",
                        schema_name=agent.output_type.__name__ if hasattr(agent.output_type, "__name__") else "agent_output",
                        input_text=st.session_state.get("draft_input_text", ""),
                        output_json=json.dumps(st.session_state["draft_summary"], indent=2, ensure_ascii=False),
                        source_chat=st.session_state.get("draft_source_chat"),
                        attempts=int(st.session_state.get("draft_attempts", 1)),
                        model_key=selected_model,
                    )
                    new_id = save_summary(saved)
                    st.success(f"Saved as summary #{new_id}.")


# Tab: Bulk Benchmark -------------------------------------------------------

with tab_bulk:
    st.subheader("Configure bulk run")
    agent = cfg.get_agent(selected_agent_id)
    bulk_agent_id = st.selectbox(
        "Agent",
        cfg.agent_ids(),
        index=cfg.agent_ids().index(selected_agent_id),
        key="bulk_agent",
    )
    bulk_pipeline_id = st.selectbox(
        "Pipeline (optional, overrides agent)",
        ["(none)"] + cfg.pipeline_ids(),
        key="bulk_pipeline",
    )
    datasets = [d.id for d in cfg.get_agent(bulk_agent_id).datasets()]
    selected_datasets = st.multiselect("Datasets", datasets, default=datasets, key="bulk_datasets")
    bulk_models = st.multiselect(
        "Models",
        list(MODEL_CATALOG.keys()),
        default=[selected_model],
        key="bulk_models",
        help=(
            "Pick one or more models. Every (source × model × few-shot variant × run) combo "
            "is scheduled on the same thread pool, so models run concurrently."
        ),
    )
    if len(bulk_models) > 1:
        st.caption(f"Concurrent across {len(bulk_models)} models: {', '.join(bulk_models)}")
    runs_per_chat = st.number_input("Runs per chat", min_value=1, max_value=10, value=1, key="bulk_runs")
    max_workers = st.number_input("Max workers", min_value=1, max_value=32, value=8, key="bulk_workers")
    skip_no_expected = st.checkbox("Skip chats without expected entries", value=True, key="bulk_skip_no_expected")

    st.subheader("Few-shot strategy")
    bulk_agent = cfg.get_agent(bulk_agent_id)
    pool = _agent_pool_labels(bulk_agent_id)
    label_to_path = {label: path for label, path in pool}
    st.caption(
        f"Few-shot pool for `{bulk_agent_id}` contains **{len(pool)}** files "
        f"(globs: {list(bulk_agent._few_shot_globs)})."
    )

    # Mode picker: exactly one of {none, explicit, walk, sweep} is active per run.
    FS_MODES = {
        "none": "None — every variant has 0 few-shot examples",
        "explicit": "Explicit — one fixed set applied to every chat",
        "walk": "Walk — fs0..fsN over a hand-picked, ordered list",
        "sweep": "Sweep — nested random sampling at the requested counts",
    }
    fs_mode = st.radio(
        "Mode",
        options=list(FS_MODES.keys()),
        format_func=lambda k: FS_MODES[k],
        index=0,
        key="bulk_fs_mode",
        horizontal=False,
        help=(
            "Pick exactly one strategy. The inputs below switch to match — only the controls "
            "for the active mode affect this run. Precedence on the CLI mirrors this radio: "
            "explicit > walk > sweep > none."
        ),
    )

    explicit: list[str] = []
    walk_labels: list[str] = []
    walk_paths: list[Path] = []
    curated_pool_labels: list[str] = []
    curated_pool_paths: list[Path] = []
    sweep_str = ""
    sweep_counts: list[int] = []

    if fs_mode == "none":
        st.info(
            "No few-shot examples will be sent. The run will produce a single `fs0` variant per "
            "(chat × model × runs-per-chat) combination."
        )

    elif fs_mode == "explicit":
        with st.container(border=True):
            st.markdown("**Explicit picks** — one fixed set, applied to every chat.")
            explicit = st.multiselect(
                "Few-shot files (cap 10)",
                [label for label, _ in pool],
                max_selections=10,
                key="bulk_fs_explicit",
            )
            if explicit:
                st.caption(
                    f"Selected **{len(explicit)}** files. Every chat will see the same few-shot set, "
                    "yielding a single variant per chat."
                )
            else:
                st.caption("Pick 1–10 files to populate the single variant.")

    elif fs_mode == "walk":
        with st.container(border=True):
            st.markdown(
                "**Walk** — order matters. Picking `[A, B, C]` yields four variants per chat: "
                "`fs0=[]`, `fs1=[A]`, `fs2=[A,B]`, `fs3=[A,B,C]`."
            )
            walk_labels = st.multiselect(
                "Pick chats in order (cap 10)",
                [label for label, _ in pool],
                max_selections=10,
                key="bulk_fs_walk",
            )
            walk_paths = [Path(label_to_path[label]) for label in walk_labels]
            if walk_labels:
                st.caption(
                    f"Walk will produce **{len(walk_labels) + 1}** variants "
                    f"(fs0..fs{len(walk_labels)}) from the picked chats, in this exact order."
                )
            else:
                st.caption("Pick at least one chat; you'll always also get an `fs0` (empty) variant.")

    elif fs_mode == "sweep":
        with st.container(border=True):
            st.markdown(
                "**Sweep** — nested random sampling from the few-shot pool. "
                "The pool is shuffled once with the seed below, then each requested count takes "
                "a prefix of that shuffle (so `count=2` ⊂ `count=5` ⊂ `count=10`)."
            )
            sweep_str = st.text_input(
                "Counts (comma-separated 0..10)",
                value="",
                key="bulk_fs_sweep",
                help="Example: `0,2,5` runs three variants per chat.",
                placeholder="0,1,3,5,10",
            )
            if sweep_str.strip():
                for token in sweep_str.split(","):
                    tok = token.strip()
                    if tok.isdigit():
                        sweep_counts.append(int(tok))
            curated_pool_labels = st.multiselect(
                "Optional: restrict sweep to a curated subset of the pool",
                [label for label, _ in pool],
                default=[],
                key="bulk_fs_pool",
                help=(
                    "Leave empty to sample from the agent's full pool of "
                    f"{len(pool)} files."
                ),
            )
            curated_pool_paths = [Path(label_to_path[label]) for label in curated_pool_labels]
            if curated_pool_labels:
                st.caption(
                    f"Sweep will draw from **{len(curated_pool_labels)}** curated files "
                    f"instead of the full pool of {len(pool)}."
                )

    # Seed + self-fewshot only meaningful for sweep mode. Walk mode is deterministic;
    # explicit/none don't sample. Show seed only when relevant, but keep allow-self
    # visible across all sampling modes because it still gates leakage in walk/explicit.
    if fs_mode == "sweep":
        fs_seed = st.number_input(
            "Sampling seed",
            min_value=0,
            max_value=10_000,
            value=42,
            step=1,
            key="bulk_fs_seed",
            help="Deterministic seed for the one-time shuffle of the pool.",
        )
    else:
        fs_seed = 42  # unused; kept for the CLI invocation below.

    if fs_mode == "none":
        allow_self_fewshot = False  # nothing to leak.
    else:
        allow_self_fewshot = st.checkbox(
            "Allow source chat in its own few-shot list",
            value=False,
            key="bulk_allow_self_fewshot",
            help=(
                "Off by default: the chat being tested is excluded from its own few-shot list "
                "(applies after pool curation / walk picks). Turn on only when you specifically "
                "want to measure that case."
            ),
        )

    # Live preview of what each variant will actually contain.
    show_preview = (
        (fs_mode == "explicit" and explicit)
        or (fs_mode == "walk" and walk_paths)
        or (fs_mode == "sweep" and sweep_counts)
    )
    if show_preview:
        with st.expander("Preview few-shot variants", expanded=True):
            preview_variants = plan_few_shot_variants(
                bulk_agent,
                explicit_paths=[label_to_path[label] for label in explicit] if fs_mode == "explicit" else None,
                walk_paths=walk_paths if fs_mode == "walk" else None,
                sweep_counts=sweep_counts if fs_mode == "sweep" else None,
                seed=int(fs_seed),
                pool_override=curated_pool_paths if (fs_mode == "sweep" and curated_pool_paths) else None,
            )
            st.caption(
                f"Mode: **{fs_mode}** · {len(preview_variants)} variant(s) per (chat × model × run)."
            )
            for label, count, paths in preview_variants:
                rels = []
                for p in paths:
                    try:
                        rels.append(str(p.relative_to(bulk_agent.repo_root)))
                    except ValueError:
                        rels.append(str(p))
                st.write(f"**{label}** (requested count={count}, actual={len(rels)})")
                if not rels:
                    st.caption("(no few-shot examples)")
                else:
                    st.code("\n".join(rels) or "(empty)", language="text")
    elif fs_mode != "none":
        st.caption("Pick at least one input above to see the variant preview.")

    if st.button("Launch bulk run", type="primary", key="bulk_run_btn"):
        cmd = [sys.executable, "-m", "harness.runner"]
        if bulk_pipeline_id and bulk_pipeline_id != "(none)":
            cmd += ["--pipeline", bulk_pipeline_id]
        else:
            cmd += ["--agent", bulk_agent_id]
        if selected_datasets:
            cmd += ["--datasets", *selected_datasets]
        if bulk_models:
            cmd += ["--models", *bulk_models]
        cmd += ["--runs-per-chat", str(int(runs_per_chat))]
        cmd += ["--max-workers", str(int(max_workers))]
        cmd += ["--db-few-shot-limit", str(int(db_lim))]
        if skip_no_expected:
            cmd += ["--skip-without-expected"]
        if fs_mode == "explicit" and explicit:
            cmd += ["--few-shot", *[label_to_path[label] for label in explicit]]
        elif fs_mode == "walk" and walk_paths:
            cmd += ["--few-shot-walk", *[str(p) for p in walk_paths]]
        elif fs_mode == "sweep" and sweep_counts:
            cmd += ["--few-shot-sweep", *[str(c) for c in sweep_counts]]
            if curated_pool_paths:
                cmd += ["--few-shot-pool", *[str(p) for p in curated_pool_paths]]
            cmd += ["--few-shot-seed", str(int(fs_seed))]
        if allow_self_fewshot:
            cmd += ["--allow-self-fewshot"]
        st.code(" ".join(cmd))
        with st.spinner("Running bulk job (this may take a few minutes)..."):
            proc = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True)
        st.subheader("stdout")
        st.code(proc.stdout or "(empty)")
        if proc.returncode != 0:
            st.subheader("stderr")
            st.code(proc.stderr or "(empty)")
            st.error(f"Run failed with exit code {proc.returncode}.")
        else:
            st.success("Run complete. See the Results Browser tab below.")


# Tab: Results Browser ------------------------------------------------------

with tab_results:
    run_dirs = _list_run_dirs()
    if not run_dirs:
        st.info("No results found. Launch a bulk run from the Bulk Benchmark tab to populate this.")
    else:
        view_mode = st.radio(
            "View mode",
            ["Single run", "Combine multiple runs"],
            horizontal=True,
            key="results_view_mode",
        )
        if view_mode == "Single run":
            picked_dir = st.selectbox(
                "Run folder",
                run_dirs,
                format_func=lambda p: p.name,
                key="results_single_dir",
            )
            selected_dirs = [picked_dir]
        else:
            picked_dirs = st.multiselect(
                "Run folders",
                run_dirs,
                default=run_dirs[: min(5, len(run_dirs))],
                format_func=lambda p: p.name,
                key="results_multi_dirs",
            )
            selected_dirs = list(picked_dirs)

        if not selected_dirs:
            st.info("Pick at least one run folder.")
        else:
            all_records: list[dict[str, Any]] = []
            for run_dir in selected_dirs:
                rows = _load_run_records(run_dir)
                for r in rows:
                    r["_run_dir"] = run_dir.name
                all_records.extend(rows)

            with st.expander("Configurations"):
                for run_dir in selected_dirs:
                    cfg_path = run_dir / "config.json"
                    if cfg_path.exists():
                        st.write(f"**{run_dir.name}**")
                        st.json(json.loads(cfg_path.read_text(encoding="utf-8")))

            if not all_records:
                st.warning("No records in selected runs.")
            else:
                providers = sorted({
                    str(r.get("model_key", "")).split(":", 1)[0] if ":" in str(r.get("model_key", "")) else "bedrock"
                    for r in all_records
                })
                models_present = sorted({r["model_key"] for r in all_records if r.get("model_key")})
                agents_present = sorted({r["agent_id"] for r in all_records})
                datasets_present = sorted({r.get("dataset_id", "default") for r in all_records})
                chats_present = sorted({r["source_filename"] for r in all_records if r.get("source_filename")})

                f1, f2, f3, f4 = st.columns(4)
                sel_agents = f1.multiselect("Agents", agents_present, default=agents_present)
                sel_models = f2.multiselect("Models", models_present, default=models_present)
                sel_providers = f3.multiselect("Providers", providers, default=providers)
                sel_datasets = f4.multiselect("Datasets", datasets_present, default=datasets_present)
                sel_chats = st.multiselect("Chats", chats_present, default=chats_present)

                def _passes(r: dict[str, Any]) -> bool:
                    provider = (
                        str(r.get("model_key", "")).split(":", 1)[0]
                        if ":" in str(r.get("model_key", "")) else "bedrock"
                    )
                    return (
                        r["agent_id"] in sel_agents
                        and r["model_key"] in sel_models
                        and provider in sel_providers
                        and r.get("dataset_id", "default") in sel_datasets
                        and r.get("source_filename") in sel_chats
                    )

                filtered = [r for r in all_records if _passes(r)]
                if not filtered:
                    st.info("No records match the filters.")
                else:
                    hm = headline_metrics(filtered)
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Runs", hm["runs"])
                    m2.metric(
                        "Success rate",
                        f"{hm['success_rate']:.1%}" if hm["success_rate"] is not None else "—",
                    )
                    m3.metric(
                        "Avg runtime (s)",
                        f"{(hm['avg_runtime_sec'] or 0):.3f}" if hm["avg_runtime_sec"] is not None else "—",
                    )
                    m4.metric(
                        "Mismatch stdev",
                        f"{(hm['mismatch_stdev'] or 0):.3f}" if hm["mismatch_stdev"] is not None else "—",
                    )

                    leaderboard_rows = leaderboard_by_combo(filtered)
                    st.subheader("Agent + Model + FS-count Leaderboard")
                    st.dataframe(leaderboard_rows, use_container_width=True, hide_index=True)

                    st.subheader("AI summary")
                    st.caption(
                        "Uses the filtered rows above (same metrics/leaderboard). "
                        "Requires Gemini credentials (same as running Gemini models in the harness)."
                    )
                    if st.button("Generate AI summary", type="secondary", key="results_ai_summary_btn"):
                        try:
                            meta = {
                                "run_folders": [p.name for p in selected_dirs],
                                "filters": {
                                    "agents": list(sel_agents),
                                    "models": list(sel_models),
                                    "providers": list(sel_providers),
                                    "datasets": list(sel_datasets),
                                    "chats": list(sel_chats),
                                },
                            }
                            brief = brief_from_slim_records(filtered, meta=meta)
                            with st.spinner("Using Gemini 2.5 Pro..."):
                                narrative = summarize_brief(brief)
                            label = ", ".join(meta["run_folders"])
                            st.session_state["results_ai_summary_md"] = narrative_to_markdown(
                                label, narrative
                            )
                            st.session_state.pop("results_ai_summary_err", None)
                        except Exception as exc:
                            st.session_state["results_ai_summary_err"] = str(exc)
                            logger.exception("AI report summary failed")
                    err = st.session_state.get("results_ai_summary_err")
                    if err:
                        st.error(err)
                    md_out = st.session_state.get("results_ai_summary_md")
                    if md_out:
                        st.caption("If you changed filters, click Generate again for an up-to-date summary.")
                        st.markdown(md_out)

                    st.subheader("Per-chat Breakdown")
                    chat_buckets: dict[tuple, list[dict[str, Any]]] = {}
                    for r in filtered:
                        chat_buckets.setdefault(
                            (r["agent_id"], r.get("source_filename"), r["model_key"], r.get("few_shot_count", 0)),
                            [],
                        ).append(r)
                    chat_rows = [
                        {
                            "agent": k[0],
                            "chat": k[1],
                            "model": k[2],
                            "fs_count": k[3],
                            "runs": len(v),
                            "success_rate": sum(1 for x in v if x["success"]) / len(v),
                            "avg_elapsed_sec": _safe_mean([x["elapsed_sec"] for x in v]),
                            "mismatch_counts": [
                                int(x["mismatch_count"]) for x in v if x.get("expected_available")
                            ],
                        }
                        for k, v in sorted(chat_buckets.items())
                    ]
                    st.dataframe(chat_rows, use_container_width=True, hide_index=True)

                    st.subheader("Mismatch inspector")
                    with_mm = [r for r in filtered if r.get("mismatches")]
                    if with_mm:
                        chosen = st.selectbox(
                            "Run with mismatches",
                            with_mm,
                            format_func=lambda r: f"{r['agent_id']} | {r['model_key']} | fs={r.get('few_shot_count', 0)} | {r.get('source_filename')} | step={r.get('pipeline_step', 0)}",
                            key="results_mm_pick",
                        )
                        st.json(chosen["mismatches"])
                    else:
                        st.success("No mismatches in current selection.")


# Tab: Seed Expected --------------------------------------------------------

with tab_seed:
    st.subheader("Draft expected_results entries")
    seed_agent_id = st.selectbox(
        "Agent",
        cfg.agent_ids(),
        index=cfg.agent_ids().index(selected_agent_id),
        key="seed_agent",
    )
    agent = cfg.get_agent(seed_agent_id)
    sources = _agent_source_labels(seed_agent_id)
    if not sources:
        st.info("Selected agent has no datasets configured.")
    else:
        picked_label = st.selectbox(
            "Source",
            [label for label, *_ in sources],
            key="seed_source",
        )
        picked_path = Path(next(p for label, p, _ in sources if label == picked_label))
        runs = st.number_input("Runs (most-stable wins)", min_value=1, max_value=5, value=1, key="seed_runs")
        pool = _agent_pool_labels(seed_agent_id)
        seed_fs = st.multiselect(
            "Few-shot examples (cap 10)",
            [label for label, _ in pool],
            max_selections=10,
            key="seed_fs",
        )
        fs_paths = [Path(p) for label, p in pool if label in seed_fs]

        if st.button("Draft expected entry", type="primary", key="seed_run"):
            payload = agent.load_input(picked_path)
            best = None
            best_score = (10**6, 10**6)
            for run_idx in range(1, int(runs) + 1):
                with st.spinner(f"Run {run_idx}..."):
                    opts = RunOptions(
                        model_key=selected_model,
                        few_shot_paths=fs_paths,
                        extra={"db_few_shot_limit": db_lim},
                    )
                    result = agent.run_one(payload, opts)
                if result.output_json is None:
                    st.warning(f"Run {run_idx} failed: {result.error}")
                    continue
                candidate = (result.score.mismatch_count, result.elapsed_sec)
                if candidate < best_score:
                    best_score = candidate
                    best = {
                        "output": normalize_contract_shape(result.output_json) or result.output_json,
                        "result": result,
                    }
            if not best:
                st.error("All runs failed.")
            else:
                current = agent.expected_for(picked_path)
                st.write("**Best output:**")
                st.json(best["output"])
                if current is not None:
                    st.write("**Diff vs current expected (truncated):**")
                    st.json({"current": current, "proposed": best["output"]})
                else:
                    st.info("No existing expected entry for this source.")
                copy_block = (
                    f"    {picked_path.name!r}: "
                    + pprint.pformat(best["output"], indent=4, width=100, sort_dicts=False).replace("\n", "\n    ")
                    + ","
                )
                st.write("**Paste into agent's `expected_results.EXPECTED_BY_CHAT`:**")
                st.code(copy_block, language="python")


# Saved summaries history (DB-backed) --------------------------------------

st.divider()
st.subheader("Saved Summaries History")
col_refresh, col_limit, _ = st.columns([1, 1, 4])
with col_refresh:
    st.button("Refresh", width="stretch", key="refresh_history")
with col_limit:
    history_limit = st.number_input("Rows", min_value=5, max_value=200, value=20, step=5, key="history_limit")

rows = get_history(limit=int(history_limit))
if rows:
    st.dataframe(
        [
            {
                "ID": r["id"],
                "Parent": r["parent_summary_id"],
                "Kind": r["kind"],
                "Schema": r["schema_name"],
                "Source": (r["source_chat"] or "pasted")[:60],
                "Model": r.get("model_key", "unknown"),
                "Created": r["created_at"],
            }
            for r in rows
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.caption("No saved summaries yet.")
