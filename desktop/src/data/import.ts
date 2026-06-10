/**
 * Recipe import via the `recetario-helper` sidecar (Architecture v2, step 4).
 *
 * Import is the one feature that isn't pure TS: turning a URL/video/captured page
 * into a structured recipe leans on Python's `recipe-scrapers` + `yt-dlp`. The
 * helper runs as a **persistent** sidecar (`serve` mode): we spawn it once, keep
 * it warm, and exchange newline-delimited JSON over stdin/stdout. That amortizes
 * the (one-time) Python interpreter + recipe-scrapers import across the whole
 * session, so only the first import is slow — the rest are near-instant. The
 * helper never touches storage; we map its JSON onto the core `Recipe` shape and
 * persist it through the same `RecipeRepository` the rest of the app uses.
 *
 * Imported recipes arrive as DRAFT with blank macros: the user reviews them and
 * fills per-serving macros in the detail view, then finalizes.
 */
import { Decimal } from "decimal.js";
import { Command, type Child } from "@tauri-apps/plugin-shell";
import {
  normalizeIngredientName,
  RecipeStatus,
  SourceType,
  type Recipe,
  type RecipeIngredient,
} from "@recetario/core";

import { getRepos } from "./repos";

/** The sidecar's externalBin name — must match capabilities/default.json. */
const HELPER = "binaries/recetario-helper";
/** Generous ceiling; a slow page or video shouldn't hang the UI forever. */
const REQUEST_TIMEOUT_MS = 90_000;

/** JSON shape the helper returns under `recipe` (camelCase, see import_helper.py). */
interface DraftIngredient {
  name: string;
  quantity: string | null;
  unit: string | null;
  rawText: string | null;
  notes: string | null;
}
interface DraftPayload {
  title: string;
  description: string | null;
  servings: number | null;
  sourceUrl: string | null;
  sourceType: "web" | "video";
  instructionsMd: string | null;
  ingredients: DraftIngredient[];
  tags: string[];
}
interface HelperResponse {
  id: number;
  ok: boolean;
  recipe: DraftPayload | null;
  error?: string;
}

/**
 * Owns the long-lived helper process and the request/response correlation. The
 * process is spawned lazily on first use and respawned automatically if it dies;
 * it shuts itself down when the app quits (its stdin reaches EOF).
 */
class HelperConnection {
  private child: Child | null = null;
  private spawning: Promise<void> | null = null;
  private nextId = 1;
  private buffer = "";
  private readonly pending = new Map<
    number,
    { resolve: (p: DraftPayload | null) => void; reject: (e: Error) => void; timer: number }
  >();

  private async ensure(): Promise<void> {
    if (this.child) return;
    if (!this.spawning) this.spawning = this.spawn();
    await this.spawning;
  }

  private async spawn(): Promise<void> {
    const command = Command.sidecar(HELPER, ["serve"]);
    command.stdout.on("data", (chunk: string) => this.onStdout(chunk));
    command.stderr.on("data", (chunk: string) =>
      console.warn("[recetario-helper]", chunk),
    );
    command.on("close", () =>
      this.fail(new Error("The import helper stopped unexpectedly.")),
    );
    command.on("error", (e) => this.fail(new Error(String(e))));
    try {
      this.child = await command.spawn();
    } catch (e) {
      this.spawning = null;
      throw new Error(
        `Couldn't start the import helper (${e instanceof Error ? e.message : String(e)}).`,
      );
    }
  }

  /** Accumulate stdout and dispatch each complete JSON line. */
  private onStdout(chunk: string): void {
    this.buffer += chunk;
    let nl: number;
    while ((nl = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, nl).trim();
      this.buffer = this.buffer.slice(nl + 1);
      if (line) this.consume(line);
    }
    // Some transports deliver whole lines without a trailing newline; if what's
    // buffered already parses, consume it now rather than wait for more.
    const rest = this.buffer.trim();
    if (rest) {
      try {
        JSON.parse(rest);
        this.buffer = "";
        this.consume(rest);
      } catch {
        /* partial line — keep buffering */
      }
    }
  }

