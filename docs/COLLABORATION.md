# Working with Codex and Claude Code

Both tools work from the same Git repository. They share code, commits and project documents; chat history is not automatically shared.

## Start with a review

Install and sign into [Claude Code](https://code.claude.com/docs/en/quickstart), then open a terminal in the repository and run:

```sh
claude --worktree first-review
```

This starts Claude in a separate checkout and branch from the current committed state. Keep Codex in its own checkout. Claude's worktree is under `.claude/worktrees/`, which is excluded from Git. Each checkout needs its own `.venv`; follow the README setup commands there. Use a different local server port, such as 8766, if both tables are running.

Suggested first prompt:

> Read CLAUDE.md, README.md and docs/ARCHITECTURE.md. Review the first playable version, focusing on opponent-policy plausibility, information isolation and gameplay friction. Run the existing tests. Report the three most useful improvements with concrete evidence; do not edit code yet. Codex will review your findings with me.

For a later implementation task, specify the desired behaviour, relevant files and completion check. Let one tool implement the change and the other review the resulting commit or pull request. Swap those roles when useful.

## Small handoffs

At the end of a task, include:

- Branch and commit (or pull-request URL).
- What changed and why.
- Tests run and their results.
- Any remaining issue or product decision.

The next tool reads the actual diff before editing. Commit a completed change before transferring it between worktrees. Avoid simultaneous edits to the same checkout, even when the tools are discussing different tasks.

## Current baseline

The first version is a six-seat, 100 BB cash-style table with three heuristic opponent profiles, authoritative PokerKit settlement, filtered observations and chronological hand replay. The test command is:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The last implementation verification passed 17 tests, including 100 simulated hands. Recent history lives in server memory and disappears on restart. Long-term opponent memory, temporary moods and persistent history are possible future tasks, not implemented features.

`AGENTS.md` is the common instruction file; `CLAUDE.md` imports it using Claude Code's supported import syntax. Local private context and credentials are never part of a commit or handoff.

References: [Claude project instructions](https://code.claude.com/docs/en/memory), [Claude worktrees](https://code.claude.com/docs/en/common-workflows#run-parallel-sessions-with-worktrees), [Codex worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees).
