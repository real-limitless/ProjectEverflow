---
name: vibeless
description: A command-driven workflow for building and managing AI vibe-coded applications sustainably. Use this skill when the user invokes /vibeless, wants to define a project goal, create an AI app, or execute/hand off any vibeless plan.
argument-hint: No arguments needed — the skill shows a help menu on launch.
---

# Vibeless — Command-Driven Sustainable AI Builder

When this skill is active, display the following help menu, then wait for a `#command`.

---

## Help Menu (show on `/vibeless`)

```
╔══════════════════════════════════════════════════════════╗
║                 VIBELESS  —  command menu                ║
╠══════════════════════════════════════════════════════════╣
║  #init         <project_path>   Initialize vibeless      ║
║                                                          ║
║  #goal create  <name>   Define a new project goal        ║
║  #goals                 List all goals                   ║
║  #app create   <name>   Define a new AI app              ║
║  #apps                  List all apps                    ║
║                                                          ║
║  #execute      <name>            Run a goal or app plan  ║
║  #execute      <name> --auto     Run without step pauses ║
║  #orchestrate  <name>            Run with supervisor +   ║
║                                  parallel subagents      ║
║  #agents       <name>            Show subagent roster    ║
║  #status       <name>            Show execution progress ║
║  #amend        <name>            Update a plan mid-run   ║
║  #checkpoint   <name>            Verify and record step  ║
║  #doc          <name>            Documentation sweep     ║
║  #compound     <name>            Propose takeaways       ║
║                                                          ║
║  #handoff      <name>            Save session state      ║
║  #help                           Show this menu          ║
╚══════════════════════════════════════════════════════════╝

Storage root: .vibeless/
```

All state lives under `.vibeless/` at the project root. Every command that touches the filesystem creates or updates files there. Sessions survive across chat restarts because everything is written to disk.

---

## #init \<project_path\>

**Purpose:** Bootstrap the `.vibeless/` folder structure inside a project. Run this once before using any other command.

**Steps:**

1. Resolve the target path. `<project_path>` may be:
   - An absolute path (e.g., `/projects/my-app`)
   - A relative path from the current working directory (e.g., `./my-app` or `my-app`)
   - `.` to initialize in the current directory

2. Verify the target path exists. If it does not, tell the user and stop — `#init` initializes an existing project directory, it does not create one.

3. Check whether `.vibeless/` already exists at that path. If it does, tell the user it is already initialized and list what is inside. Do not overwrite anything.

4. Create the following directory structure:
   ```
   <project_path>/
   └── .vibeless/
       ├── goal/
       ├── apps/
       └── VIBELESS.md
   ```

5. Write `<project_path>/.vibeless/VIBELESS.md`:

```markdown
# Vibeless

Initialized: <ISO date>
Project: <project_path>

## Storage Layout

.vibeless/
├── goal/                         # One subdirectory per goal
│   └── <name>/
│       ├── <NNN>_<subject>.md    # Session memory files
│       ├── VIBE.md               # Executable plan
│       ├── checkpoints/          # Per-step verification records
│       ├── deviations/           # Mid-execution plan conflicts
│       ├── decisions/            # Key decision notes
│       ├── subagents/            # Orchestration briefs and outputs
│       └── COMPOUND.md           # Post-execution takeaways
├── apps/                         # One subdirectory per app
│   └── <name>/
│       ├── <NNN>_<subject>.md    # Session memory files
│       ├── APP.md                # App specification and build plan
│       ├── checkpoints/
│       ├── deviations/
│       ├── decisions/
│       ├── subagents/
│       └── COMPOUND.md
└── HANDOFF.md                    # Current session state (written by #handoff)
```

## Commands
Run `/vibeless` in your AI session to see the full command menu.
```

6. Confirm success: tell the user where `.vibeless/` was created and what to do next — run `/vibeless` to see the command menu, then `#goal create <name>` or `#app create <name>` to start.

---

## #goal create \<name\>

**Purpose:** Define what you want to accomplish. The result is a plan you can `#execute` later.

**Steps:**

