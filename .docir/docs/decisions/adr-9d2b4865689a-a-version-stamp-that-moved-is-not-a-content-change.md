---
code:
- src/docir/modules/agents/**
- src/docir/entry_points/cli/rendering.py
created: '2026-08-17'
description: Why docir agent update reports 'unchanged' when a release moved only
  the version stamp, and why the file is rewritten anyway.
id: adr-9d2b4865689a
owner: maintainer
related:
- adr-3a2d5ee7bc84
- adr-31aa7aa60d11
- adr-6ed847e02fe5
status: accepted
tags:
- agents
- cli
title: A version stamp that moved is not a content change
type: decision
updated: '2026-08-17'
---

## Context

`docir self upgrade` from 0.14.0 to 0.16.0 reported both installed skill files as
`updated  v0.14.0 → v0.16.0`. Neither template had changed: every commit touching
`modules/agents/infra/templates/` in that range landed in 0.14.0, and the two
releases after it shipped none. The line described the version stamp, which moves
on every release whether or not the content did, and read as "your skill changed"
after an upgrade that changed nothing an agent will ever see.

A byte comparison cannot tell the two apart. The stamp is written *into* the
rendered file, so `existing == rendered` is false for every upgrade by
construction — the check that looks like it would catch this always says the file
moved.

## Decision

**Compare the rendered file against the existing one with the stamp blanked out,
and report `unchanged` when that is the only difference.** `differs_only_by_stamp`
is what separates "this file now says v0.16.0" from "this file says something
new"; `InstallAction` gains `unchanged` beside `created`/`updated`/`skipped`, and
the `v… → v…` arrow already fired only on `updated`, so the misleading line
disappears without a second output format.

## The file is still written

The stamp is the only state this module persists — `parse_version` reads it back
to report the transition — so skipping the write when nothing moved would leave
`update` reporting the same v0.14.0 → v0.16.0 on every run forever. What changes
is the claim made about the write, not whether it happens.

## One grammar for the stamp

The stamp expression now spans the whole HTML comment rather than just its
opening, so reading the stamp and excluding it from a comparison share one
pattern. Two expressions here would let a stamp be parseable by one and invisible
to the other, which is this document's own bug one level down.

## Consequences

`unchanged` is a new value on the module's public contract, so a consumer
switching on the action has a fourth case.

A hand-edited skill file reports `updated` on the next run. That is correct — the
file did change and was overwritten — but it does not distinguish "docir shipped
a change" from "somebody edited this". Telling those apart needs the template the
previous stamp rendered, which docir does not keep, and the file is regenerated
either way.
