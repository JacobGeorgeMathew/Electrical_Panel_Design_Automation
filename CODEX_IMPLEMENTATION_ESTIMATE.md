# PanelFlow: Codex Implementation Time, Token Budget, Models and Responsibilities

**Prepared:** 7 November 2026.  
**Planning baseline:** [ARCHITECTURE_ASSESSMENT.md](ARCHITECTURE_ASSESSMENT.md), especially Sections 4–8 and 10–12.  
**Scope:** Planning only. No implementation, paid model runs, migrations or deployment were performed.

## 1. Recommended planning budget

For the recommended architecture, use an initial planning allowance of **about 170 million cumulative model tokens, 950 hours of active Codex sessions, and 620 hours of human participation**. Under the scheduling assumptions below, that is **approximately 12 months** with one primary Codex workstream and consistent human availability. These are scenario calculations, not measured Codex performance or a guaranteed delivery date.

| Scope | Original developer effort | Central Codex active-session hours | Central human hours | Central cumulative tokens | Central elapsed schedule |
|---|---:|---:|---:|---:|---:|
| MVP: P0–P3 | 880–1,360 h | 370 h | 191 h | 70.5M | 17 weeks / about 4 months |
| Recommended: P0–P7 | 2,080–3,280 h | 945 h | 622 h | 168.5M | 52 weeks / about 12 months |
| Broader target: P0–P8 | 3,280–5,680 h | 1,710 h | 1,207 h | 281M | 98 weeks / about 23 months |

**M means one million tokens.** Tokens include repeated input context and output/reasoning across many requests, not only generated code. These numbers are not a model context-window requirement, subscription allowance, or dollar cost.

The assessment contains no measured agent throughput, token logs or human review data. Exact requirements cannot be calculated from developer hours alone. This report therefore gives explicit assumptions, low/central/high scenarios, and a calibration procedure. Treat the central values as starting budgets and the wider ranges as uncertainty envelopes—not statistical confidence bounds or guaranteed maximums.

The MVP fixes document authority, editing, history and execution reliability using bounded existing DB engineering. It excludes advanced AI, verified exact CAD and expanded professional calculations. Recommended scope adds those bounded capabilities and release hardening. P8 expands ECAD, CAD features, engineering methods and intelligence; it does not mean full AutoCAD or SolidWorks parity.

## 2. How time is calculated

### 2.1 Three different quantities

- **Original developer hours:** engineering effort estimated in the assessment without a measured Codex workflow.
- **Codex active-session hours:** elapsed time while the agent reads, reasons, edits, executes tools, waits for relevant tests/builds and repairs work. This is neither GPU time nor human labor. It excludes unattended idle time waiting for human decisions or quotas to reset.
- **Human hours:** combined effort by you and any necessary software/electrical/CAD reviewers for decisions, data, setup, review, manual verification and acceptance. You do not need to type all the code, but domain review still takes time.

Agent and human time can overlap. Adding them describes resource demand; it does not directly give elapsed duration. Test correctness, environment availability and approval delays matter more than text-generation speed on many phases.

### 2.2 Explicit conversion assumptions

Let `D` be the original phase effort. The following factors are **our planning hypotheses**, not OpenAI benchmarks. They reflect less acceleration for geometry, engineering and deployment work than for bounded schema/code changes.

| Phase | Agent-session factor × D | Human-effort factor × D | Why |
|---|---:|---:|---|
| P0 baseline/decisions | 0.20–0.35 | 0.15–0.25 | Much inspection is automated; setup/scope still need people |
| P1 documents/revisions | 0.20–0.40 | 0.10–0.20 | Mostly code/schema work after invariants are settled |
| P2 operations/editors | 0.25–0.45 | 0.10–0.20 | Cross-view state and undo need integration/UX checks |
| P3 dependencies/jobs | 0.25–0.45 | 0.15–0.25 | Concurrency/failure behavior needs deliberate review |
| P4 engineering | 0.25–0.50 | 0.25–0.40 | Approved methods/catalog facts cannot be invented |
| P5 CAD/documents | 0.30–0.55 | 0.20–0.35 | Kernel packaging, reference geometry and interoperability |
| P6 AI assistance | 0.20–0.40 | 0.15–0.25 | Code is automatable; evidence/intent quality needs review |
| P7 release | 0.25–0.45 | 0.20–0.35 | Target environments, user acceptance and restore drills |
| P8 extensions | 0.30–0.55 | 0.25–0.40 | Broad, uncertain requirements and specialist work |