1. Create the directory `.vibeless/goal/<name>/` if it does not exist.

2. **Check for an existing interview.** Look for session memory files already under `.vibeless/goal/<name>/`. If any exist, read them all and tell the user what you already know, then ask only the questions that are still unanswered. Do not re-ask questions that were already answered in a prior session.

3. Check for an existing handoff: if `.vibeless/HANDOFF.md` references this goal, load that context before starting the interview.

4. **Interview the user.** Ask one question at a time — never a bullet-dump. Keep asking until you have clear answers for all of:
   - What outcome does this goal achieve, and for whom?
   - What does "done" look like in concrete, observable terms?
   - What constraints exist (tech stack, budget, timeline, existing code)?
   - What is explicitly out of scope for now?

5. **After each answer that reveals something useful**, write a session memory file:
   ```
   .vibeless/goal/<name>/<session_number>_<short_subject>.md
   ```
   - `<session_number>` starts at `001` and increments within this goal. Check existing files to determine the next number.
   - `<short_subject>` is a 2–4 word kebab-case label (e.g., `001_target-users.md`, `002_success-criteria.md`).
   - Each file contains only the useful fact extracted from that answer — no filler, no re-stating the question.

6. When the interview is complete and you have enough clarity, write `.vibeless/goal/<name>/VIBE.md` using this structure:

```markdown
# VIBE: <name>

## Goal
One or two sentences stating the end objective and who it serves.

## Done Looks Like
Concrete, observable criteria — what the user will be able to do or see when this goal is achieved.

## Constraints
Explicit list of known constraints (stack, budget, timeline, integrations).

## Out of Scope
Explicit list of things deliberately excluded from this goal.

## Execution Plan
Step-by-step instructions written so that any AI model or developer can pick this up cold and execute it. Each step should be atomic and verifiable. No vague directions.

## Open Questions
Anything still unresolved that execution will need to address.
```

7. Confirm: tell the user the goal is saved and how to run it with `#execute <name>`.

---

## #goals

List all directories under `.vibeless/goal/`. For each, show:
- Goal name
- Whether `VIBE.md` exists (ready to execute) or not (interview incomplete)
- Number of session memory files
- Number of checkpoints completed (from `.vibeless/goal/<name>/checkpoints/`)

---

## #app create \<name\>

**Purpose:** Define an AI-powered application you want built. The result is a specification you can `#execute` later.

**Steps:**

1. Create the directory `.vibeless/apps/<name>/` if it does not exist.

2. **Check for an existing interview.** Look for session memory files already under `.vibeless/apps/<name>/`. If any exist, read them all and tell the user what you already know, then ask only the questions still unanswered. Do not re-ask questions answered in a prior session.

3. Check for an existing handoff: if `.vibeless/HANDOFF.md` references this app, load that context before starting the interview.

4. **Offer a starter template.** Before asking any interview questions, ask the user if their app fits one of these common patterns. If they pick one, pre-fill the known answers for that template and skip those interview questions — only ask what is unique to their app.

   | Template | Pre-fills |
   |----------|-----------|
   | **Claude Chatbot** | Interface: chat (terminal or web); AI integration: Claude via Anthropic SDK, model calls isolated in one module; Data flow: user message → system prompt + history → Claude → assistant reply |
   | **RAG Pipeline** | Interface: CLI or API; AI integration: embedding model + Claude for generation; Data flow: document corpus → chunk + embed → vector store → query → retrieved chunks + Claude → answer |
   | **CLI Tool** | Interface: command-line flags/arguments; AI integration: Claude for a single transformation task; Data flow: file or stdin → prompt → Claude → stdout or file output |
   | **API Wrapper / Agent** | Interface: REST API or SDK; AI integration: Claude with tool use; Data flow: structured request → tool-augmented Claude → structured response |

   If none fit, proceed with the full interview.

5. **Interview the user** for any unanswered questions. Ask one question at a time until you have clear answers for all of:
   - What does this app do, in one sentence?
   - Who uses it and how do they interact with it (CLI, chat, web, API)?
   - What AI model or provider is preferred, and why?
   - What data does it take in and what does it produce?
   - What does a successful demo of this app look like?
   - What happens when things go wrong — bad model output, rate limits, missing data?
   - What is explicitly out of scope for the first version?

