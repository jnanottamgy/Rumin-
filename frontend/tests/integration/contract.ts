/**
 * Checks a live API payload against a schema in the committed OpenAPI contract
 * (docs/api/openapi.json) — the same file the frontend's TypeScript types are generated
 * from. Supports the subset of JSON Schema that FastAPI emits: $ref, anyOf/oneOf, const,
 * enum, object (required + properties), array, and the primitive types.
 */
import openapi from "../../../docs/api/openapi.json";

type Schema = {
  $ref?: string;
  anyOf?: Schema[];
  oneOf?: Schema[];
  const?: unknown;
  enum?: unknown[];
  type?: string;
  properties?: Record<string, Schema>;
  required?: string[];
  items?: Schema;
};

const contract = openapi as unknown as { components: { schemas: Record<string, Schema> } };

function resolve(ref: string): Schema {
  const name = ref.replace("#/components/schemas/", "");
  const schema = contract.components.schemas[name];
  if (!schema) throw new Error(`Unknown schema reference ${ref}`);
  return schema;
}

function check(schema: Schema, value: unknown, path: string, problems: string[]): void {
  if (schema.$ref) {
    check(resolve(schema.$ref), value, path, problems);
    return;
  }
  const alternatives = schema.anyOf ?? schema.oneOf;
  if (alternatives) {
    const matches = alternatives.filter((option) => violations(option, value).length === 0);
    if (matches.length === 0) problems.push(`${path}: matches none of the allowed shapes`);
    return;
  }
  if ("const" in schema && value !== schema.const) {
    problems.push(`${path}: expected ${JSON.stringify(schema.const)}`);
  }
  if (schema.enum && !schema.enum.includes(value)) {
    problems.push(`${path}: ${JSON.stringify(value)} is not one of ${schema.enum.join(", ")}`);
  }
  switch (schema.type) {
    case "object": {
      if (typeof value !== "object" || value === null || Array.isArray(value)) {
        problems.push(`${path}: expected an object`);
        return;
      }
      const record = value as Record<string, unknown>;
      for (const key of schema.required ?? []) {
        if (!(key in record)) problems.push(`${path}.${key}: required but missing`);
      }
      for (const [key, property] of Object.entries(schema.properties ?? {})) {
        if (key in record) check(property, record[key], `${path}.${key}`, problems);
      }
      return;
    }
    case "array":
      if (!Array.isArray(value)) problems.push(`${path}: expected an array`);
      else if (schema.items) {
        for (const [index, item] of value.entries()) {
          check(schema.items, item, `${path}[${index}]`, problems);
        }
      }
      return;
    case "string":
      if (typeof value !== "string") problems.push(`${path}: expected a string`);
      return;
    case "integer":
      if (!Number.isInteger(value)) problems.push(`${path}: expected an integer`);
      return;
    case "number":
      if (typeof value !== "number") problems.push(`${path}: expected a number`);
      return;
    case "boolean":
      if (typeof value !== "boolean") problems.push(`${path}: expected a boolean`);
      return;
    case "null":
      if (value !== null) problems.push(`${path}: expected null`);
      return;
  }
}

function violations(schema: Schema, value: unknown): string[] {
  const problems: string[] = [];
  check(schema, value, "$", problems);
  return problems;
}

/** Problems found when checking `value` against components.schemas[`name`]; empty if none. */
export function contractViolations(name: string, value: unknown): string[] {
  return violations({ $ref: `#/components/schemas/${name}` }, value);
}
