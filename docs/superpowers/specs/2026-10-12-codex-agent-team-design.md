# Codex agent team integration

Date: 2026-10-12, America/Los_Angeles. Status: proposed design for review.

## Intended result

Perry can use a reusable specialist team inside Codex alongside different projects. A new idea, prompt, rubric, sponsor brief or judge conversation becomes an updated project brief and actionable tasks. Agents load Perry's taste and their own memory, work toward concrete acceptance conditions, revise within a bounded budget and save useful lessons.

The existing [agent-team kit](../../../agent-team/README.md) supplies the eight roles and seeded memories. Perry selected Codex as the first runtime. The first integration connects those existing definitions to Codex, with persistent context and a verified video-editing tool path. New product implementation and a finished real-world demo require their own project task and input assets.

## Available local support

Read-only inspection found Codex CLI `0.162.0-alpha.17.2`, with `multi_agent` enabled. There are currently no personal `.toml` agent files and no installed personal agent-team directory. Python, Node, FFmpeg and FFprobe are available on PATH. Availability is not yet proof of manifest discovery, memory persistence or a successful video render.

The [official Codex documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents) describes personal agents under `~/.codex/agents/` and project agents under `.codex/agents/`. A standalone manifest defines `name`, `description` and `developer_instructions`. Omitted model settings inherit the session configuration. Validate the actual installed runtime rather than assuming an already-running chat reloads new manifests.

## Installation approaches

| Approach | Benefit | Tradeoff |
| --- | --- | --- |
| Personal Codex agents with shared personal memories — recommended | Reusable across projects; one current taste and role-memory collection | Memory writes need access to the personal data directory |
| Project-scoped agents and memories | Self-contained in a repository | Preferences and lessons can diverge between project copies |
| A packaged Codex plugin | Distributable and versioned | Additional packaging and lifecycle work for this initial personal setup |

Select personal agents for this version. Keep the repository kit as source/seed material; the installed personal memory becomes the active durable record. Project-specific state stays in the active project's directory.

## Storage and ownership

Resolve `CODEX_HOME` from the running environment, falling back to the user's `.codex` directory. Do not hardcode the hackathon path into active agent instructions.

| Location | Content | Owner |
| --- | --- | --- |
| `CODEX_HOME/agents/perry_*.toml` | Eight custom-agent manifests | Installer |
| `CODEX_HOME/agent-team/` | Role definitions, workflow, policy, templates and quickstart | Installer; updates from the source kit |
| `CODEX_HOME/agent-team/TASTE.md` | Confirmed shared preferences | Coordinator, from Perry's feedback |
| `CODEX_HOME/agent-team/agents/<role>/MEMORY.md` | Durable role lessons and corrections | That role |
| `<project-root>/.agent-team/projects/<project-id>/` | Brief, criteria, sources, judge notes, task logs and artifacts | Coordinator and assigned task owners |

Use an explicit project root when provided, otherwise the current Git root, otherwise the working directory. Create a new project ID for a new event or independent idea. Every task receives its exact project/brief path and revision; agents do not infer an active project from an unrelated conversation.

Keep the B@B retrospective in the source repository as trial evidence. The installer does not turn its deadlines or sponsor rules into generic settings. Historical source links remain identified as historical and may require access to that repository.

## Registered roles and context loading

Register `perry_coordinator`, `perry_product_strategist`, `perry_integration_researcher`, `perry_builder`, `perry_experience_designer`, `perry_reviewer`, `perry_demo_editor` and `perry_deployment_engineer`.

Each manifest contains a narrow description and bootstrap instructions with resolved absolute paths. Its first task is to read its ROLE.md, MEMORY.md, shared TASTE.md, WORKFLOW.md and MEMORY_POLICY.md, then the current project brief and task. Load relevant source/evidence on demand. Carry task scope and outputs in the handoff.

Keep the user's model, reasoning effort, permission policy and runtime concurrency limit. This installation does not change account settings, sandbox policy, credentials, MCP connections or unrelated project instructions. Use only necessary roles. When the active tool surface cannot select a registered custom role, explicitly load the matching role instructions in a supported agent session and label that fallback; do not claim the manifest was used.

