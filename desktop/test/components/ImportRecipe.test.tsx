/**
 * Example component test (#73): the import box's browser-first states.
 *
 * This is the copy-paste pattern for the rest of the UI suite — render a
 * component, drive it with user-event, and assert on the DOM, with the two
 * Tauri seams stubbed so nothing touches the real native layer:
 *   - `@tauri-apps/api` (invoke + event.listen) — the in-app capture browser
 *   - `../data/import`  — the recetario-helper sidecar
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ImportRecipe } from "../../src/components/ImportRecipe";
import { invoke } from "@tauri-apps/api/core";
import { importFromVideo } from "../../src/data/import";

// The capture browser: open_recipe_capture is a Rust command (invoke), and the
// captured HTML rides back on a "recipe-html-captured" event we subscribe to.
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(() => Promise.resolve(() => {})),
}));

// The import sidecar seam — both paths the box can take.
vi.mock("../../src/data/import", () => ({
  importFromVideo: vi.fn(),
  importFromHtml: vi.fn(),
}));

const invokeMock = vi.mocked(invoke);
const importFromVideoMock = vi.mocked(importFromVideo);

beforeEach(() => {
  vi.clearAllMocks();
});

/** A promise plus its resolver/rejecter, to hold the import in its busy state. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("ImportRecipe", () => {
  it("starts idle: the submit button reads 'Open in browser' and is disabled with no URL", () => {
    render(<ImportRecipe onImported={vi.fn()} />);

    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("Open in browser");
    expect(button).toBeDisabled();
    expect(
      screen.getByText(/Opens the page in an in-app browser/i),
    ).toBeInTheDocument();
  });

  it("a web URL opens the in-app capture browser rather than importing directly", async () => {
    const user = userEvent.setup();
    render(<ImportRecipe onImported={vi.fn()} />);

    await user.type(screen.getByLabelText(/Import from URL/i), "https://example.com/cake");

    const button = screen.getByRole("button", { name: "Open in browser" });
    expect(button).toBeEnabled();
    await user.click(button);

    expect(invokeMock).toHaveBeenCalledWith("open_recipe_capture", {
      url: "https://example.com/cake",
    });
    expect(importFromVideoMock).not.toHaveBeenCalled();
    expect(
      await screen.findByText(/Opened in a browser window/i),
    ).toBeInTheDocument();
  });

  it("a video URL switches the button to 'Import' and routes to the caption importer", async () => {
    const user = userEvent.setup();
    const onImported = vi.fn();
    importFromVideoMock.mockResolvedValue("recipe-42");
    render(<ImportRecipe onImported={onImported} />);

    const input = screen.getByLabelText(/Import from URL/i);
    await user.type(input, "https://youtube.com/watch?v=abc");

    const button = screen.getByRole("button", { name: "Import" });
    await user.click(button);

    await waitFor(() => expect(onImported).toHaveBeenCalledWith("recipe-42"));
    expect(importFromVideoMock).toHaveBeenCalledWith("https://youtube.com/watch?v=abc");
    expect(invokeMock).not.toHaveBeenCalled();
    // The box clears itself for the next import.
    expect(input).toHaveValue("");
  });

  it("shows the busy state while an import is in flight", async () => {
    const user = userEvent.setup();
    const pending = deferred<string>();
    importFromVideoMock.mockReturnValue(pending.promise);
    render(<ImportRecipe onImported={vi.fn()} />);

    const input = screen.getByLabelText(/Import from URL/i);
    await user.type(input, "https://youtu.be/abc");
    await user.click(screen.getByRole("button", { name: "Import" }));

    // Mid-flight: button reads "Importing…", input is locked.
    const button = await screen.findByRole("button", { name: "Importing…" });
    expect(button).toBeDisabled();
    expect(input).toBeDisabled();
    expect(screen.getByText(/Reading the recipe/i)).toBeInTheDocument();

    pending.resolve("recipe-1");
    await waitFor(() => expect(input).toBeEnabled());
  });

  it("surfaces the import error and does not report success", async () => {
    const user = userEvent.setup();
    const onImported = vi.fn();
    importFromVideoMock.mockRejectedValue(new Error("captions unavailable"));
    render(<ImportRecipe onImported={onImported} />);

    await user.type(screen.getByLabelText(/Import from URL/i), "https://youtu.be/abc");
    await user.click(screen.getByRole("button", { name: "Import" }));

    expect(await screen.findByText("captions unavailable")).toBeInTheDocument();
    expect(onImported).not.toHaveBeenCalled();
  });
});
