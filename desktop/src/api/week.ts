/** Shared week-date helpers for the calendar and shopping views. */

/** Local YYYY-MM-DD (avoids the UTC shift of toISOString). */
export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

/** Monday of the week containing `d`. */
export function startOfWeek(d: Date): Date {
  const out = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dow = (out.getDay() + 6) % 7; // 0 = Monday
  out.setDate(out.getDate() - dow);
  return out;
}

export function addDays(d: Date, n: number): Date {
  const out = new Date(d);
  out.setDate(out.getDate() + n);
  return out;
}

/** Short "Jun 1 – Jun 7" label for the week starting at `weekStart`. */
export function weekRangeLabel(weekStart: Date): string {
  const end = addDays(weekStart, 6);
  const fmt: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${weekStart.toLocaleDateString(undefined, fmt)} – ${end.toLocaleDateString(
    undefined,
    fmt,
  )}`;
}