6. **After each answer that reveals something useful**, write a session memory file:
   ```
   .vibeless/apps/<name>/<session_number>_<short_subject>.md
   ```
   Same numbering and naming convention as goals.

7. When the interview is complete, write `.vibeless/apps/<name>/APP.md` using this structure:

```markdown
# APP: <name>

## What It Does
One paragraph describing the app and its purpose.

## Users & Interface
Who uses it and how they interact with it.

## AI Integration
Model/provider, what the model is responsible for, isolation strategy (all model calls go through one module — never scattered through business logic).

## Data Flow
What goes in → what the model sees → what comes out.

## Failure Modes
What happens when the model returns garbage, hits a rate limit, or gets bad input. Defined now, not discovered later.

## Done Looks Like
What a working demo produces that you can verify by hand.

## Out of Scope (v1)
Explicit exclusions for the first version.

## Build Plan
Ordered list of build steps, each atomic and verifiable. Includes: project scaffold, model integration, core logic, failure handling, verification, documentation.

## Key Decisions
Any stack, model, or architecture choices made during the interview, and why.
```

8. Confirm: tell the user the app spec is saved and how to build it with `#execute <name>`.

---

## #apps

List all directories under `.vibeless/apps/`. For each, show:
- App name
- Whether `APP.md` exists (ready to execute) or not (interview incomplete)
- Number of session memory files
- Number of checkpoints completed (from `.vibeless/apps/<name>/checkpoints/`)

---

## #execute \<name\> [--auto]

**Purpose:** Carry out the plan defined in a `VIBE.md` (goal) or `APP.md` (app), one verified step at a time.

**Flags:**
- _(no flag)_ — pause after every step and ask "Continue to step N+1?" before proceeding.
- `--auto` — run all steps without pausing between them. Still stops on any deviation and still writes a checkpoint after every step. Use when you trust the plan and want uninterrupted execution.

**Steps:**

1. Determine type: check `.vibeless/goal/<name>/VIBE.md` first, then `.vibeless/apps/<name>/APP.md`. If neither exists, tell the user the plan is not ready and suggest completing the interview.

2. Load the plan file and all session memory files in the relevant directory for full context.

3. Check `.vibeless/HANDOFF.md` — if it references this name, load the current session state and resume from where it left off rather than starting over. Check existing checkpoints to identify the last completed step and begin from the next one.

4. For **each step** in the Execution Plan or Build Plan, follow this loop exactly — do not skip any part of it:

   **a. Announce** — State which step you are about to execute and what it will produce.

   **b. Execute** — Build or do only that step. Nothing more.

   **c. Verify** — Demonstrate the step worked:
   - Show the happy path: the expected output or behavior when everything is correct.
   - Show at least one failure or edge case: what happens when input is bad, a dependency is missing, or the model misbehaves. If verification is impossible in the current environment, state that explicitly — do not silently skip it.

   **d. Checkpoint** — Automatically write a checkpoint file (do not wait for the user to run `#checkpoint`):
   ```
   .vibeless/goal/<name>/checkpoints/<step_N>_<short_subject>.md
   OR
   .vibeless/apps/<name>/checkpoints/<step_N>_<short_subject>.md
   ```
   See `#checkpoint` below for the file format.

   **e. Report & continue** — Tell the user what was built and confirmed.
   - If a deviation was found: write a deviation note (see below), **always stop**, and ask how to proceed — even in `--auto` mode.
   - If no deviation and running normally: ask "Continue to step N+1?"
   - If no deviation and running `--auto`: proceed immediately to the next step without asking.

