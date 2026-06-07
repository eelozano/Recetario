/**
 * UUID generation for new records.
 *
 * Uses the `uuid` package (v4, random). On React Native this needs the
 * `react-native-get-random-values` polyfill imported once at app startup — a
 * step-3/mobile concern, not the pure domain's.
 */
import { v4 as uuidv4 } from "uuid";

import type { Id } from "../identity";

export function newId(): Id {
  return uuidv4();
}
