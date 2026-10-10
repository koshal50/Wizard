import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { remainingMs } from '../deadline.ts';

const DB_PATH = process.env.WIZARD_CEREBRAS_GATE_DB ?? join(homedir(), ".wizard", "cerebras-rate-gate.sqlite3");

export class CerebrasRateGate {
  private readonly db: DatabaseSync;
  private readonly intervalSeconds: number;
  constructor(intervalMs = 12_000) {
    this.intervalSeconds = intervalMs / 1000;
    mkdirSync(dirname(DB_PATH), { recursive: true });
    this.db = new DatabaseSync(DB_PATH);
    this.db.exec("PRAGMA busy_timeout=30000; CREATE TABLE IF NOT EXISTS provider_gate (provider TEXT PRIMARY KEY, next_allowed REAL NOT NULL)");
  }

  async acquire(): Promise<void> {
    while (true) {
      this.db.exec("BEGIN IMMEDIATE");
      const row = this.db.prepare("SELECT next_allowed FROM provider_gate WHERE provider='cerebras'").get() as { next_allowed: number } | undefined;
      const now = Date.now() / 1000;
      const wait = row ? row.next_allowed - now : 0;
      if (wait <= 0) {
        this.db.prepare("INSERT INTO provider_gate(provider,next_allowed) VALUES('cerebras',?) ON CONFLICT(provider) DO UPDATE SET next_allowed=excluded.next_allowed").run(now + this.intervalSeconds);
      }
      this.db.exec("COMMIT");
      if (wait <= 0) return;
      if (wait * 1000 >= remainingMs(300_000)) throw new Error('Provider rate gate exceeds investigation deadline');
      console.info(JSON.stringify({ event: "provider_rate_limit_wait", provider: "cerebras", wait_ms: Math.ceil(wait) }));
      await new Promise((resolve) => setTimeout(resolve, wait * 1000));
    }
  }

  defer(waitMs: number): void {
    this.db.exec("BEGIN IMMEDIATE");
    this.db.prepare("INSERT INTO provider_gate(provider,next_allowed) VALUES('cerebras',?) ON CONFLICT(provider) DO UPDATE SET next_allowed=MAX(provider_gate.next_allowed, excluded.next_allowed)").run(Date.now() / 1000 + waitMs / 1000);
    this.db.exec("COMMIT");
  }
}

export function retryAfterMs(headers: Headers): number {
  const retryAfter = headers.get("retry-after");
  if (retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
    const date = Date.parse(retryAfter);
    if (Number.isFinite(date)) return Math.max(0, date - Date.now());
  }
  for (const name of ["x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"]) {
    const value = headers.get(name);
    if (!value) continue;
    const number = Number(value);
    if (Number.isFinite(number)) return Math.max(0, number - (number > 10_000_000 ? Date.now() / 1000 : 0)) * 1000;
    const match = value.match(/^([\d.]+)\s*(ms|s|m)?$/i);
    if (match) {
      const amount = Number(match[1]);
      const unit = (match[2] ?? "s").toLowerCase();
      return amount * (unit === "ms" ? 1 : unit === "m" ? 60_000 : 1000);
    }
    const date = Date.parse(value);
    if (Number.isFinite(date)) return Math.max(0, date - Date.now());
  }
  return 60_000;
}
