export function formatPercent(value: unknown, digits = 2): string {
  const number = toNumber(value);
  if (number === null) return "--";
  return `${(number * 100).toFixed(digits)}%`;
}

export function formatNumber(value: unknown, digits = 2): string {
  const number = toNumber(value);
  if (number === null) return "--";
  return number.toFixed(digits);
}

export function formatWeight(value: unknown): string {
  return formatPercent(value, 2);
}

export function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function compactDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}
