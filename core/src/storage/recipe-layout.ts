/**
 * On-disk layout for recipes: directory name and `{slug}-{short8}.md` filenames.
 *
 * The filename is cosmetic/human-friendly — the authoritative id is the UUID in
 * the file's frontmatter. The 8-char short id (the uuid's first block) keeps two
 * recipes with the same title from colliding and makes the file findable by id.
 */
import type { Id } from "../identity";

export const RECIPES_DIR = "recipes";

/** A filesystem-safe, readable slug from a title (ascii, lowercase, hyphenated). */
export function slug(title: string): string {
  const s = title
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "") // strip diacritics (combining marks)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return s || "recipe";
}

/** First 8 chars of the uuid (its first hyphen-delimited block), for the filename. */
export function short8(id: Id): string {
  return id.replace(/-/g, "").slice(0, 8) || id.slice(0, 8);
}

export function recipeFileName(title: string, id: Id): string {
  return `${slug(title)}-${short8(id)}.md`;
}

/** Suffix shared by every file for a given id, regardless of title/slug changes. */
export function recipeFileSuffix(id: Id): string {
  return `-${short8(id)}.md`;
}
