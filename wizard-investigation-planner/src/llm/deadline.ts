import { AsyncLocalStorage } from "node:async_hooks";
export const deadlineContext = new AsyncLocalStorage<number>();
export function remainingMs(defaultMs: number): number {
  const deadline = deadlineContext.getStore();
  const remaining = deadline === undefined ? defaultMs : deadline - Date.now();
  if (remaining <= 0) throw new Error("Investigation deadline reached");
  return Math.min(defaultMs, remaining);
}
