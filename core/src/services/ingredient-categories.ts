/**
 * Grocery-aisle categories for shopping list items (#69).
 *
 * The canonical category set is deliberately small — one header per store
 * section, not a taxonomy. It must stay in sync with the import helper's
 * category enum (`backend/src/recetario/infrastructure/llm/recipe_extractor.py`),
 * which has Haiku classify ingredients at import time; this module is the
 * zero-cost fallback for everything that arrives without one (keyless imports,
 * hand-entered recipes, manual list items).
 *
 * `categorizeIngredient` matches on `normalizedName` (trim + lowercase, see
 * ../storage/normalize.ts): exact phrase first — so pantry staples like
 * "tomato paste" don't get dragged into Produce by the word "tomato" — then by
 * single word, scanning from the end because the head noun is usually last
 * ("boneless chicken thighs", "cheddar cheese"). Unknown names return null;
 * the UI buckets those under Other.
 */

export const SHOPPING_CATEGORIES = [
  "produce",
  "meat",
  "dairy",
  "pantry",
  "frozen",
  "other",
] as const;

export type ShoppingCategory = (typeof SHOPPING_CATEGORIES)[number];

/** Display labels, in store-walk order (the array order above). */
export const CATEGORY_LABELS: Record<ShoppingCategory, string> = {
  produce: "Produce",
  meat: "Meat & Seafood",
  dairy: "Dairy & Eggs",
  pantry: "Pantry",
  frozen: "Frozen",
  other: "Other",
};

/** Validate a category arriving from the LLM or a hand-edited file. */
export function asShoppingCategory(value: unknown): ShoppingCategory | null {
  return typeof value === "string" &&
    (SHOPPING_CATEGORIES as readonly string[]).includes(value)
    ? (value as ShoppingCategory)
    : null;
}

/** Multiword phrases checked before single words win ("tomato paste" ≠ tomato). */
const EXACT: Record<string, ShoppingCategory> = {
  "tomato paste": "pantry",
  "tomato sauce": "pantry",
  "crushed tomatoes": "pantry",
  "diced tomatoes": "pantry",
  "sun-dried tomatoes": "pantry",
  "coconut milk": "pantry",
  "coconut cream": "pantry",
  "evaporated milk": "pantry",
  "condensed milk": "pantry",
  "almond milk": "dairy",
  "oat milk": "dairy",
  "soy milk": "dairy",
  "peanut butter": "pantry",
  "almond butter": "pantry",
  "corn starch": "pantry",
  "corn syrup": "pantry",
  "corn tortillas": "pantry",
  "flour tortillas": "pantry",
  "garlic powder": "pantry",
  "onion powder": "pantry",
  "chili powder": "pantry",
  "dried oregano": "pantry",
  "dried basil": "pantry",
  "dried thyme": "pantry",
  "bay leaves": "pantry",
  "frozen peas": "frozen",
  "frozen corn": "frozen",
  "frozen spinach": "frozen",
  "ice cream": "frozen",
};

