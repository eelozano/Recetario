# @recetario/core

The **portable domain core** for Recetario — Architecture v2 (Path B). See
`../docs/architecture-v2-proposal.md` for the why.

This package is pure: **no network, no filesystem, no framework, no Node-only
APIs**. It holds the entities, value objects, and domain services (macro math,
shopping aggregation, meal-plan rollups). The desktop shell consumes it today; a
future React Native app reuses it unchanged (Q4 in the proposal). Anything that
touches the OS (file storage, the Python ingestion helper) lives *outside* this
package, behind small platform ports added in later steps.

These services are a faithful TypeScript port of the original Python domain
(`backend/src/recetario/domain/`). The Python unit tests are the spec; the vitest
suites here mirror them case-for-case. `Decimal` arithmetic uses
[`decimal.js`](https://mikemcl.github.io/decimal.js/) so the numbers match the
Python `decimal.Decimal` results exactly (no float drift).

```bash
npm test --workspace @recetario/core        # vitest
npm run typecheck --workspace @recetario/core
```
