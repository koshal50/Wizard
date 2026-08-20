/**
 * Deterministic id factory.
 *
 * Ids are sequential per-prefix so that investigations are reproducible and
 * tests can assert on exact ids (e.g. "node_001"). A single factory instance is
 * threaded through an investigation.
 */

export interface IdFactory {
  next(prefix: string): string;
  reset(): void;
}

export function createIdFactory(): IdFactory {
  const counters = new Map<string, number>();
  return {
    next(prefix: string): string {
      const n = (counters.get(prefix) ?? 0) + 1;
      counters.set(prefix, n);
      return `${prefix}_${String(n).padStart(3, "0")}`;
    },
    reset(): void {
      counters.clear();
    },
  };
}
