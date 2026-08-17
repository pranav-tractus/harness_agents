# Agent Harness — Architecture

A visual map of the **benchmark harness**: how a chat file becomes a scored,
reported run. For the task-oriented walkthrough (configuring agents, CLI
recipes, few-shot modes) see [`multi_customer_harness.md`](multi_customer_harness.md).
For the *other* system in this repo — the live chat-simulation app under
`apps/` — see [`architecture.md`](architecture.md).

> The diagrams below pin `theme: dark`. Drop the `%%{init: …}%%` line from any
> block if you'd rather it follow the reader's GitHub theme.

---

## The harness at a glance

```mermaid
%%{init: {'theme':'dark'}}%%
flowchart TB
  ENTRY["Entrypoints<br/>CLI · Streamlit Dashboard"]

  subgraph cfg ["Configuration"]
    JSON["configs/agents.json"]
    HCFG["HarnessConfig<br/>get_agent · build_pipeline"]
    JSON --> HCFG
  end

  ORCH["Runner (Orchestration)<br/>harness/runner.py"]

  subgraph inputs ["Inputs"]
    SRC["raw_data/<br/>chats · emails · specs"]
    FS["few-shot pool<br/>+ variant planner"]
  end

  subgraph agents ["Pluggable Agents — BaseAgent of I, O"]
    SOA["SO Extraction Agent"]
    PRA["Product Retrieval Agent"]
  end

  subgraph twolayer ["Extraction — two layers"]
    L1["Layer 1<br/>ExtractionEngine → raw JSON"]
    L2["Layer 2<br/>deterministic rules"]
    L2B["Validation LLM<br/>+ date freeze"]
    L1 --> L2 --> L2B
  end

  subgraph retr ["Retrieval"]
    RANK["load specs → ranked docs"]
  end

  subgraph scoring ["Scoring & Quality"]
    JD["json_diff<br/>field mismatches"]
    RM["retrieval_metrics<br/>precision@K · recall@K · MRR"]
    DUAL["dual scoring<br/>raw vs final vs baseline"]
  end

  subgraph artifacts ["Artifacts — results/&lt;run_id&gt;/"]
    JSONL["run.jsonl"]
    AGG["aggregate.json"]
    RPT["report.html"]
    CONF["config.json"]
  end

  subgraph reporting ["Reporting"]
    DASHHTML["dashboard report"]
    PITCH["pitch report"]
    TOKENS["token report"]
    STORY["LLM narrative<br/>report_summary"]
  end

  subgraph curation ["Expected-results curation (feedback loop)"]
    SEED["seed_expected"]
    AUTO["auto_expected<br/>best-of-N + AST rewrite"]
    EXP["expected_results.py"]
    SEED --> EXP
    AUTO --> EXP
  end

  ENTRY --> HCFG
  HCFG --> ORCH
  inputs --> ORCH
  ORCH --> SOA
  ORCH --> PRA
  SOA --> L1
  PRA --> RANK
  L2B --> JD
  RANK --> RM
  JD --> DUAL
  RM --> DUAL
  DUAL --> JSONL
  JSONL --> AGG --> RPT
  ORCH --> CONF
  RPT --> DASHHTML
  RPT --> PITCH
  RPT --> TOKENS
  RPT --> STORY
  AGG -.-> AUTO
  EXP -.-> DUAL

  classDef entry fill:#8e44ad,stroke:#b06fc4,color:#fff
  classDef orch fill:#4a4f93,stroke:#7c81c4,color:#fff
  classDef a1 fill:#1f4e79,stroke:#4b8dc4,color:#fff
  classDef a2 fill:#7a3b3b,stroke:#b56b6b,color:#fff
  class ENTRY entry
  class ORCH orch
  class SOA a1
  class PRA a2
```

**Reading it:** everything funnels through one orchestrator. `agents.json` is
the only place an agent is declared; the runner is generic over whatever it
finds there and never imports a concrete agent.

---

## Run modes

The runner has three modes off one argument parser. Bulk is the interesting
one — it is a **four-way cross product**, which is why a "small" sweep can be
thousands of LLM calls.

```mermaid
%%{init: {'theme':'dark'}}%%
flowchart LR
  ARGS["harness.runner args"]

  subgraph single ["Single"]
    S1["--chat one_file.json"]
  end

  subgraph bulk ["Bulk sweep"]
    B1["sources<br/>× models<br/>× few-shot variants<br/>× runs-per-chat"]
    B2["ThreadPoolExecutor<br/>--max-workers 50"]
    B3["checkpoint:<br/>re-aggregate + rewrite report<br/>every N runs"]
    B1 --> B2 --> B3
  end

  subgraph pipe ["Pipeline"]
    P1["steps from agents.json"]
    P2["output of step N<br/>→ input of step N+1"]
    P3["halt on first failure"]
    P1 --> P2 --> P3
  end

  ARGS --> S1
  ARGS --> B1
  ARGS --> P1
  S1 --> OUT["AgentRunResult records"]
  B3 --> OUT
  P3 --> OUT

  classDef orch fill:#4a4f93,stroke:#7c81c4,color:#fff
  class ARGS orch
```

Few-shot selection is its own axis with four mutually exclusive modes —
`explicit` / `walk` / `sweep` / `none` — planned up front by
`harness/fewshot.py` so a sweep is reproducible from `--few-shot-seed`.

---

## The two-layer extraction agent

`SOExtractionAgent` is the only fully-built agent. It wraps the `core/`
extraction library and keeps **both** snapshots so post-processing can be
measured rather than assumed.