5. **On deviation:** If a step reveals the plan was wrong or incomplete, **stop** (regardless of `--auto`). Write a deviation note to:
   ```
   .vibeless/goal/<name>/deviations/<step_N>_<short_subject>.md
   OR
   .vibeless/apps/<name>/deviations/<step_N>_<short_subject>.md
   ```
   Format:
   ```markdown
   ## Deviation: <short subject>
   **Discovered at:** Step <N>
   **What the plan said:** ...
   **What we found instead:** ...
   **Impact:** ...
   **Proposed resolution:** ...
   ```
   Then ask the user how to proceed. Options to offer: update the plan with `#amend <name>`, skip this step, or abort execution.

6. When all steps are complete, prompt the user to run `#doc <name>` and then `#compound <name>`.

---

## #status \<name\>

**Purpose:** Show execution progress at a glance without re-running anything.

**Steps:**

1. Determine type (goal or app) and load the plan file to get the full list of steps.

2. Read all checkpoint files from `.vibeless/<type>/<name>/checkpoints/` and all deviation files from `.vibeless/<type>/<name>/deviations/`.

3. Display a progress table:

```
STATUS: <name>
─────────────────────────────────────────────
  Step 1  ✅  <short subject>   PASS
  Step 2  ✅  <short subject>   PASS
  Step 3  ⚠️  <short subject>   PARTIAL  ← deviation logged
  Step 4  🔄  <short subject>   IN PROGRESS
  Step 5  ⬜  <short subject>   NOT STARTED
─────────────────────────────────────────────
  Completed: 2/5   Deviations: 1   Blocked: 0
```

Legend: ✅ PASS  ⚠️ PARTIAL/deviation  ❌ FAIL  🔄 in progress  ⬜ not started

4. If any deviations exist, list them below the table with a one-line summary each and remind the user they can resolve them with `#amend <name>`.

---

## #amend \<name\>

**Purpose:** Formally update a plan (`VIBE.md` or `APP.md`) when mid-execution discoveries require a course correction. Never rewrites existing content — only appends a versioned amendment block.

**Steps:**

1. Determine type and load the current plan file.

2. Ask the user what needs to change and why. One question at a time if the scope is unclear.

3. Append an amendment block to the bottom of `VIBE.md` or `APP.md`:
   ```markdown
   ---
   ## Amendment <N> — <short subject>
   **Date:** <ISO date>
   **Triggered by:** Deviation at Step <X> | User decision | New information
   **What changed:** Clear description of what in the plan is now different.
   **Original text:** Quote the original section or step being superseded.
   **Reason:** Why this change was necessary.
   ```
   `<N>` increments from any prior amendments. Never modify the original plan text above — the amendment block is the authoritative override.

4. If the amendment changes step ordering or adds/removes steps, also update `.vibeless/HANDOFF.md` to reflect the new step count so `#status` stays accurate.

5. Confirm to the user what was amended and tell them to run `#execute <name>` to continue from the current step.

---

## #checkpoint \<name\>

**Purpose:** Manually record a verified step outside of `#execute`, or re-verify a step that was skipped or failed earlier.

**Steps:**

1. Determine the next checkpoint number by counting files in `.vibeless/goal/<name>/checkpoints/` or `.vibeless/apps/<name>/checkpoints/`.

2. Ask the user (or determine from context): which step is being checkpointed?

3. Write the checkpoint file:
   ```
   .vibeless/<type>/<name>/checkpoints/<step_N>_<short_subject>.md
   ```

   Format:
   ```markdown
   ## Checkpoint: Step <N> — <short subject>

   **What was built:** ...
   **Happy path result:** ...
   **Failure/edge case tested:** ...
   **Result:** PASS | FAIL | PARTIAL
   **Deviations from plan:** none | <description>
   **Notes:** ...
   ```

4. If result is FAIL or PARTIAL, write a deviation note and surface it to the user before continuing.

---

## #doc \<name\>

**Purpose:** Run a documentation sweep after execution is complete (or at any point mid-execution). Ensures the work is survivable by a future session or collaborator.

**Steps:**

1. Determine type (goal or app) from directory structure.

2. **README check:** If a `README.md` does not exist at the project root, create one with: what the project is, how to run it, and how it is structured. If it exists, verify it still reflects what was built this session and update any stale sections.

