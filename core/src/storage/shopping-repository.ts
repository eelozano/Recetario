/**
 * ShoppingListRepository — one YAML file per list in
 * `<baseDir>/shopping-lists/shopping-{uuid}.yaml`.
 *
 * The filename embeds the full UUID, so reads/deletes are direct (no scan). The
 * whole list is rewritten on any change (small file; keeps check-off state in
 * one place). Depends only on the FileSystem port.
 */
import type { Id } from "../identity";
import type { ShoppingList } from "../entities/shopping";
import { atomicWrite, type FileSystem, joinPath } from "./fs";
import { newId } from "./id";
import { shoppingListFromYaml, shoppingListToYaml } from "./shopping-serialization";

export const SHOPPING_DIR = "shopping-lists";

function fileName(id: Id): string {
  return `shopping-${id}.yaml`;
}

export class ShoppingListRepository {
  constructor(
    private readonly fs: FileSystem,
    private readonly baseDir: string,
  ) {}

  private dir(): string {
    return joinPath(this.baseDir, SHOPPING_DIR);
  }

  private path(id: Id): string {
    return joinPath(this.dir(), fileName(id));
  }

  async create(input: ShoppingList): Promise<ShoppingList> {
    const now = new Date().toISOString();
    const list: ShoppingList = {
      ...input,
      id: input.id ?? newId(),
      generatedAt: input.generatedAt ?? now,
      createdAt: input.createdAt ?? now,
      updatedAt: now,
    };
    await atomicWrite(this.fs, this.path(list.id!), shoppingListToYaml(list));
    return list;
  }

  async update(input: ShoppingList): Promise<ShoppingList> {
    if (!input.id) {
      throw new Error("ShoppingListRepository.update requires a list id");
    }
    const list: ShoppingList = { ...input, updatedAt: new Date().toISOString() };
    await atomicWrite(this.fs, this.path(list.id!), shoppingListToYaml(list));
    return list;
  }

  async getById(id: Id): Promise<ShoppingList | null> {
    const path = this.path(id);
    if (!(await this.fs.exists(path))) return null;
    try {
      return shoppingListFromYaml(await this.fs.readTextFile(path));
    } catch {
      return null;
    }
  }

  async list(): Promise<ShoppingList[]> {
    if (!(await this.fs.exists(this.dir()))) return [];
    const entries = await this.fs.readDir(this.dir());
    const out: ShoppingList[] = [];
    for (const name of entries) {
      if (!name.startsWith("shopping-") || !name.endsWith(".yaml")) continue;
      try {
        const list = shoppingListFromYaml(
          await this.fs.readTextFile(joinPath(this.dir(), name)),
        );
        if (list.id) out.push(list);
      } catch {
        // skip unreadable file
      }
    }
    return out;
  }

  async delete(id: Id): Promise<void> {
    await this.fs.remove(this.path(id));
  }
}
