export type JsonRecord = Record<string, unknown>;

export function parsePayload(input: string): JsonRecord {
  if (Buffer.byteLength(input, "utf8") > 65_536) {
    throw new Error("payload exceeds 64 KiB");
  }
  let value: unknown;
  try {
    value = JSON.parse(input);
  } catch {
    throw new Error("payload must be valid JSON");
  }
  if (value === null || Array.isArray(value) || typeof value !== "object") {
    throw new Error("payload must be a JSON object");
  }
  return value as JsonRecord;
}

export function requireString(
  value: unknown,
  field: string,
  maximum = 256,
): string {
  if (typeof value !== "string") {
    throw new Error(`${field} must be a string`);
  }
  const normalized = value.trim();
  if (!normalized || normalized.length > maximum) {
    throw new Error(`${field} must contain 1-${maximum} characters`);
  }
  return normalized;
}

export function optionalString(
  value: unknown,
  field: string,
  maximum = 256,
): string | null {
  if (value === undefined || value === null || value === "") return null;
  return requireString(value, field, maximum);
}

export function requireSha256(value: unknown, field = "sha256Hash"): string {
  const hash = requireString(value, field, 64).toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(hash)) throw new Error(`${field} must be SHA-256`);
  return hash;
}

export function requireInteger(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${field} must be a non-negative integer`);
  }
  return value;
}
