/**
 * Centralized YAML load/dump for the storage layer, pinned to `JSON_SCHEMA`.
 *
 * The default js-yaml schema is YAML 1.1, which auto-converts unquoted scalars
 * like `2026-06-03` into JS `Date`s and `yes`/`no` into booleans — surprising for
 * a hand-edited file. JSON_SCHEMA keeps those as plain strings, so a date a user
 * types stays a date string and best-effort parsing stays predictable.
 */
import yaml from "js-yaml";

export function loadYaml(content: string): unknown {
  return yaml.load(content, { schema: yaml.JSON_SCHEMA });
}

export function dumpYaml(data: unknown): string {
  return yaml.dump(data, { schema: yaml.JSON_SCHEMA, lineWidth: -1, sortKeys: false });
}