Calculation:

```text
Low agent hours = baseline low hours × low agent factor
Central agent hours = baseline midpoint × midpoint agent factor
High agent hours = baseline high hours × high agent factor
Human hours use the corresponding human factors.
Round each phase to whole hours; aggregate those displayed rows.
```

The factors include ordinary code review, test writing and repair loops. The low case assumes clear requirements, working tools and reusable code; high includes substantial integration difficulty. Major scope changes or failed kernel assumptions require a new estimate.

### 2.3 Phase time budget

Each cell is **low / central / high**. Human effort includes specialist assistance where needed; physical certification services are excluded.

| Phase | Original hours | Codex active-session hours | Human hours | Main acceptance gate |
|---|---:|---:|---:|---|
| P0 baseline | 80–120 | 16 / 28 / 42 | 12 / 20 / 30 | Reproducible tests, scope and architecture decisions |
| P1 documents/revisions | 240–360 | 48 / 90 / 144 | 24 / 45 / 72 | Complete immutable history and stable identity |
| P2 operations/editors | 280–440 | 70 / 126 / 198 | 28 / 54 / 88 | Manual edits persist into published outputs |
| P3 stages/jobs/validation | 280–440 | 70 / 126 / 198 | 42 / 72 / 110 | Incremental equivalence and safe recovery/concurrency |
| P4 engineering | 400–640 | 100 / 195 / 320 | 100 / 169 / 256 | Independently reviewed engineering reference cases |
| P5 exact CAD/docs | 320–520 | 96 / 179 / 286 | 64 / 116 / 182 | Real STEP round trips and output identity |
| P6 AI | 240–400 | 48 / 96 / 160 | 36 / 64 / 100 | Valid proposals, explicit approval, deterministic checks |
| P7 release | 240–360 | 60 / 105 / 162 | 48 / 82 / 126 | Clean install, upgrades, restore and acceptance |
| P8 broader target | 1,200–2,400 | 360 / 765 / 1,320 | 300 / 585 / 960 | Separate acceptance per advanced capability |
| **MVP P0–P3** | **880–1,360** | **204 / 370 / 582** | **106 / 191 / 300** | Architecture-correct bounded editor |
| **Recommended P0–P7** | **2,080–3,280** | **508 / 945 / 1,510** | **354 / 622 / 964** | Professional bounded DB scope |
| **Full P0–P8** | **3,280–5,680** | **868 / 1,710 / 2,830** | **654 / 1,207 / 1,924** | Broader scoped architecture |

Do not add these numbers to the original developer hours; they are an alternative execution scenario for the same scope. There is no evidence supporting a claim that the entire architecture can be delivered in a few autonomous overnight runs.

### 2.4 Calendar calculation

Assume one primary Codex stream receives **40 active hours/week**, and you plus reviewers provide **20 human hours/week combined**. Assume half of the smaller workload overlaps with the larger workload across well-separated tasks. Add a scheduling allowance of 10% low, 20% central, 30% high.

```text
A = agent hours / 40
H = human hours / 20
Elapsed weeks = (A + H − 0.5 × min(A, H)) × scheduling allowance
Scheduling allowance = 1.10 / 1.20 / 1.30
```

This is a capacity approximation, not a dependency-aware project schedule. P1 must establish identity before P2 can reliably commit edits; P3 must establish job fencing before expensive asynchronous generation is trusted. If review and implementation cannot overlap, use `(A + H) × allowance` instead.

| Scope | Best-case scenario | Central scenario | Conservative scenario |
|---|---:|---:|---:|
| MVP | 9 weeks / 2 months | 17 weeks / 4 months | 29 weeks / 7 months |
| Recommended | 27 weeks / 6 months | 52 weeks / 12 months | 87 weeks / 20 months |
| Full scoped target | 48 weeks / 11 months | 98 weeks / 23 months | 171 weeks / 40 months |

Calendar months use approximately 4.33 weeks. These do not include indefinite waits for licenses, qualified reviewers, inaccessible target hardware or vendor data. Rate limits can also reduce active hours/week; account allowance was not inspected.

**Your availability is important:** for the central recommended scope, 10 human hours/week instead of 20 increases this formula to about 94 weeks, roughly 22 months. At 5 human hours/week it becomes about 163 weeks, roughly 38 months. Those hours can be shared with a teammate/reviewer; they need not all be yours.

