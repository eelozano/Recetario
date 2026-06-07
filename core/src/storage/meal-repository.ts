/**
 * MealEventRepository — meal events as monthly YAML files in
 * `<baseDir>/meal-calendar/meal-calendar-YYYY-MM.yaml`.
 *
 * The month is derived from each event's date, so an event lives in exactly one
 * file. Editing the date can move it between months; `update` removes the old
 * occurrence and re-inserts so there's never a duplicate. Depends only on the
 * FileSystem port.
 */
import type { Id } from "../identity";
import type { MealEvent } from "../entities/meal";
import { atomicWrite, type FileSystem, joinPath } from "./fs";
import { newId } from "./id";
import { eventsFromMonthFile, monthFileToString } from "./meal-serialization";

export const MEAL_DIR = "meal-calendar";

function monthOf(date: string): string {
  return date.slice(0, 7); // "YYYY-MM-DD" -> "YYYY-MM"
}

function monthFileName(month: string): string {
  return `meal-calendar-${month}.yaml`;
}

/** Inclusive list of "YYYY-MM" months spanning [startMonth, endMonth]. */
function monthsBetween(startMonth: string, endMonth: string): string[] {
  const [lo, hi] = startMonth <= endMonth ? [startMonth, endMonth] : [endMonth, startMonth];
  const months: string[] = [];
  let [year, month] = lo.split("-").map(Number) as [number, number];
  const [endYear, endM] = hi.split("-").map(Number) as [number, number];
  while (year < endYear || (year === endYear && month <= endM)) {
    months.push(`${year}-${String(month).padStart(2, "0")}`);
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return months;
}

export class MealEventRepository {
  constructor(
    private readonly fs: FileSystem,
    private readonly baseDir: string,
  ) {}

  private dir(): string {
    return joinPath(this.baseDir, MEAL_DIR);
  }

  async create(input: MealEvent): Promise<MealEvent> {
    const now = new Date().toISOString();
    const event: MealEvent = {
      ...input,
      id: input.id ?? newId(),
      createdAt: input.createdAt ?? now,
      updatedAt: now,
    };
    const month = monthOf(event.date);
    const events = await this.readMonth(month);
    events.push(event);
    await this.writeMonth(month, events);
    return event;
  }

  async update(input: MealEvent): Promise<MealEvent> {
    if (!input.id) {
      throw new Error("MealEventRepository.update requires an event id");
    }
    const event: MealEvent = { ...input, updatedAt: new Date().toISOString() };
    await this.removeById(event.id!);
    const month = monthOf(event.date);
    const events = await this.readMonth(month);
    events.push(event);
    await this.writeMonth(month, events);
    return event;
  }

  async delete(id: Id): Promise<void> {
    await this.removeById(id);
  }

  async getById(id: Id): Promise<MealEvent | null> {
    for (const month of await this.listMonths()) {
      const found = (await this.readMonth(month)).find((e) => e.id === id);
      if (found) return found;
    }
    return null;
  }

  /** Events whose date falls within [startDate, endDate] inclusive (ISO YYYY-MM-DD). */
  async listRange(startDate: string, endDate: string): Promise<MealEvent[]> {
    const [from, to] = startDate <= endDate ? [startDate, endDate] : [endDate, startDate];
    const out: MealEvent[] = [];
    for (const month of monthsBetween(monthOf(from), monthOf(to))) {
      for (const event of await this.readMonth(month)) {
        if (event.date >= from && event.date <= to) out.push(event);
      }
    }
    return out;
  }

  // --- internals ---

  private async removeById(id: Id): Promise<void> {
    for (const month of await this.listMonths()) {
      const events = await this.readMonth(month);
      const kept = events.filter((e) => e.id !== id);
      if (kept.length !== events.length) {
        await this.writeMonth(month, kept);
      }
    }
  }

  private async readMonth(month: string): Promise<MealEvent[]> {
    const path = joinPath(this.dir(), monthFileName(month));
    if (!(await this.fs.exists(path))) return [];
    try {
      return eventsFromMonthFile(await this.fs.readTextFile(path));
    } catch {
      return [];
    }
  }

  private async writeMonth(month: string, events: MealEvent[]): Promise<void> {
    const path = joinPath(this.dir(), monthFileName(month));
    if (events.length === 0) {
      await this.fs.remove(path); // don't leave an empty month file behind
      return;
    }
    await atomicWrite(this.fs, path, monthFileToString(month, events));
  }

  private async listMonths(): Promise<string[]> {
    if (!(await this.fs.exists(this.dir()))) return [];
    const entries = await this.fs.readDir(this.dir());
    return entries
      .filter((n) => n.startsWith("meal-calendar-") && n.endsWith(".yaml"))
      .map((n) => n.slice("meal-calendar-".length, -".yaml".length));
  }
}
