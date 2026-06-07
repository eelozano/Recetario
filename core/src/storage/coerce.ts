/**
 * Best-effort coercion of loosely-typed YAML values (numbers, strings, objects)
 * into the shapes the domain expects. Every helper returns `undefined` (or a
 * documented default) rather than throwing, so a hand-edited file can't crash a
 * parse. Shared by all three serializers.
 */
import { Decimal } from "decimal.js";

export function asString(value: unknown): string | undefined {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return undefined;
}

export function asInt(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value);
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n)) return Math.trunc(n);
  }
  return undefined;
}

export function asDecimal(value: unknown): Decimal | undefined {
  if (value === null || value === undefined) return undefined;
  if (typeof value !== "number" && typeof value !== "string") return undefined;
  try {
    return new Decimal(String(value));
  } catch {
    return undefined;
  }
}

export function asBool(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** A Decimal as a plain number for YAML output (re-parsed exactly via `asDecimal`). */
export function decimalToNumber(value: Decimal | null | undefined): number | undefined {
  if (value === null || value === undefined) return undefined;
  return Number(value.toString());
}
