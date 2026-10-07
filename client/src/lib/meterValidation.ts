export function normalizeMeterCode(value: string): string {
  return value.replace(/\D/g, "").slice(0, 20);
}

export function isValidMeterCode(value: string): boolean {
  return /^\d{20}$/.test(value);
}