More agents are not an automatic solution: they add repeated context, coordination and review. Consider parallel independent work only after contracts stabilize. No parallel agents were launched for this planning task.

## 3. How tokens are calculated

### 3.1 Accounting definition

```text
Total tokens = sum(input tokens + output tokens) across all model requests
Input tokens include repeated history, instructions, tool schemas, code and tool results.
Output tokens include generated text/tool arguments and reported reasoning tokens.
```

Reasoning tokens are included in reported output usage; do not add them again. The official reasoning guide documents `output_tokens_details.reasoning_tokens` and its accounting within output usage. [OpenAI reasoning documentation](https://developers.openai.com/api/docs/guides/reasoning).

Cached input is a subset of input in API usage, not a second copy to add to `input_tokens`. Caching affects cost/latency, not the cumulative input-plus-output measure used here. Cache-read/write fields and rates depend on the actual model/API. [OpenAI prompt caching documentation](https://developers.openai.com/api/docs/guides/prompt-caching).

Token estimates cover development, model-assisted review, test generation and ordinary repair. They exclude the deployed PanelFlow AI assistant's future production inference, embedding/index maintenance, user traffic and external tools' fees. A terminal's entire output is not counted merely because it exists; it contributes when passed into model context.

### 3.2 Work-package model

Divide scope into reviewable packages representing approximately **eight original developer hours** each. This is an estimating unit, not a claim that every eight-hour human task has identical AI difficulty. Each package includes implementation, relevant tests, review and fixes.

| Scenario | Model requests per package | Average input/request | Average total output/request | Tokens/package |
|---|---:|---:|---:|---:|
| Low | 20 | 9,000 | 1,000 | 200,000 = 0.20M |
| Central | 25 | 18,000 | 2,000 | 500,000 = 0.50M |
| High | 40 | 27,000 | 3,000 | 1,200,000 = 1.20M |

These averages include small tool-follow-up turns and larger reasoning/review turns. They are not per-response output limits. Long full-repository contexts, extensive reasoning or repeated failed attempts can exceed the high scenario. Conversely, very constrained edits may use far less. Account/provider usage logs must calibrate the averages.

```text
Packages_low = ceil(phase baseline low hours / 8)
Packages_central = ceil(phase baseline midpoint hours / 8)
Packages_high = ceil(phase baseline high hours / 8)
Phase tokens = packages × corresponding tokens/package
```

Example P1: baseline 240–360 h → 30 / 38 / 45 packages → **6M / 19M / 54M** tokens. Central 38 packages × 25 calls × (18,000 input + 2,000 output) = 19,000,000 tokens. Rounding packages per phase explains why central totals differ slightly from dividing the combined midpoint by eight.

### 3.3 Phase token budget

| Phase | Packages low / central / high | Low tokens | Central tokens | High tokens |
|---|---:|---:|---:|---:|
| P0 baseline | 10 / 13 / 15 | 2M | 6.5M | 18M |
| P1 documents/revisions | 30 / 38 / 45 | 6M | 19M | 54M |
| P2 commands/editors | 35 / 45 / 55 | 7M | 22.5M | 66M |
| P3 dependencies/jobs | 35 / 45 / 55 | 7M | 22.5M | 66M |
| P4 engineering | 50 / 65 / 80 | 10M | 32.5M | 96M |
| P5 CAD/docs | 40 / 53 / 65 | 8M | 26.5M | 78M |
| P6 AI | 30 / 40 / 50 | 6M | 20M | 60M |
| P7 release | 30 / 38 / 45 | 6M | 19M | 54M |
| P8 extensions | 150 / 225 / 300 | 30M | 112.5M | 360M |
| **MVP** | **110 / 141 / 170** | **22M** | **70.5M** | **204M** |
| **Recommended** | **260 / 337 / 410** | **52M** | **168.5M** | **492M** |
| **Full scoped target** | **410 / 562 / 710** | **82M** | **281M** | **852M** |

For practical central planning round to **75M MVP, 170M recommended, 285M full**. These are gross cumulative token budgets; not all input will be uncached. They cannot be translated into ChatGPT plan sufficiency or credits without the actual account's applicable limits/rates.

### 3.4 Central token composition and sensitivity

The central assumption is 90% input and 10% output:

| Scope | Input, including cached input | Output, including reasoning | Total |
|---|---:|---:|---:|
| MVP | 63.45M | 7.05M | 70.5M |
| Recommended | 151.65M | 16.85M | 168.5M |
| Full | 252.9M | 28.1M | 281M |

No cache-hit ratio or reasoning share is claimed as measured. A model producing much more reasoning can change the ratio and cost substantially.

For the 337-package recommended scope:

- Each extra 10,000 average input tokens per request adds `337 × 25 × 10,000 = 84.25M` tokens.
- Each extra five calls per package at 20,000 tokens/call adds `337 × 5 × 20,000 = 33.7M` tokens.
- Each extra 1,000 average output tokens per request adds 8.425M tokens.

This is why full-context, maximum-effort execution for every small task can be unnecessarily expensive. Token budget is much more sensitive to repeated context and retries than final source-line count.

**Cost:** no dollar amount is asserted here. For API work, apply the selected model's current input/cache-read/cache-write/output rates to their respective usage buckets, plus tool fees where applicable. For ChatGPT-authenticated Codex, use its account usage/credit rules rather than assuming raw API token pricing. Your plan, limits, billing route and usage telemetry remain unverified.

## 4. Suitable models for each phase

### 4.1 Verified model guidance versus our recommendations

Official guidance describes **GPT-6 Astra** for the most demanding work, **GPT-6.1 Sol** for repeated complex work at lower cost than Astra, **GPT-6.1 Terra** for writing/visual understanding/computer use, and **GPT-6 Luna** for focused high-volume tasks including focused coding. It distinguishes Work/Codex availability from ordinary Chat and notes that choices vary by account/client. [Official model guidance](https://learn.chatgpt.com/docs/models?surface=cli).

For this report, “ChatGPT models” means OpenAI models selectable **inside Codex**, where repository/tools are available. An ordinary chat can help review a pasted design but does not automatically have this repository or execution environment. No model or setting was changed during this task; your account-specific picker was not inspected.

**Our project-specific choice:** use Sol as the primary implementer, Astra selectively for architecture/concurrency/geometry issues and consequential review, Terra for visual/documentation assistance, and Luna for well-specified repetitive work. This is a recommendation, not a benchmark result on PanelFlow. A stronger model does not replace an independent electrical reviewer.

### 4.2 Phase assignments

Effort levels below are suggested starting settings when exposed by your client. Increase effort for difficult reasoning; keep ordinary edits at medium/default. Higher effort can increase latency/token usage; model guidance recommends increasing it when needed rather than universally. [Official reasoning-effort guidance](https://learn.chatgpt.com/docs/models?surface=cli).

| Phase | Primary coding model | Architecture/review model | Supporting work | Why this assignment |
|---|---|---|---|---|
| P0 baseline | GPT-6.1 Sol, medium | GPT-6 Astra, high | Luna for inventories; Terra for report clarity | Most work is tracing/testing; use deeper review for design contracts |
| P1 documents/revisions | GPT-6.1 Sol, high | GPT-6 Astra, high | Luna for generated types only after schema approval | Identity, migrations and immutable history are consequential |
| P2 operations/editors | GPT-6.1 Sol, medium/high | Astra, high for undo/transaction invariants | Terra for screenshots/interaction documentation | Cross-model edits require careful integration |
| P3 dependencies/jobs | GPT-6 Astra, high for core design; Sol, high for implementation | Astra reviewing focused failure cases | Sol for logging/status UI | Race conditions, stale output and dependency correctness |
| P4 engineering | GPT-6.1 Sol, high for implementing approved methods | Astra, high for algorithm critique **plus human domain review** | Luna for validated data formatting | Code reasoning cannot establish missing engineering facts |
| P5 CAD/docs | GPT-6.1 Sol, high | Astra, high for kernel/geometry failures | Terra for rendered output review; Luna for report templates | Integration and geometry edge cases dominate |
| P6 AI layer | GPT-6.1 Sol, medium/high | Astra, high for trust boundary/adversarial review | Luna for labelled fixtures; Terra for assistant UX | Need strict proposal, validation and approval boundaries |
| P7 hardening | GPT-6.1 Sol, high | Astra, high for security/concurrency review | Terra for user docs/visual acceptance; Luna for release notes | Operational failures span multiple layers |
| P8 advanced features | Astra, high for new algorithms; Sol, high for implementation | Astra and specialist humans | Terra/Luna for bounded supporting tasks | Requirements and algorithm risk are highest |

Relevant Codex identifiers in the fetched official guide are `gpt-6.1-sol`, `gpt-6-astra`, `gpt-6.1-terra`, and `gpt-6-luna`. Use only identifiers available in your installed client/account; recheck at phase start. Do not assume an API identifier, Chat label and plan entitlement are interchangeable.

A sensible **experimental** allocation is 65% of coding/review work packages to Sol, 20% to Astra, 10% to Luna and 5% to Terra. This is not a token or cost allocation—models/contexts consume differently. Avoid running every task through all four models. Escalate after a bounded failed attempt or for a specific high-risk invariant, then measure whether it helped.

P6's model recommendations above are for **building** the assistant. Choosing the model used by PanelFlow's deployed assistant requires separate accuracy, latency, privacy and cost evaluations; its production tokens are excluded from this report.

## 5. Task classification: what Codex can do and where you are needed

### 5.1 Meaning of the three categories

**1 — Codex can execute without task-by-task help:** bounded software work with agreed requirements, repository access, working dependencies/tools and appropriate authorization. It can implement, run accessible tests, debug and document. This does not mean guaranteed correctness, unrestricted permissions, or exemption from normal release review.

**2 — Codex requires your help:** you or a qualified collaborator supplies decisions, inaccessible data, credentials through secure configuration, environment access or acceptance judgment. Once those prerequisites are supplied, Codex can often execute most of the remaining software work autonomously. “Requires help” does not necessarily mean you must write code.

**3 — Cannot be completed by Codex itself:** physical measurement/manufacturing/testing, official certification/signature, or accountable engineering/product acceptance. Codex can prepare procedures, software, checklists and evidence, but cannot independently perform or authorize these outcomes. Missing software/tool access is usually Category 2, not an inherent Category 3 limitation.

The following decomposes the assessment's phase tasks. Separate software execution from its prerequisite decision rather than marking an entire phase as either autonomous or impossible.

### 5.2 P0 — Baseline and architectural decisions

| Task | Category | Codex contribution / your contribution |
|---|:---:|---|
| Inventory source, APIs, dependencies, existing tests and known gaps | 1 | Inspect and produce evidence map |
| Run accessible isolated suites, collect failures and reproduce draft/export divergence | 1 | Execute/debug once environment is ready; do not use production DB |
| Create baseline CEM/PDM/artifact regression fixtures and CI configuration | 1 | Generate software fixtures and checks |
| Provision PostgreSQL, dependency/kernel binaries and target OS access | 2 | Codex prepares commands; you provide permissions, services or machines when unavailable |
| Decide supported panel scope, deployment profile, geometry tolerance and acceptance goals | 2 | Codex compares options; you select business/domain requirements |
| Review authoritative document, identity, net and release semantics | 2 | Codex drafts ADRs; you/reviewer confirm domain assumptions |
| Run kernel proof-of-concept after dependencies/reference STEP are available | 1 | Code and execute import/build/export checks |
| Supply representative manufacturer files and independently approved reference cases | 2 | You obtain/share permitted data; Codex formats and tests it |

### 5.3 P1 — Documents and complete revisions

| Task | Category | Codex contribution / your contribution |
|---|:---:|---|
| Implement document aggregate, object registry and typed contracts | 1 | Code models/APIs/type generation from agreed schema |
| Implement migration registry and legacy identity/overlay conversion | 1 | Write conversion/rollback tests; preserve originals |
| Snapshot schematic, BOM, CAD descriptors, validation and artifact manifests | 1 | Implement complete publication/read path |
| Implement historical reads, restore-to-new-state and atomic publication | 1 | Database transactions and immutability tests |
| Update recovery/package format and projection consistency checks | 1 | Implement deterministic persistence behavior |
| Decide ambiguous legacy ID mappings, retention and package dependencies | 2 | Codex highlights conflicts; you choose policy/data interpretation |
| Migrate valuable existing user data and validate business meaning | 2 | Codex stages backup/dry-run/diff; owner authorizes production migration and checks sample records |

### 5.4 P2 — Operations and authoritative editing

| Task | Category | Codex contribution / your contribution |
|---|:---:|---|
| Build operation registry, preview, commit, idempotency and transaction history | 1 | Implement and test shared mutation boundary |
| Add undo/redo, gesture grouping and stale-proposal rejection | 1 | Write inverse/concurrency behavior and tests |
| Implement requirement/component/connection/enclosure operations | 1 | Apply agreed engineering invariants, not invented ones |
| Bind 2D/3D editing, inspector and selection to working PDM | 1 | Refactor store/components and add interaction tests |
| Add typed single-page schematic and separate graphics from connectivity | 1 | Implement CEM-grounded connections and graphical operations |
| Adapt generation into operation batches and preserve manual locks | 1 | Integration and regression tests |
| Decide permitted rotations, add/remove behavior, UX expectations and Save/Publish semantics | 2 | Codex proposes behavior; you confirm expected workflow |
| Validate real engineer interaction and accessibility on target setup | 2 | Codex automates available checks; you provide practical usability feedback |

### 5.5 P3 — Dependencies, jobs and validation

| Task | Category | Codex contribution / your contribution |
|---|:---:|---|
| Isolate stage contracts, dependency registry, hashes and cache | 1 | Implement scheduler and full/incremental equivalence tests |
| Implement job claiming, leases, retries, cancellation and fenced completion | 1 | Code and fault-injection tests in isolated environment |
| Add operation checkpoints, correlated logs and stale-output status | 1 | Integrate recovery/diagnostics |
| Reconstruct server-owned properties and prevent untrusted policy changes | 1 | Harden operation validation |
| Implement aggregate PASS/WARN/FAIL/UNRESOLVED/STALE handling | 1 | Enforce explicitly agreed policy |
| Decide which unresolved findings block engineering release | 2 | Domain owner approves policy; Codex does not decide safety acceptance alone |
| Supply deployment constraints, performance targets and fault-test access | 2 | You provide limits/access; Codex runs bounded tests |

### 5.6 P4 — Engineering strengthening

| Task | Category | Codex contribution / your contribution |
|---|:---:|---|
| Implement load model, unit handling and approved calculation methods | 1 | Convert reviewed formulas/inputs into deterministic code/tests |
| Replace fixed feeder patterns with constrained catalog selection | 1 | Implement declared suitability/ranking and rejection evidence |
| Implement net/conductor equivalence and terminal-reference checks | 1 | Code the approved electrical semantics |
| Extend placement locks, mounting/orientation constraints and zoning | 1 | Solver constraints and independent validation |
| Extend routing capacity, bend checks and segregation constraints | 1 | Algorithms/tests using supplied specs and policies |
| Add thermal applicability status and unresolved-data reporting | 1 | Implement the approved screening method and limits |
| Select applicable engineering methods/standards and supply permitted source material | 2 | Qualified reviewer chooses applicability; Codex helps compare and trace references |
| Obtain authentic ratings, conductor/terminal dimensions, curves and vendor restrictions | 2 | You/vendor supplies authoritative data; Codex validates/imports it |
| Independently review calculations, protection choices and realistic failure cases | 2 | Qualified electrical reviewer checks substance, not only passing software tests |
| Measure actual thermal rise, insulation behavior or fault performance | 3 | Laboratory/qualified people perform physical tests; Codex can analyze supplied measurements |
| Certify electrical safety/compliance or sign engineering responsibility | 3 | Authorized professionals/body must do this; model output is not certification |

### 5.7 P5 — CAD and engineering documentation

| Task | Category | Codex contribution / your contribution |
|---|:---:|---|
| Implement kernel worker adapter, declarative inputs and process isolation | 1 | Code/build/test where runtime is available |
| Implement assembly identity, transforms, tessellation and mesh cache | 1 | Software and geometric regression checks |
| Execute STEP import/export/reopen checks in an accessible kernel | 1 | Can perform actual automated CAD execution; not merely emit scripts |
| Build frozen PDF/CSV/BOM/cut-list exports and revision mapping | 1 | Implement renderers and output tests |
| Repair reproducible geometry failures using reference inputs | 1 | Debug when problem/data/tooling are accessible |
| Supply vendor STEP files, coordinate references and acceptable manufacturing tolerances | 2 | You supply source facts and acceptance criteria |
| Provide/approve kernel installation, supported OS targets and third-party CAD cross-checks | 2 | Codex packages/tests; you supply unavailable environments/licenses and approve choices |
| Confirm practical mounting access, assembly fit and manufacturing usability | 2 | Engineer/manufacturer reviews CAD and intended production workflow |
| Fabricate/assemble a panel and physically verify fit or wire access | 3 | Physical work requires people/equipment; Codex can generate drawings/checklists |

### 5.8 P6 — AI assistance

| Task | Category | Codex contribution / your contribution |
|---|:---:|---|
| Implement provider adapter, context builder and structured proposals | 1 | Backend and UI code; mocked/offline tests |
| Implement retrieval/citations from an approved corpus | 1 | Index/query/filter and provenance logic |
| Implement preview/approval/base-recheck integration | 1 | Shared operation path and no-direct-mutation guarantees |
| Add hallucinated-ID, injection, malformed-output and timeout evaluations | 1 | Fixtures, adversarial cases and automated checks |
| Configure provider account, budget, credentials and data-sharing policy | 2 | You authorize expenditure/data access; do not paste secrets into ordinary prompts |
| Supply approved knowledge sources and judge recommendation usefulness | 2 | Reviewer labels cases and acceptable answers |
| Approve actual engineering changes proposed by the deployed assistant | 2 | Human approval is a product workflow requirement, not bypassed by the coding agent |

### 5.9 P7 — Release hardening

| Task | Category | Codex contribution / your contribution |
|---|:---:|---|
| Implement CI, packaging scripts, session controls and resource limits | 1 | Software work under chosen deployment policy |
| Implement backups, asset GC, restore/upgrade/failure tests | 1 | Execute in safe accessible environments |
| Optimize measured bottlenecks and add regression benchmarks | 1 | Profiling and bounded code changes |
| Write operations/user documentation and release evidence | 1 | Draft from verified behavior/results |
| Provide target machines, signing credentials, hosting/network access and deployment approval | 2 | Owner supplies external prerequisites and authorizes release |
| Run clean-machine/third-party GUI checks where tools cannot reach | 2 | You execute guided steps or provide remote test environment |
| Decide risk acceptance and final user/product acceptance | 2 | Owner/reviewers accept release; Codex supplies evidence |
| Issue official certification or perform independent accredited testing | 3 | External accountable process; not an agent capability |

### 5.10 P8 — Broader target

| Task | Category | Codex contribution / your contribution |
|---|:---:|---|
| Implement multipage schematic, symbol library and cross-references | 1 | Once semantics and examples are specified |
| Implement bounded CAD features/sketch constraints | 1 | Prototype/code/test within available kernel; difficulty does not make it inherently impossible |
| Implement approved additional archetypes/methods and larger-design algorithms | 1 | After domain rules/data are supplied |
| Implement similar-design retrieval, richer alternatives and evaluations | 1 | Based on approved corpus and metrics |
| Select advanced feature scope, supply realistic examples and judge quality | 2 | Business/domain owners determine usefulness and constraints |
| Obtain sufficient approved historical designs and resolve reuse/data rights | 2 | You provide authorized corpus; Codex prepares ingestion |
| Conduct real-world performance qualification/manufacturing trials/certification | 3 | People/equipment/authorities perform physical and accountable tasks |

### 5.11 What “cannot be done” does not mean

Database migrations, tests, STEP execution, solver implementation, installers and security checks are **not automatically beyond Codex**. They are software tasks it can perform with suitable tools/access. However, it cannot truthfully claim a kernel export passed without executing it, a target OS works without testing it, or a panel is physically safe because unit tests pass.

Category 3 activities are relevant external completion requirements but mostly outside the software hours in the source assessment. Their cost/duration cannot be responsibly estimated without jurisdiction, panel class, manufacturing plan, laboratory scope and reviewer arrangements. If required for commercial release, add them as a separate workstream; the software schedule is not the date of certified product availability.

## 6. What you should prepare

| When | Required human input | Effect if unavailable |
|---|---|---|
| Before P0 | Safe test DB, supported OS decision, tools/install permissions, representative board | Baseline and kernel assumptions remain unverified |
| Before P1 | Document/identity/history policy and sample legacy projects | Migration may encode the wrong meaning |
| Before P2 | Supported edit operations, rotation rules and expected workflow | UI and backend invariants may diverge |
| Before P3 | Release-blocking validation policy and job/resource limits | No defensible global approval status |
| Before P4 | Qualified reviewer, reviewed calculations, permitted standards/vendor data | Code can be implemented, engineering validity remains unresolved |
| Before P5 | Representative STEP/components, tolerances, manufacturing review criteria | Geometry may be plausible but unqualified |
| Before P6 | Provider/budget/privacy decisions, curated sources and labelled proposals | Live inference/retrieval evaluations cannot be trusted |
| Before P7 | Release environment, signing/access arrangements, backup location and acceptance owner | Packaging and release remain incomplete |
| Before P8 | Explicit advanced requirements and datasets | Estimates become open-ended |

Do not wait until the end to obtain electrical review. P4's human workload is intentionally larger than ordinary application coding because approved input data and expected results are prerequisites, not optional polishing.

## 7. Recommended execution and calibration

### 7.1 First pilot: measure before committing the whole budget

Use three representative, independently accepted work packages:

1. One bounded contract/API/test change.
2. One persistence/revision-fidelity change with migration/rollback checks.
3. One component-movement vertical slice linking working PDM, validation and output.

Limit initial scope to approved pilot requirements. At the central per-package assumption, three packages use **about 1.5M tokens**; the corresponding low/high allowance is **0.6–3.6M**. This pilot is part of P0–P2, not additional project scope. It is too small to validate P4/P5/P8 estimates; calibrate those with separate domain/kernel spikes.

Record per accepted package:

```text
package_id, phase, model and effort
input_tokens, cached_input_tokens, output_tokens, reasoning_tokens (subset of output)
model_requests, tool/test runtime, active agent hours
human review/setup hours, external waiting time
acceptance result, failed attempts, defects found after acceptance
```

If the client does not expose all fields, mark them unavailable and use supported account/API usage reporting. Do not fabricate token counters or assume message count equals token usage. Deduplicate cumulative session counters; sum deltas or request records, not repeated totals.

Re-estimate using:

```text
Remaining token budget = sum(remaining packages by complexity × measured tokens/accepted package)
Remaining agent hours = sum(remaining packages by complexity × measured active hours/accepted package)
Remaining human hours = sum(remaining packages by complexity × measured human hours/accepted package)
```

Track failed attempts within the accepted-package denominator. Measure both median and upper-tail usage, and include integration defects discovered later. If averages materially exceed the assumptions, revise the forecast immediately rather than use the original number as a promise.

### 7.2 Keep each implementation task reviewable

A useful task brief specifies:

- Exact objective and non-goals.
- Files/modules likely affected and authoritative model.
- Operation/schema/identity invariants that must remain true.
- Required tests and concrete acceptance results.
- Permitted data/environment and expected migration behavior.
- Definition of done: implemented, tested, reviewed, documented and compatible with existing projects.

Prefer one narrow vertical slice over “implement the whole architecture.” Save accepted decisions and short phase handoffs in the repository during implementation. Provide relevant files/test outputs instead of repeatedly sending the entire report and repository. Avoid maximum reasoning effort for routine renames/types/docs; use stronger reasoning for unresolved invariants and failures. Stop retry loops to diagnose missing information rather than repeatedly regenerate similar patches.

### 7.3 Suggested first delivery sequence

1. P0 baseline and decisions.
2. P1 working document plus frozen historical outputs.
3. A narrow P2 MoveComponent operation with save/reopen/publish/export consistency.
4. Remaining bounded commands and authoritative schematic editing.
5. P3 stage invalidation and durable jobs.
6. Re-estimate MVP completion from measured throughput before expanding to P4–P7.

Manual, automatic and later AI workflows must share the operation/document boundary. Do not accelerate apparent progress by implementing AI changes directly against workspace overlays; that creates rework and defeats the target architecture.

## 8. Final recommendation

Start with **GPT-6.1 Sol** as the coding default and use **GPT-6 Astra** for consequential architecture/concurrency/geometry review. Use **Terra** for visual/document work and **Luna** for tightly bounded repetitive tasks, where available. These phase assignments are project-specific recommendations based on the official model roles, not a measured PanelFlow model comparison. [OpenAI model guidance](https://learn.chatgpt.com/docs/models?surface=cli).

Budget the **MVP first**: central **70.5M tokens, 370 agent hours and 191 human hours**, about **four months** under the stated availability assumptions. For the recommended application, central planning is **168.5M tokens, 945 agent hours and 622 human hours**, about **12 months**. The full scoped target is central **281M tokens, 1,710 agent hours and 1,207 human hours**, about **23 months**.

Codex can perform much of the repository implementation without task-by-task help once contracts and prerequisites are settled. Your most important contributions are scope decisions, trusted engineering data, independent review, environment access and acceptance. Physical validation and official certification remain external work. Calibrate the forecast after the pilot and again after the engineering/kernel spikes.
