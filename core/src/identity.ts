/**
 * Entity identity for Architecture v2.
 *
 * Identity is a **UUID string**, not an auto-increment integer. Auto-increment
 * ids can't survive folder-sync across machines (two devices would mint the same
 * next id for different records), so every cross-reference in the flat-file store
 * is a UUID. See docs/architecture-v2-proposal.md §4.
 *
 * `Id` is a plain string alias (not branded) — deliberately lightweight so plain
 * string literals work in tests and serialized YAML/frontmatter maps cleanly.
 *
 * Note: `usdaFdcId` is **not** one of these — it's an external USDA FoodData
 * Central identifier (an integer owned by USDA), so it stays `number`.
 */
export type Id = string;