3. **Decision notes:** For every key decision made during the interview or execution that is not already recorded, write a decision file:
   ```
   .vibeless/<type>/<name>/decisions/<NNN>_<short_subject>.md
   ```
   Format:
   ```markdown
   ## Decision: <short subject>
   **Context:** Why this decision came up.
   **Decision:** What was chosen.
   **Alternatives considered:** ...
   **Consequences:** What this means going forward.
   ```

4. **Plan completion record:** Append a dated completion block to the bottom of `VIBE.md` or `APP.md`:
   ```markdown
   ---
   ## Completion Record
   **Date:** <ISO date>
   **Status:** COMPLETE | PARTIAL
   **Steps completed:** N of M
   **Deviations:** none | list
   **What shipped:** one-line summary
   ```
   Never rewrite the plan itself — only append.

5. Report to the user: what was created or updated, and any gaps that still need attention.

---

## #compound \<name\>

**Purpose:** Close the loop after a goal or app is executed. Extract one reusable takeaway and propose what to do next.

**Steps:**

1. Review all session memory files, checkpoints, deviations, and decision notes for this goal or app.

2. Propose **exactly one** compounding improvement — choose the most valuable from:
   - A new rule or guardrail worth adding to `VIBE.md` or a shared conventions file
   - A reusable pattern or module extracted from what was built
   - A doc that captures a hard-won lesson from a deviation
   - A cleanup that removes a boundary violation or technical debt introduced during execution

3. Propose the **next goal or app** to create: the smallest logical next step that builds on what was just completed.

4. Write a compound note to:
   ```
   .vibeless/<type>/<name>/COMPOUND.md
   ```
   Format:
   ```markdown
   ## Compound: <name>
   **Date:** <ISO date>

   ### What Was Built
   One paragraph summary.

   ### What Was Learned
   Key lessons, especially from deviations or surprises.

   ### Compounding Improvement
   The one thing worth extracting or fixing now.

   ### Proposed Next Step
   The next goal or app to create, and why it is the right next move.
   ```

5. Ask the user if they want to act on the compounding improvement or create the next goal/app now.

---

## #orchestrate \<name\>

**Purpose:** Execute a plan using a supervisor/subagent model. The supervisor (a capable, expensive model — Sonnet, Opus, or Fable) handles all planning, decomposition, validation, and integration. Subagents (cheaper, faster models — Haiku, Qwen, or similar) execute individual atomic tasks in parallel. Token cost is reduced because expensive model time is spent only on coordination, not raw execution.

---

### Step 1 — Supervisor Setup

1. Load the plan file (`VIBE.md` or `APP.md`) and all session memory files for this goal or app.

2. Ask the user which model to use as supervisor if not already set. Recommended: Sonnet for most work; Opus or Fable for plans requiring deep reasoning or complex integration. Record the choice in `.vibeless/<type>/<name>/ORCHESTRATION.md`.

3. Ask which model to use for subagents. Recommended: Haiku for fast atomic tasks; Qwen or similar for code-heavy subtasks. Record in `ORCHESTRATION.md`.

4. Write `.vibeless/<type>/<name>/ORCHESTRATION.md`:

```markdown
# Orchestration Config: <name>

**Supervisor model:** <model>
**Subagent model:** <model>
**Date started:** <ISO date>

## Batch Log
(filled in as batches execute)
```

---

### Step 2 — Task Decomposition (Supervisor only)

The supervisor reads the full plan and produces a **dependency-aware decomposition** before any subagent is spawned.

1. Identify which plan steps have dependencies on prior steps and which are independent of each other.

2. Group steps into **sequential batches**. Within each batch, all steps are independent and can run in parallel. Across batches, order is preserved.

   Example decomposition for a 6-step plan:
   ```
   Batch 1 (parallel): Step 1, Step 2          ← no dependencies
   Batch 2 (parallel): Step 3, Step 4          ← depend on batch 1
   Batch 3 (sequential): Step 5, Step 6        ← step 6 depends on step 5
   ```

3. Write the decomposition to `ORCHESTRATION.md` under a `## Task Decomposition` section.