const WORD: Record<string, ShoppingCategory> = {
  // produce
  apple: "produce",
  apples: "produce",
  avocado: "produce",
  avocados: "produce",
  banana: "produce",
  bananas: "produce",
  basil: "produce",
  beet: "produce",
  beets: "produce",
  berries: "produce",
  blueberries: "produce",
  broccoli: "produce",
  cabbage: "produce",
  carrot: "produce",
  carrots: "produce",
  cauliflower: "produce",
  celery: "produce",
  chile: "produce",
  chiles: "produce",
  chili: "produce",
  chilies: "produce",
  cilantro: "produce",
  corn: "produce",
  cucumber: "produce",
  cucumbers: "produce",
  eggplant: "produce",
  garlic: "produce",
  ginger: "produce",
  grapes: "produce",
  jalapeno: "produce",
  jalapeño: "produce",
  jalapenos: "produce",
  kale: "produce",
  leek: "produce",
  leeks: "produce",
  lemon: "produce",
  lemons: "produce",
  lettuce: "produce",
  lime: "produce",
  limes: "produce",
  mango: "produce",
  mushroom: "produce",
  mushrooms: "produce",
  onion: "produce",
  onions: "produce",
  orange: "produce",
  oranges: "produce",
  parsley: "produce",
  pepper: "produce", // bell pepper; ground pepper is caught by "black pepper"-ish pantry words rarely listed bare
  peppers: "produce",
  potato: "produce",
  potatoes: "produce",
  scallion: "produce",
  scallions: "produce",
  shallot: "produce",
  shallots: "produce",
  spinach: "produce",
  strawberries: "produce",
  thyme: "produce",
  tomatillo: "produce",
  tomatillos: "produce",
  tomato: "produce",
  tomatoes: "produce",
  zucchini: "produce",
  // meat & seafood
  bacon: "meat",
  beef: "meat",
  brisket: "meat",
  chicken: "meat",
  chorizo: "meat",
  clams: "meat",
  cod: "meat",
  crab: "meat",
  duck: "meat",
  fish: "meat",
  ham: "meat",
  lamb: "meat",
  meat: "meat",
  meatballs: "meat",
  mussels: "meat",
  pancetta: "meat",
  pepperoni: "meat",
  pork: "meat",
  prosciutto: "meat",
  salami: "meat",
  salmon: "meat",
  sausage: "meat",
  sausages: "meat",
  shrimp: "meat",
  sirloin: "meat",
  steak: "meat",
  tilapia: "meat",
  tuna: "meat",
  turkey: "meat",
  veal: "meat",
  // dairy & eggs
  butter: "dairy",
  buttermilk: "dairy",
  cheddar: "dairy",
  cheese: "dairy",
  cream: "dairy",
  creme: "dairy",
  crema: "dairy",
  egg: "dairy",
  eggs: "dairy",
  feta: "dairy",
  ghee: "dairy",
  gouda: "dairy",
  margarine: "dairy",
  mascarpone: "dairy",
  milk: "dairy",
  mozzarella: "dairy",
  parmesan: "dairy",
  provolone: "dairy",
  queso: "dairy",
  ricotta: "dairy",
  yogurt: "dairy",
  // pantry
  baguette: "pantry",
  barley: "pantry",
  beans: "pantry",
  bread: "pantry",
  breadcrumbs: "pantry",
  broth: "pantry",
  buns: "pantry",
  capers: "pantry",
  cereal: "pantry",
  chickpeas: "pantry",
  chocolate: "pantry",
  cinnamon: "pantry",
  cocoa: "pantry",
  couscous: "pantry",
  cumin: "pantry",
  flour: "pantry",
  honey: "pantry",
  ketchup: "pantry",
  lentils: "pantry",
  mayonnaise: "pantry",
  mustard: "pantry",
  noodles: "pantry",
  nutmeg: "pantry",
  oats: "pantry",
  oil: "pantry",
  olives: "pantry",
  oregano: "pantry",
  paprika: "pantry",
  pasta: "pantry",
  quinoa: "pantry",
  rice: "pantry",
  salsa: "pantry",
  salt: "pantry",
  spaghetti: "pantry",
  stock: "pantry",
  sugar: "pantry",
  syrup: "pantry",
  tortillas: "pantry",
  vanilla: "pantry",
  vinegar: "pantry",
  walnuts: "pantry",
  almonds: "pantry",
  pecans: "pantry",
};

/**
 * Processed-form modifiers, checked between the exact phrases and the word
 * scan: "can of fire roasted tomatoes" is Pantry no matter what the head noun
 * says, and anything "frozen" belongs in Frozen.
 */
const FROZEN_RE = /\bfrozen\b/;
const PANTRY_MODIFIER_RE = /\b(canned|jarred|dried|cans? of|jars? of)\b/;

export function categorizeIngredient(
  normalizedName: string,
): ShoppingCategory | null {
  const name = normalizedName.trim().toLowerCase();
  if (!name) return null;
  const exact = EXACT[name];
  if (exact !== undefined) return exact;
  if (FROZEN_RE.test(name)) return "frozen";
  if (PANTRY_MODIFIER_RE.test(name)) return "pantry";
  const words = name.split(/[^a-zà-ÿ]+/).filter(Boolean);
  for (let i = words.length - 1; i >= 0; i--) {
    // Light plural folding so unlisted plurals still hit ("shrimps" → shrimp,
    // "potatoes" → potato).
    const word = words[i];
    const hit =
      WORD[word] ??
      (word.endsWith("es") ? WORD[word.slice(0, -2)] : undefined) ??
      (word.endsWith("s") ? WORD[word.slice(0, -1)] : undefined);
    if (hit !== undefined) return hit;
  }
  return null;
}