  private consume(line: string): void {
    let msg: HelperResponse;
    try {
      msg = JSON.parse(line) as HelperResponse;
    } catch {
      return; // not our protocol (e.g. a stray log line) — ignore
    }
    const entry = msg.id != null ? this.pending.get(msg.id) : undefined;
    if (!entry) return;
    this.pending.delete(msg.id);
    clearTimeout(entry.timer);
    if (msg.ok) entry.resolve(msg.recipe);
    else entry.reject(new Error(msg.error || "Import failed. Please try again."));
  }

  /** Tear down on process death: drop the handle and reject everything pending. */
  private fail(err: Error): void {
    this.child = null;
    this.spawning = null;
    this.buffer = "";
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timer);
      entry.reject(err);
    }
    this.pending.clear();
  }

  async request(command: string, params: Record<string, unknown>): Promise<DraftPayload | null> {
    await this.ensure();
    const id = this.nextId++;
    const line = `${JSON.stringify({ id, command, ...params })}\n`;
    return new Promise<DraftPayload | null>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("Import timed out. Please try again."));
      }, REQUEST_TIMEOUT_MS) as unknown as number;
      this.pending.set(id, { resolve, reject, timer });
      this.child!.write(line).catch((e) => {
        this.pending.delete(id);
        clearTimeout(timer);
        reject(
          new Error(
            `Couldn't reach the import helper (${e instanceof Error ? e.message : String(e)}).`,
          ),
        );
      });
    });
  }
}

const helper = new HelperConnection();

/** Parse a quantity string from the helper into a Decimal, or null. */
function parseQuantity(raw: string | null): Decimal | null {
  if (raw == null || !raw.trim()) return null;
  try {
    return new Decimal(raw);
  } catch {
    return null;
  }
}

function payloadToRecipe(payload: DraftPayload): Recipe {
  const ingredients: RecipeIngredient[] = payload.ingredients
    .filter((i) => i.name.trim())
    .map((i) => {
      const name = i.name.trim();
      return {
        ingredient: { name, normalizedName: normalizeIngredientName(name) },
        quantity: parseQuantity(i.quantity),
        unit: i.unit?.trim() || null,
        rawText: i.rawText?.trim() || null,
        notes: i.notes?.trim() || null,
      };
    });
  return {
    title: payload.title.trim() || "Untitled recipe",
    description: payload.description?.trim() || null,
    sourceUrl: payload.sourceUrl || null,
    sourceType: payload.sourceType === "video" ? SourceType.VIDEO : SourceType.WEB,
    // Imported data is unverified, so it lands as a draft for review/finalize.
    status: RecipeStatus.DRAFT,
    servings: payload.servings ?? null,
    instructionsMd: payload.instructionsMd?.trim() || null,
    ingredients,
    tags: payload.tags.map((name) => ({ name })),
  };
}

/** Persist a parsed draft and return the new recipe's id. */
async function saveDraft(payload: DraftPayload | null): Promise<string> {
  if (!payload) throw new Error("Import returned no recipe.");
  const { recipes } = await getRepos();
  const saved = await recipes.create(payloadToRecipe(payload));
  return saved.id!;
}

/**
 * Warm the import helper at app startup. The first spawn pays a one-time ~9s
 * PyInstaller extraction; doing it eagerly (rather than lazily on the first
 * import) keeps that cost off the first import — the way the old always-on
 * backend did. Best-effort: if it fails, the first import just spawns as usual.
 */
export async function warmUpImporter(): Promise<void> {
  try {
    await helper.request("ping", {});
  } catch {
    /* best-effort: the next import will spawn/retry on its own */
  }
}

/** Import a recipe from a video URL (captions). Resolves to the new recipe's id. */
export async function importFromVideo(url: string): Promise<string> {
  return saveDraft(await helper.request("from-video", { url }));
}

/**
 * Import from page HTML captured by the in-app browser (bot-protected pages).
 * The rendered HTML rides the stdin request directly — no temp file needed.
 */
export async function importFromHtml(html: string, url: string): Promise<string> {
  return saveDraft(await helper.request("from-html", { url, html }));
}
