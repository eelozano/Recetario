/**
 * Shopping-list serialization: one file per list,
 * `shopping-lists/shopping-{uuid}.yaml`. Best-effort read; an item without an
 * ingredient name is skipped.
 */
import { type ShoppingList, type ShoppingListItem } from "../entities/shopping";
import { asBool, asDecimal, asRecord, asString, decimalToNumber } from "./coerce";
import { dumpYaml, loadYaml } from "./yaml";

function itemToData(item: ShoppingListItem): Record<string, unknown> {
  const out: Record<string, unknown> = { ingredient_name: item.ingredientName };
  if (item.unit) out.unit = item.unit;
  const total = decimalToNumber(item.totalQuantity);
  if (total !== undefined) out.total_quantity = total;
  if (item.checked) out.checked = true; // default false → omit
  if (item.ingredientId) out.ingredient_id = item.ingredientId;
  if (item.sourceEventIds && item.sourceEventIds.length > 0) {
    out.source_event_ids = item.sourceEventIds;
  }
  return out;
}

function itemFromData(value: unknown): ShoppingListItem | null {
  const row = asRecord(value);
  const ingredientName = asString(row.ingredient_name);
  if (ingredientName === undefined || ingredientName.trim() === "") return null;

  const item: ShoppingListItem = { ingredientName };
  const unit = asString(row.unit);
  if (unit !== undefined) item.unit = unit;
  const total = asDecimal(row.total_quantity);
  if (total !== undefined) item.totalQuantity = total;
  item.checked = asBool(row.checked) ?? false;
  const ingredientId = asString(row.ingredient_id);
  if (ingredientId !== undefined) item.ingredientId = ingredientId;
  if (Array.isArray(row.source_event_ids)) {
    const ids: string[] = [];
    for (const id of row.source_event_ids) {
      const s = asString(id);
      if (s !== undefined) ids.push(s);
    }
    item.sourceEventIds = ids;
  }
  return item;
}

export function shoppingListToYaml(list: ShoppingList): string {
  const data: Record<string, unknown> = {
    id: list.id,
    name: list.name,
    week_start: list.weekStart,
    week_end: list.weekEnd,
  };
  if (list.generatedAt) data.generated_at = list.generatedAt;
  if (list.createdAt) data.created_at = list.createdAt;
  if (list.updatedAt) data.updated_at = list.updatedAt;
  data.items = (list.items ?? []).map(itemToData);
  return dumpYaml(data);
}

export function shoppingListFromYaml(content: string): ShoppingList {
  let data: Record<string, unknown> = {};
  try {
    data = asRecord(loadYaml(content));
  } catch {
    data = {};
  }

  const list: ShoppingList = {
    name: asString(data.name) ?? "Shopping list",
    weekStart: asString(data.week_start) ?? "",
    weekEnd: asString(data.week_end) ?? "",
  };
  const id = asString(data.id);
  if (id !== undefined) list.id = id;
  const generatedAt = asString(data.generated_at);
  if (generatedAt !== undefined) list.generatedAt = generatedAt;
  const createdAt = asString(data.created_at);
  if (createdAt !== undefined) list.createdAt = createdAt;
  const updatedAt = asString(data.updated_at);
  if (updatedAt !== undefined) list.updatedAt = updatedAt;

  if (Array.isArray(data.items)) {
    const items: ShoppingListItem[] = [];
    for (const row of data.items) {
      const item = itemFromData(row);
      if (item) items.push(item);
    }
    list.items = items;
  } else {
    list.items = [];
  }
  return list;
}
