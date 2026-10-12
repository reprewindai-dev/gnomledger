# AGENTS.md — READ FIRST

Before any work, read [`00_VEKLOM_BIBLE.md`](./00_VEKLOM_BIBLE.md).

Project Genome Ledger is both a standalone product and a reusable Veklom evidence/provenance/lineage capability domain. Do not embed the standalone UI wholesale into Capability OS.

Repo-local source and tests govern Genome Ledger implementation details only when they do not conflict with current runtime evidence or the Bible. A hash chain is tamper-evident; do not claim physical immutability or external finality without verifying it.

Owner decision (2026-10-07): Coolify, Hetzner and Vercel are not part of Veklom; it runs on Docker Desktop (WSL2) on the owner's Windows host behind a Cloudflare tunnel (see `docs/docker-desktop-deploy.md`). Older guidance follows: use Coolify UI/API/MCP for Coolify management; SSH is for direct host/container verification or operations. Host port `8000` is Coolify-owned, while Gnomledger may legitimately listen on internal Docker port `8000` behind Traefik.