```mermaid
%%{init: {'theme':'dark'}}%%
flowchart TB
  CHAT["chat JSON"]

  subgraph l1 ["Layer 1 — Extraction"]
    PS["prompt strategy"]
    FSI["few-shot injection<br/>files + DB-backed"]
    CTX["organization_info<br/>customer_info"]
    ENG["ExtractionEngine → SOExtractContractList"]
    PS --> ENG
    FSI --> ENG
    CTX --> ENG
  end

  RAW["raw_llm_output_json"]

  subgraph l2 ["Layer 2 — Post-processing"]
    DET["deterministic rules<br/>units · recompute totals"]
    WARN["date warnings only<br/>never mutates dates"]
    VLLM["validation LLM<br/>separate model key"]
    FREEZE["freeze date fields<br/>copied back from raw"]
    DET --> WARN --> VLLM --> FREEZE
  end

  FINAL["output_json (final)"]
  BASE["baseline extractor"]

  CHAT --> ENG --> RAW --> DET
  FREEZE --> FINAL
  CHAT --> BASE

  RAW --> SR["score_raw_llm"]
  FINAL --> SF["score (final)"]
  BASE --> SB["score_baseline"]

  classDef a1 fill:#1f4e79,stroke:#4b8dc4,color:#fff
  classDef good fill:#1b5e3a,stroke:#4f9e73,color:#fff
  class ENG a1
  class FINAL good
```

Two invariants worth carrying in your head:

- **Dates are never auto-corrected.** The deterministic stage emits warnings
  only, and every date field is copied back verbatim from the raw extraction
  after the validation LLM runs. Everything else (units, totals) may be fixed.
- **Downstream consumers use `output_json`.** `raw_llm_output_json` is kept
  purely so the report can show what post-processing changed.

---

## Artifacts and reporting

One folder per run, written incrementally so a long sweep is inspectable
while it is still going.

```mermaid
%%{init: {'theme':'dark'}}%%
flowchart LR
  REC["AgentRunResult"]

  subgraph dir ["results/&lt;run_id&gt;/"]
    J["run.jsonl<br/>append-only, one row per run"]
    A["aggregate.json<br/>rollups by model · strategy<br/>fs_count · dataset · agent"]
    C["config.json<br/>full invocation"]
    H["report.html"]
  end

  subgraph rend ["Renderers"]
    D["report_dashboard_html"]
    P["report_pitch_html"]
    T["token_report_html"]
    B["results_brief<br/>+ report_summary narrative"]
  end

  UI["Streamlit<br/>Results Browser"]

  REC --> J --> A --> H
  REC --> C
  H --> D
  H --> P
  H --> T
  A --> B --> H
  A --> UI
  J --> UI

  classDef store fill:#2f3136,stroke:#7a7f87,color:#e8e8ea
  class J,A,C,H store
```

`config.json` exists so the dashboard can reload and re-run an invocation
exactly. `report.html` is rewritten at every checkpoint; the LLM narrative
layer is only generated on the final write (and skipped entirely with
`--no-report-llm`).

---

## Two systems, one `core/`

The repo name is plural for a reason — there are two independent runtimes,
and they meet only at the shared extraction library.

```mermaid
%%{init: {'theme':'dark'}}%%
flowchart TB
  subgraph bench ["Benchmark harness — offline, batch"]
    HR["harness/ + agents/ + dashboard/"]
    RES["results/ · extractions.db"]
    HR --> RES
  end

  subgraph live ["Chat simulation — online, interactive"]
    API["apps/api + apps/web"]
    STORES["MongoDB · FalkorDB · S3 Vectors"]
    API --> STORES
  end

  subgraph shared ["core/ — shared library"]
    LLM["llm_client<br/>schema-coerced calls"]
    MOD["models<br/>SOExtractContractList"]
    EMB["embeddings"]
    PP["postprocess_pipeline"]
  end

  HR --> LLM
  HR --> MOD
  HR --> PP
  API --> LLM
  API --> MOD
  API --> EMB

  classDef a1 fill:#1f4e79,stroke:#4b8dc4,color:#fff
  classDef a2 fill:#7a3b3b,stroke:#b56b6b,color:#fff
  class HR a1
  class API a2
```

They share schemas and the LLM client, but **not** state: the harness scores
against curated `expected_results.py` fixtures and writes to `results/` and
SQLite, while the app writes to Mongo, FalkorDB and S3 Vectors. Neither reads
the other's stores.

---

## Component map

| Box in the diagram | Code |
|---|---|
| Configuration | `configs/agents.json`, `agents/config.py::HarnessConfig` |
| Agent contract | `agents/base.py::BaseAgent` (`load_input` · `run_one` · `expected_for` · `score`) |
| Pipeline | `agents/base.py::Pipeline` |
| Orchestration | `harness/runner.py` (`_run_bulk` · `_run_pipeline`) |
| Few-shot planning | `harness/fewshot.py::plan_few_shot_variants` |
| SO extraction agent | `agents/so_extraction/agent.py::SOExtractionAgent` |
| Two-layer extraction | `core/extractor.py`, `core/postprocess_pipeline.py` |
| Retrieval agent (scaffold) | `agents/product_retrieval/agent.py` |
| Scoring | `harness/scoring.py::json_diff`, `::retrieval_metrics` |
| Run record | `agents/base.py::AgentRunResult` |
| Artifacts | `harness/artifacts.py` (`append_record` · `aggregate` · `write_report`) |
| Reports | `harness/report_dashboard_html.py`, `report_pitch_html.py`, `token_report_html.py`, `report_summary.py`, `results_brief.py` |
| Expected curation | `harness/seed_expected.py`, `harness/auto_expected.py` |
| UI | `dashboard/app.py` (Single · Bulk · Results · Seed · Auto tabs) |
