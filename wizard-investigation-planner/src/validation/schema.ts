/**
 * Zero-dependency, Zod-like runtime schema validator.
 *
 * We deliberately avoid pulling in Zod (the existing Wizard project has no
 * validation library and the build must stay offline/dependency-free). This is
 * intentionally small — just enough to validate untrusted LLM output before it
 * is allowed anywhere near the Runtime.
 *
 * A schema is `{ validate(value, path) => Result<T> }`. Composers: string,
 * number, boolean, literal, enum_, union, array, object, record, unknown.
 */

export type Ok<T> = { ok: true; value: T };
export type Err = { ok: false; errors: string[] };
export type Result<T> = Ok<T> | Err;

export interface Schema<T> {
  readonly _t?: T; // phantom for inference
  validate(value: unknown, path: string): Result<T>;
  optional(): Schema<T | undefined>;
}

export type Infer<S> = S extends Schema<infer T> ? T : never;

function ok<T>(value: T): Ok<T> {
  return { ok: true, value };
}
function err(errors: string[]): Err {
  return { ok: false, errors };
}
function at(path: string, msg: string): string {
  return `${path || "<root>"}: ${msg}`;
}

function makeSchema<T>(fn: (value: unknown, path: string) => Result<T>): Schema<T> {
  const schema: Schema<T> = {
    validate: fn,
    optional(): Schema<T | undefined> {
      return makeSchema<T | undefined>((value, path) => {
        if (value === undefined) return ok(undefined);
        return fn(value, path);
      });
    },
  };
  return schema;
}

export function string(opts?: { minLength?: number }): Schema<string> {
  return makeSchema<string>((value, path) => {
    if (typeof value !== "string") return err([at(path, `expected string, got ${typeName(value)}`)]);
    if (opts?.minLength !== undefined && value.length < opts.minLength) {
      return err([at(path, `string shorter than min length ${opts.minLength}`)]);
    }
    return ok(value);
  });
}

export function number(opts?: { min?: number; max?: number; int?: boolean }): Schema<number> {
  return makeSchema<number>((value, path) => {
    if (typeof value !== "number" || Number.isNaN(value)) {
      return err([at(path, `expected number, got ${typeName(value)}`)]);
    }
    if (opts?.int && !Number.isInteger(value)) return err([at(path, `expected integer`)]);
    if (opts?.min !== undefined && value < opts.min) return err([at(path, `number < min ${opts.min}`)]);
    if (opts?.max !== undefined && value > opts.max) return err([at(path, `number > max ${opts.max}`)]);
    return ok(value);
  });
}

export function boolean(): Schema<boolean> {
  return makeSchema<boolean>((value, path) =>
    typeof value === "boolean" ? ok(value) : err([at(path, `expected boolean, got ${typeName(value)}`)]),
  );
}

export function unknown(): Schema<unknown> {
  return makeSchema<unknown>((value) => ok(value));
}

export function literal<L extends string | number | boolean>(lit: L): Schema<L> {
  return makeSchema<L>((value, path) =>
    value === lit ? ok(lit) : err([at(path, `expected literal ${JSON.stringify(lit)}, got ${JSON.stringify(value)}`)]),
  );
}

export function enum_<L extends string>(values: readonly L[]): Schema<L> {
  return makeSchema<L>((value, path) => {
    if (typeof value === "string" && (values as readonly string[]).includes(value)) return ok(value as L);
    return err([at(path, `expected one of [${values.join(", ")}], got ${JSON.stringify(value)}`)]);
  });
}

export function array<T>(item: Schema<T>): Schema<T[]> {
  return makeSchema<T[]>((value, path) => {
    if (!Array.isArray(value)) return err([at(path, `expected array, got ${typeName(value)}`)]);
    const out: T[] = [];
    const errors: string[] = [];
    for (let i = 0; i < value.length; i++) {
      const r = item.validate(value[i], `${path}[${i}]`);
      if (r.ok) out.push(r.value);
      else errors.push(...r.errors);
    }
    return errors.length ? err(errors) : ok(out);
  });
}

export function record<T>(valueSchema: Schema<T>): Schema<Record<string, T>> {
  return makeSchema<Record<string, T>>((value, path) => {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return err([at(path, `expected object, got ${typeName(value)}`)]);
    }
    const out: Record<string, T> = {};
    const errors: string[] = [];
    for (const [k, v] of Object.entries(value)) {
      const r = valueSchema.validate(v, `${path}.${k}`);
      if (r.ok) out[k] = r.value;
      else errors.push(...r.errors);
    }
    return errors.length ? err(errors) : ok(out);
  });
}

type ShapeToType<S extends Record<string, Schema<unknown>>> = {
  [K in keyof S]: S[K] extends Schema<infer T> ? T : never;
};

export function object<S extends Record<string, Schema<unknown>>>(
  shape: S,
  opts?: { allowUnknownKeys?: boolean },
): Schema<ShapeToType<S>> {
  return makeSchema<ShapeToType<S>>((value, path) => {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return err([at(path, `expected object, got ${typeName(value)}`)]);
    }
    const obj = value as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    const errors: string[] = [];
    for (const key of Object.keys(shape)) {
      const fieldSchema = shape[key] as Schema<unknown>;
      const r = fieldSchema.validate(obj[key], path ? `${path}.${key}` : key);
      if (r.ok) {
        if (r.value !== undefined) out[key] = r.value;
      } else {
        errors.push(...r.errors);
      }
    }
    if (!opts?.allowUnknownKeys) {
      for (const key of Object.keys(obj)) {
        if (!(key in shape)) errors.push(at(path ? `${path}.${key}` : key, `unexpected key`));
      }
    }
    return errors.length ? err(errors) : ok(out as ShapeToType<S>);
  });
}

/** Discriminated union by a string field (e.g. `type`). */
export function taggedUnion<T>(
  tag: string,
  variants: Record<string, Schema<unknown>>,
): Schema<T> {
  return makeSchema<T>((value, path) => {
    if (typeof value !== "object" || value === null) {
      return err([at(path, `expected object for tagged union`)]);
    }
    const tagValue = (value as Record<string, unknown>)[tag];
    if (typeof tagValue !== "string" || !(tagValue in variants)) {
      return err([at(path, `invalid discriminator ${tag}=${JSON.stringify(tagValue)}; expected one of [${Object.keys(variants).join(", ")}]`)]);
    }
    const variant = variants[tagValue] as Schema<unknown>;
    const r = variant.validate(value, path);
    return r.ok ? ok(r.value as T) : err(r.errors);
  });
}

function typeName(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

/** Convenience: parse arbitrary (possibly JSON-string) input against a schema. */
export function safeParse<T>(schema: Schema<T>, value: unknown): Result<T> {
  return schema.validate(value, "");
}