4. **File ownership map:** For each task in each batch, list which files the subagent is permitted to create or modify. No two subagents in the same batch may own the same file. If two steps would touch the same file, they must be in different batches, not the same one. Add the ownership map to `ORCHESTRATION.md`.

---

### Step 3 — Subagent Brief Writing (Supervisor only)

Before spawning any subagent, the supervisor writes a self-contained brief for every task in the current batch. Subagents read only their brief — never the full plan.

Write each brief to:
```
.vibeless/<type>/<name>/subagents/batch_<N>/task_<M>_brief.md
```

Brief format:
```markdown
# Subagent Brief: Batch <N> / Task <M>

## Context (read this first)
One paragraph: what the overall goal is, where this task fits, and what was already completed in prior batches.

## Your Task
Exactly what you must build or produce. Be specific enough that no clarifying questions are needed.

## Inputs
Files or data you are allowed to read. List paths explicitly.

## Outputs
Files you must create or modify. These are the only files you may touch.
**You do not own any file not listed here. Do not read or write outside this list.**

## Done Looks Like
The concrete, observable result that marks this task complete.

## Failure Handling
What to do if you hit an error, ambiguity, or an unexpected state. Do not improvise — write your findings to your output file and mark the task BLOCKED.

## Model
<subagent model name>
```

---

### Step 4 — Parallel Batch Execution

For each batch, in order:

1. **Spawn subagents in parallel** — one per task in the batch. Each subagent receives only its brief. Run all tasks in the batch simultaneously; do not wait for one before starting another.

2. Each subagent writes its result to:
   ```
   .vibeless/<type>/<name>/subagents/batch_<N>/task_<M>_output.md
   ```

   Output format the subagent must follow:
   ```markdown
   # Subagent Output: Batch <N> / Task <M>

   **Status:** COMPLETE | BLOCKED | FAILED
   **Model used:** <model>

   ## What Was Done
   Description of what was built or produced.

   ## Files Written
   List of files created or modified.

   ## Verification
   Happy path result and at least one failure/edge case tested.

   ## Blockers / Surprises
   Anything unexpected found. If BLOCKED or FAILED, explain here.
   ```

3. Wait for all tasks in the batch to complete before the supervisor proceeds to Step 5.

---

### Step 5 — Supervisor Validation (after each batch)

The supervisor reads all output files for the completed batch and for each task:

1. **Validate** — does the output match what the brief asked for? Does verification evidence show the happy path and a failure case?

2. **Integrate** — if multiple subagents produced complementary outputs (e.g., separate modules that must be wired together), the supervisor performs the integration step directly. Integration is supervisor work, not subagent work.

3. **Write a checkpoint** for each task using the standard checkpoint format under:
   ```
   .vibeless/<type>/<name>/checkpoints/batch_<N>_task_<M>_<short_subject>.md
   ```
   Include which model ran the task in the checkpoint's **Notes** field.

4. **On BLOCKED or FAILED output:** Stop the batch. Write a deviation note. Ask the user how to proceed before spawning the next batch. Options: re-brief the failing task with corrections, amend the plan with `#amend <name>`, or skip.

5. **On COMPLETE batch with no issues:** Append a batch summary to `ORCHESTRATION.md`:
   ```markdown
   ## Batch <N> — COMPLETE
   **Date:** <ISO date>
   **Tasks:** M
   **Supervisor actions:** list any integration or fixups done
   **Checkpoint files:** list paths
   ```
   Then move to the next batch.

---

### Step 6 — Completion

When all batches are done:

1. The supervisor writes a final summary to `ORCHESTRATION.md`:
   ```markdown
   ## Orchestration Complete
   **Date:** <ISO date>
   **Total batches:** N
   **Total tasks:** M
   **Supervisor model:** <model>
   **Subagent model:** <model>
   **Estimated token savings:** supervisor handled X steps; subagents handled Y steps
   ```

2. Prompt the user to run `#doc <name>` and then `#compound <name>`.

---

## #agents \<name\>

**Purpose:** Show the current subagent roster and status for an active or completed orchestration run.

