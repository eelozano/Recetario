/**
 * Node implementation of the FileSystem port.
 *
 * NOT part of the pure core barrel (`src/index.ts`) — importing `node:fs` would
 * break the React-Native target. It's exported via the `@recetario/core/node`
 * subpath for Node consumers: the vitest storage tests and a future migration
 * CLI. The desktop shell uses a Tauri adapter instead.
 */
import { constants } from "node:fs";
import * as fs from "node:fs/promises";

import type { FileSystem } from "../fs";

export class NodeFileSystem implements FileSystem {
  readTextFile(path: string): Promise<string> {
    return fs.readFile(path, "utf8");
  }

  writeTextFile(path: string, content: string): Promise<void> {
    return fs.writeFile(path, content, "utf8");
  }

  async readDir(dir: string): Promise<string[]> {
    return fs.readdir(dir);
  }

  async mkdir(dir: string): Promise<void> {
    await fs.mkdir(dir, { recursive: true });
  }

  rename(from: string, to: string): Promise<void> {
    return fs.rename(from, to);
  }

  async remove(path: string): Promise<void> {
    await fs.rm(path, { force: true });
  }

  async exists(path: string): Promise<boolean> {
    try {
      await fs.access(path, constants.F_OK);
      return true;
    } catch {
      return false;
    }
  }
}
