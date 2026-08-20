/**
 * Structured, secret-safe logger.
 *
 * Emits structured events (level + event name + fields). Redacts anything that
 * looks like a secret so API keys / tokens / .env contents can never leak into
 * logs. Log lines are captured in-memory as well so the report/tests can inspect
 * the investigation trace.
 */

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface LogEvent {
  level: LogLevel;
  event: string;
  fields: Record<string, unknown>;
  time: string;
}

const SECRET_KEY_PATTERN = /(api[_-]?key|secret|token|password|passwd|authorization|bearer|private[_-]?key)/i;
const SECRET_VALUE_PATTERN = /\b(sk-[a-z0-9-]{8,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,})\b/gi;

function redact(value: unknown, keyHint?: string): unknown {
  if (keyHint && SECRET_KEY_PATTERN.test(keyHint)) return "[REDACTED]";
  if (typeof value === "string") {
    return value.replace(SECRET_VALUE_PATTERN, "[REDACTED]");
  }
  if (Array.isArray(value)) return value.map((v) => redact(v));
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) out[k] = redact(v, k);
    return out;
  }
  return value;
}

export interface Logger {
  debug(event: string, fields?: Record<string, unknown>): void;
  info(event: string, fields?: Record<string, unknown>): void;
  warn(event: string, fields?: Record<string, unknown>): void;
  error(event: string, fields?: Record<string, unknown>): void;
  events(): LogEvent[];
}

export interface LoggerOptions {
  level?: LogLevel;
  /** print to stderr as well as capturing. Default false (CLI prints its own). */
  echo?: boolean;
  now?: () => string;
}

const LEVEL_ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };

export function createLogger(opts: LoggerOptions = {}): Logger {
  const min = LEVEL_ORDER[opts.level ?? "info"];
  const captured: LogEvent[] = [];
  const now = opts.now ?? (() => new Date().toISOString());

  function emit(level: LogLevel, event: string, fields?: Record<string, unknown>): void {
    const safeFields = (redact(fields ?? {}) as Record<string, unknown>) ?? {};
    const rec: LogEvent = { level, event, fields: safeFields, time: now() };
    captured.push(rec);
    if (opts.echo && LEVEL_ORDER[level] >= min) {
      const line = `[${level.toUpperCase()}] ${event} ${Object.keys(safeFields).length ? JSON.stringify(safeFields) : ""}`;
      process.stderr.write(line.trimEnd() + "\n");
    }
  }

  return {
    debug: (e, f) => emit("debug", e, f),
    info: (e, f) => emit("info", e, f),
    warn: (e, f) => emit("warn", e, f),
    error: (e, f) => emit("error", e, f),
    events: () => captured.slice(),
  };
}

export function nullLogger(): Logger {
  return {
    debug: () => {},
    info: () => {},
    warn: () => {},
    error: () => {},
    events: () => [],
  };
}