**Steps:**

1. Check that `ORCHESTRATION.md` exists for the given name. If not, tell the user no orchestration has been run yet and suggest `#orchestrate <name>`.

2. Read all brief and output files under `.vibeless/<type>/<name>/subagents/`.

3. Display a status table:

```
AGENTS: <name>
Supervisor: <model>   Subagent model: <model>
──────────────────────────────────────────────────────
  Batch 1
    Task 1  ✅  <short subject>   COMPLETE   (Haiku)
    Task 2  ✅  <short subject>   COMPLETE   (Haiku)
  Batch 2
    Task 3  ⚠️  <short subject>   BLOCKED    (Haiku)  ← deviation logged
    Task 4  ⬜  <short subject>   NOT STARTED
──────────────────────────────────────────────────────
  Batches complete: 1/2   Tasks complete: 2/4   Blocked: 1
```

4. If any tasks are BLOCKED or FAILED, list the blocker reason from their output file and remind the user they can unblock with `#amend <name>`.

---

## #handoff \<name\>

**Purpose:** Persist the current session state so any future session — same or different AI model — can resume without losing context.

**Steps:**

1. Gather state: review all session memory files, checkpoints, deviations, and decision notes written this session.

2. Write (or overwrite) `.vibeless/HANDOFF.md` with the following structure:

```markdown
# Vibeless Handoff

_Last updated: <ISO date>_

## Active Context
- **Type:** goal | app
- **Name:** <name>
- **Plan file:** .vibeless/<type>/<name>/VIBE.md  OR  APP.md

## Session Summary
What happened this session — key decisions made, blockers hit, things learned.

## Current Status
What step execution is on, what is complete, what is next.

## Open Items
Anything unresolved that the next session must address before continuing.

## Checklist
- [ ] All completed steps have checkpoint files
- [ ] All deviations have deviation notes
- [ ] All key decisions have decision notes
- [ ] Doc sweep (#doc) completed or scheduled
- [ ] Compound review (#compound) completed or scheduled

## How to Resume
Exact command to run to pick this back up:
  #execute <name>
```

3. Confirm to the user that the handoff is saved at `.vibeless/HANDOFF.md`.

---

## #help

Re-display the help menu from the top of this skill.

---

## Conduct Rules (apply to all commands)

- **One question at a time.** Never present a bullet list of interview questions at once. Ask, wait for the answer, then ask the next.
- **Write before you forget.** Every interview answer that contains a useful fact gets written to a session memory file immediately — not batched at the end.
- **Never assume.** If a constraint, preference, or scope boundary is not stated explicitly, ask for it.
- **Verify every step.** No build step is complete without a demonstrated happy path and at least one failure or edge case. Claiming something works without showing it is not verification.
- **Stop on deviation.** If execution uncovers something that contradicts the plan, stop, write the deviation note, and ask the user how to proceed. Do not improvise silently.
- **Plans are executable.** `VIBE.md` and `APP.md` must be written so a brand-new AI model or developer — with zero prior context — can read them and execute correctly. Vague directions are a bug.
- **Handoff before closing.** If the session is ending with unfinished work, always run `#handoff` before signing off.
- **Supervisor owns integration.** Subagents build isolated pieces; the supervisor wires them together. Never ask a subagent to read another subagent's output — that is supervisor work.
- **File ownership is a hard boundary.** Two subagents in the same batch must never own the same file. If a conflict is discovered during decomposition, split the conflicting steps into separate batches. This is non-negotiable.
- **Briefs must be self-contained.** A subagent brief must be readable cold, with zero context from the chat session or the full plan. If the brief requires the reader to "see above" or "check the plan," rewrite it.
- **Expensive models supervise; cheap models execute.** Never assign complex reasoning, cross-step integration, or validation to a subagent. If a task requires judgment beyond executing clear instructions, it is supervisor work.
- **BLOCKED beats wrong.** Instruct subagents that if they are uncertain about anything in their brief, they must mark the task BLOCKED and explain — not guess and produce incorrect output that the supervisor then has to debug.
