/**
 * Tauri implementation of the core's `FileSystem` port (Architecture v2, step 3).
 *
 * The pure core never imports `node:fs` (it must stay React-Native-safe), so the
 * desktop shell injects this adapter, backed by `@tauri-apps/plugin-fs`. Access is
 * scoped to the data dir by `src-tauri/capabilities/default.json`. Paths are the
 * absolute "/"-joined strings the core produces; we pass them straight through.
 *
 * Tolerances are matched to the Node adapter so the same repositories behave
 * identically here and under vitest: `mkdir` is recursive and a no-op if the dir
 * exists; `remove` ignores an already-absent path. `rename` replaces the
 * destination (atomic on one volume on macOS — Windows is revisited later).
 */
import {
  exists,
  mkdir,
  readDir,
  readTextFile,
  remove,
  rename,
  writeTextFile,
} from "@tauri-apps/plugin-fs";
import type { FileSystem } from "@recetario/core";

export class TauriFileSystem implements FileSystem {
  readTextFile(path: string): Promise<string> {
    return readTextFile(path);
  }

  writeTextFile(path: string, content: string): Promise<void> {
    return writeTextFile(path, content);
  }

  async readDir(dir: string): Promise<string[]> {
    const entries = await readDir(dir);
    return entries.map((e) => e.name);
  }

  async mkdir(dir: string): Promise<void> {
    try {
      await mkdir(dir, { recursive: true });
    } catch (err) {
      // Some platforms surface "already exists" even with recursive; tolerate it
      // to match Node's recursive mkdir, but rethrow anything that left no dir.
      if (!(await exists(dir))) throw err;
    }
  }

  rename(from: string, to: string): Promise<void> {
    return rename(from, to);
  }

  async remove(path: string): Promise<void> {
    try {
      await remove(path);
    } catch (err) {
      if (await exists(path)) throw err;
    }
  }

  exists(path: string): Promise<boolean> {
    return exists(path);
  }
}
