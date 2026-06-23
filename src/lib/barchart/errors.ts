export type BarchartErrorKind =
  | "AUTH" // 401/403 or "not authorized" / "not subscribed"
  | "EMPTY" // 204 or empty result set
  | "RATE_LIMIT" // 429 or "max queries"
  | "NETWORK" // fetch failure / timeout / 5xx
  | "PARSE" // invalid JSON or schema mismatch
  | "BAD_PARAMS" // invalid input to a wrapper
  | "UNKNOWN";

export interface BarchartErrorOptions {
  status?: number;
  barchartCode?: number;
  cause?: unknown;
}

export class BarchartError extends Error {
  readonly kind: BarchartErrorKind;
  readonly status?: number;
  readonly barchartCode?: number;

  constructor(kind: BarchartErrorKind, message: string, opts: BarchartErrorOptions = {}) {
    super(message);
    this.name = "BarchartError";
    this.kind = kind;
    this.status = opts.status;
    this.barchartCode = opts.barchartCode;
    if (opts.cause !== undefined) {
      (this as { cause?: unknown }).cause = opts.cause;
    }
  }
}

export function isRetryable(kind: BarchartErrorKind): boolean {
  return kind === "NETWORK" || kind === "RATE_LIMIT";
}
