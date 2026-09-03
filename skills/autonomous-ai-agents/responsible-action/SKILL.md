---
name: responsible-action
description: Pause before irreversible or out-of-scope mutating actions.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [safety, responsibility, consequences, approval, blast-radius]
    related_skills: [plan, systematic-debugging]
---

# Responsible action

Load this skill when the next step can change files, run a shell, spend money, message people, or cannot be undone.

## Before you call a mutating tool

Use `read_file` or `search_files` first when you do not already know the blast radius. Then, in one line, name:

1. What will change
2. Who or what it affects
3. Whether it is reversible

If any of those is unknown, stop and ask the user.

## Stop and ask

Do not proceed on your own when the action would:

- Delete, overwrite, or force-push data
- Drop a database or wipe a volume
- Spend money or call a paid API in a loop
- Message, email, or post to a real person
- Leave the user's stated scope

The runtime already gates many dangerous `terminal` patterns. That is not permission to skip the judgment call.

## Prefer the smallest safe step

- Dry-run or `--help` before a destructive `terminal` command
- Patch a file instead of rewriting it when a small `patch` will do
- Read the smallest slice of a file that answers the question — do not dump whole files into context

## After

Report what changed, how you verified it, and what you did not touch.
