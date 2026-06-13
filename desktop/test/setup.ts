/**
 * Vitest setup for the desktop component/integration suite (#73).
 *
 * Registers jest-dom's matchers on Vitest's `expect`, and tears down the
 * rendered DOM after each test so cases stay isolated (we don't enable
 * globals, so auto-cleanup is wired here explicitly).
 */
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
