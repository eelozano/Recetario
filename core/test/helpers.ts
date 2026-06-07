import type { MacroProfile } from "../src/index";

/**
 * A MacroProfile's amounts as `{ key: decimalString }`. Mirrors comparing the
 * Python `profile.amounts` dict, but with Decimals rendered to strings so
 * `toEqual` works on plain values (Decimal instances aren't value-equal).
 */
export function plain(profile: MacroProfile): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(profile.amounts)) {
    out[key] = value.toString();
  }
  return out;
}
