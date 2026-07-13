# Knowledge System

> **This document has been superseded.**
>
> The static Knowledge Module architecture was replaced with the **Investigation Planner**.
>
> Please read [`investigation-planner.md`](investigation-planner.md) instead.

## Why It Changed

Static Knowledge Modules required writing code for every technology Wizard would ever need to understand. This created a hard ceiling: the system could only investigate repositories using technologies that had been manually coded into modules.

The Investigation Planner replaced this with a dynamic, LLM-powered approach. The Planner generates investigation plans for any repository, any technology, any era — including technologies that did not exist when Wizard was built.

The core architecture (Runtime Engine, two graphs, observations, claims, evidence, trust) remained unchanged. Only the planning component became dynamic.

See [`investigation-planner.md`](investigation-planner.md) for the complete design.
