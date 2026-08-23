/**
 * Robust JSON extraction from LLM text output.
 *
 * Real models frequently wrap JSON in ```json fences, prefix it with prose
 * ("Here is the plan:"), or append a trailing explanation. This module pulls
 * the first balanced JSON object/array out of arbitrary text so it can be
 * schema-validated. It NEVER trusts the parsed value beyond "it is valid JSON" —
 * the schema layer does the real validation.
 */

export type JsonExtraction =
  | { ok: true; value: unknown }
  | { ok: false; error: string };

/** Strip a leading/trailing markdown code fence if present. */
function stripFence(text: string): string {
  const trimmed = text.trim();
  const fence = /^```(?:json|javascript|js)?\s*([\s\S]*?)\s*```$/i.exec(trimmed);
  if (fence && fence[1] !== undefined) return fence[1].trim();
  return trimmed;
}

/**
 * Scan for the first balanced `{...}` or `[...]` region, respecting string
 * literals and escapes so braces inside strings don't confuse the balance count.
 */
function findBalanced(text: string): string | null {
  const start = firstStructuralIndex(text);
  if (start < 0) return null;
  const open = text[start];
  const close = open === "{" ? "}" : "]";

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === open) depth++;
    else if (ch === close) {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return null;
}

function firstStructuralIndex(text: string): number {
  const brace = text.indexOf("{");
  const bracket = text.indexOf("[");
  if (brace < 0) return bracket;
  if (bracket < 0) return brace;
  return Math.min(brace, bracket);
}

export function extractJson(text: string): JsonExtraction {
  const cleaned = stripFence(text);

  // Fast path: the whole thing is JSON.
  const direct = tryParse(cleaned);
  if (direct.ok) return direct;

  // Otherwise pull out the first balanced region.
  const region = findBalanced(cleaned);
  if (region === null) {
    return { ok: false, error: "no JSON object/array found in model output" };
  }
  return tryParse(region);
}

function tryParse(text: string): JsonExtraction {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (e) {
    return { ok: false, error: `JSON parse failed: ${(e as Error).message}` };
  }
}
