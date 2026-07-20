import type { WarningPresentation } from "./types";

export type WarningPresentationGroup = {
  category: string;
  categoryLabel: string;
  count: number;
  samples: WarningPresentation[];
  items: WarningPresentation[];
};

export function groupWarningPresentations(
  items: WarningPresentation[],
  sampleLimit = 3
): WarningPresentationGroup[] {
  const groups = new Map<string, WarningPresentation[]>();
  for (const item of items) {
    const current = groups.get(item.category) ?? [];
    current.push(item);
    groups.set(item.category, current);
  }
  return Array.from(groups.entries()).map(([category, entries]) => ({
    category,
    categoryLabel: entries[0]?.category_label ?? category,
    count: entries.length,
    samples: entries.slice(0, Math.max(0, sampleLimit)),
    items: entries
  }));
}
