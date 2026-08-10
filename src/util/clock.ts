/**
 * Clock abstraction so timestamps are injectable/deterministic in tests.
 * The real clock uses Date; the fixed clock returns a monotonic counter.
 */
import type { Timestamp } from "../core/types.ts";

export interface Clock {
  now(): Timestamp;
}

export function systemClock(): Clock {
  return {
    now(): Timestamp {
      return new Date().toISOString();
    },
  };
}

/** Deterministic clock: advances by `stepMs` on each call from a fixed epoch. */
export function fixedClock(startIso = "2026-01-01T00:00:00.000Z", stepMs = 1000): Clock {
  let t = Date.parse(startIso);
  return {
    now(): Timestamp {
      const iso = new Date(t).toISOString();
      t += stepMs;
      return iso;
    },
  };
}
