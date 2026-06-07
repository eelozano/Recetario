/**
 * The filesystem port.
 *
 * The pure core never imports `node:fs` (it must stay React-Native-safe), so all
 * I/O goes through this small async interface. Concrete adapters live outside the
 * pure bundle: a Node adapter (`adapters/node-fs.ts`) for tests and a future
 * migration CLI, and a Tauri adapter in the desktop shell (step 3).
 *
 * Paths are joined with "/" (`joinPath`) — accepted on every platform by both
 * Node's `fs` and the Tauri fs plugin — so the core never touches `node:path`.
 */
export interface FileSystem {
  /** Read a UTF-8 text file. Rejects if it does not exist. */
  readTextFile(path: string): Promise<string>;
  /** Write a UTF-8 text file, overwriting if present. */
  writeTextFile(path: string, content: string): Promise<void>;
  /** Entry names (files and dirs) directly under `dir`. */
  readDir(dir: string): Promise<string[]>;
  /** Create a directory and any missing parents (no error if it exists). */
  mkdir(dir: string): Promise<void>;
  /** Rename/move, replacing the destination if it exists (atomic on one volume). */
  rename(from: string, to: string): Promise<void>;
  /** Remove a file (no error if it is already gone). */
  remove(path: string): Promise<void>;
  /** Whether a path exists. */
  exists(path: string): Promise<boolean>;
}

/** Join path segments with "/", collapsing duplicate and trailing slashes. */
export function joinPath(...segments: string[]): string {
  return segments
    .filter((s) => s.length > 0)
    .map((s, i) => (i === 0 ? s.replace(/\/+$/, "") : s.replace(/^\/+|\/+$/g, "")))
    .filter((s) => s.length > 0)
    .join("/");
}

/** The directory portion of a "/"-joined path (everything before the last "/"). */
export function dirOf(path: string): string {
  const i = path.lastIndexOf("/");
  return i <= 0 ? "" : path.slice(0, i);
}

/**
 * Write a file atomically: write a sibling `*.tmp` then rename it over the target.
 * A crash mid-write leaves the old file intact (or no file), never a half-written
 * one — important for a folder that a sync client is watching. Ensures the parent
 * directory exists first.
 */
export async function atomicWrite(
  fs: FileSystem,
  path: string,
  content: string,
): Promise<void> {
  const dir = dirOf(path);
  if (dir) {
    await fs.mkdir(dir);
  }
  const tmp = `${path}.tmp`;
  await fs.writeTextFile(tmp, content);
  await fs.rename(tmp, path);
}
