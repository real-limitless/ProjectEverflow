# Vibeless

Initialized: 2026-06-25
Project: /projects/ProjectEverflow

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

## Commands
Run `/vibeless` in your AI session to see the full command menu.