The coordinator is the human-facing entry point. A quickstart prompt activates the team explicitly, so unrelated Codex work does not automatically start eight specialists. Once active, the coordinator turns rough requests into task contracts and routes supported specialist work within the user's authorization and runtime rules.

## Revision and feedback behavior

Reuse the documented loop: initial attempt plus two revisions by default, or a task-specific explicit budget. Acceptance requires evidence suited to the artifact. Persist attempt number, actual check result, change and next action in the project task file so an interrupted session can resume.

Exit when the task passes, reaches its budget, lacks an essential input/tool, or makes no progress on two consecutive attempts. Report unmet conditions and the next useful action. These are instructed, auditable agent loops in Codex; deterministic scheduling and background execution are outside this first adapter.

New judge feedback records its source and confidence, updates the brief revision, and invalidates only affected tasks/evidence. Mandatory published rules remain distinct from informal advice. Perry continues to steer product choices and script revisions.

## Memory behavior

Seed personal taste and role memory only when they do not exist. Reinstalling updated instructions must preserve accumulated memories. Inspect existing destination files before replacement; conflicting files owned by another setup are surfaced rather than overwritten.

Agents read memory at task start and save small, sourced, deduplicated updates after verified outcomes or explicit feedback. The source kit remains the initial snapshot; personal memory is canonical after installation. Provide an explicit export path for backups or later migration instead of silently maintaining two mutable copies.

A restricted session may read personal files but lack permission to write them. Verify write access at startup. If blocked, return a proposed memory delta and the exact destination rather than claiming it was saved. Document how a session can grant access to this specific directory through its normal permission controls; do not broaden permissions automatically. The current setup task has filesystem access, but future sessions may differ.

## Demo editor integration

Use the existing demo-editor role and VIDEO_BRIEF template. Brainstorm the story and script with Perry, plan real-setting shots Perry films, inventory supplied media, produce explanatory graphics, edit and inspect the final export against this project's limits.

FFmpeg and FFprobe provide the initial local assembly/inspection path. Use suitable available graphic tools for overlays and diagrams; image generation is conditional on an available tool and a relevant asset need. Do not require a paid video service for the initial adapter.

Verification uses a clearly labeled synthetic clip and graphic to prove the local rendering path. It is a tool smoke test, not a product demonstration. Actual real-world footage, narration/music preferences and a selected story have not been supplied. In their absence the editor can deliver pre-production artifacts, with production gaps stated explicitly.

## Installation and recovery boundaries

Provide a repeatable installer with a dry run listing destination files and collisions. Install the role definitions and manifests together, validate paths and TOML, and retain enough ownership information to distinguish this installation from unrelated files. Preserve existing memories on all normal updates. Report partial installation precisely if a step fails, along with safe rerun/recovery instructions.

No global AGENTS.md or config.toml changes are required for the selected approach unless runtime verification establishes a missing setting. Any necessary adjustment is proposed with its exact scope. Do not restart or disturb unrelated chats to test loading; use a fresh small session.

## Acceptance evidence

1. Eight manifest files parse and contain the documented required fields; all referenced role/context files exist.
2. A fresh Codex session discovers at least one installed custom role and performs a minimal scoped task with its designated context. File presence alone is insufficient.
3. A controlled new-project brief with different timing and requirements produces project-local tasks without importing B@B rules.
4. A small test memory update is saved and read in a fresh task; reinstallation preserves the update. Keep test data separate from confirmed user preferences.
5. A controlled task logs attempts and exits with an explicit unmet check at its revision limit. An independent review or accurately labeled self-review reports the evidence.
6. A synthetic video with an explanatory overlay exports successfully and FFprobe reports its duration and stream properties. Inspect representative frames; the final video editor remains awaiting real project assets.
7. The quickstart documents activation, project-state location, memory ownership, session permission limits, update behavior and known execution gaps.

## Design self-review

The design preserves the user's adaptable-event requirement and separates taste, role memory and project state. It defines ownership, bootstrap loading, update behavior, tool limits and acceptance evidence. Personal memory writes and custom-agent discovery are explicit runtime checks. There are no chosen model replacements, automatic paid-service integrations, or promised finished videos without assets.

## Review and next stage

Review this written design before creating the implementation plan. Implementation will use the eight existing roles, with Codex as the selected runtime. No runtime files have been installed during this design step.
