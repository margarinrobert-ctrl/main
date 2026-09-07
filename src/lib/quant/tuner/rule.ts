/**
 * The rule language: `close>ema200 and rsi14<40` compiled to a per-bar boolean mask.
 *
 * This is a hand-written tokeniser and recursive-descent parser rather than anything built on
 * `eval` or `new Function`. Three reasons, in order of how much they matter:
 *
 *   1. The rule text comes from a text box in a browser. Handing user input to `eval` is a script
 *      injection, and the app's Content-Security-Policy would refuse `new Function` anyway.
 *   2. A parser can say `unknown indicator "emaa" at column 7` instead of `ReferenceError`.
 *   3. It fixes the operator-precedence trap directly. In array languages `and` has to become a
 *      bitwise `&`, which binds TIGHTER than a comparison, so a textual rewrite turns
 *      `c>ema200 and rsi14<40` into `c > (ema200 & rsi14) < 40` -- a different rule that still
 *      runs. Parsing to a tree means the comparisons are grouped before the conjunction ever
 *      sees them.
 *
 * Chained comparisons (`35 < rsi14 < 65`) are expanded to `(35<rsi14) and (rsi14<65)`, which is
 * what a person writing that means and what an array language cannot do on its own.
 *
 * A NaN on either side of a comparison yields FALSE, so a rule simply does not fire while its
 * indicators are still warming up. That is deliberate: the alternative is a warm-up window that
 * every rule has to remember to state.
 */
import { get, REGISTRY, type IndicatorContext } from "./indicators";

type TokKind = "num" | "ident" | "op" | "lparen" | "rparen" | "comma" | "end";
interface Tok {
  kind: TokKind;
  text: string;
  pos: number;
}

const WORD_OPS = new Set(["and", "or", "not"]);
const CMP_OPS = new Set(["<", ">", "<=", ">=", "==", "!="]);

export class RuleError extends Error {
  constructor(message: string, readonly pos: number) {
    super(message);
    this.name = "RuleError";
  }
}

function tokenize(src: string): Tok[] {
  const out: Tok[] = [];
  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if (/\s/.test(ch)) {
      i++;
      continue;
    }
    if (ch === "(") {
      out.push({ kind: "lparen", text: ch, pos: i++ });
      continue;
    }
    if (ch === ")") {
      out.push({ kind: "rparen", text: ch, pos: i++ });
      continue;
    }
    if (ch === ",") {
      out.push({ kind: "comma", text: ch, pos: i++ });
      continue;
    }
    if (/[0-9]/.test(ch) || (ch === "." && /[0-9]/.test(src[i + 1] ?? ""))) {
      const start = i;
      while (i < src.length && /[0-9.]/.test(src[i])) i++;
      out.push({ kind: "num", text: src.slice(start, i), pos: start });
      continue;
    }
    if (/[A-Za-z_]/.test(ch)) {
      const start = i;
      while (i < src.length && /[A-Za-z0-9_]/.test(src[i])) i++;
      out.push({ kind: "ident", text: src.slice(start, i), pos: start });
      continue;
    }
    const two = src.slice(i, i + 2);
    if (CMP_OPS.has(two)) {
      out.push({ kind: "op", text: two, pos: i });
      i += 2;
      continue;
    }
    if (CMP_OPS.has(ch) || "+-*/".includes(ch)) {
      out.push({ kind: "op", text: ch, pos: i++ });
      continue;
    }
    if (ch === "=" && src[i + 1] !== "=") throw new RuleError(`use == for equality, not =`, i);
    throw new RuleError(`unexpected character "${ch}"`, i);
  }
  out.push({ kind: "end", text: "", pos: src.length });
  return out;
}

type Node =
  | { t: "num"; v: number }
  | { t: "ind"; name: string; args: number[]; pos: number }
  | { t: "arith"; op: string; l: Node; r: Node }
  | { t: "neg"; x: Node }
  | { t: "cmp"; op: string; l: Node; r: Node }
  | { t: "and" | "or"; l: Node; r: Node }
  | { t: "not"; x: Node };

/** Split a bare identifier into an indicator name and its trailing period: ema200 -> ema, 200. */
function splitIdent(text: string, pos: number): { name: string; args: number[] } {
  if (REGISTRY[text]) return { name: text, args: [] };
  const m = /^([A-Za-z_]+?)(\d+)$/.exec(text);
  if (m && REGISTRY[m[1]]) return { name: m[1], args: [Number(m[2])] };
  const near = Object.keys(REGISTRY).filter((k) => k.startsWith(text.slice(0, 3)));
  throw new RuleError(`unknown indicator "${text}"${near.length ? ` — did you mean ${near.slice(0, 4).join(", ")}?` : ""}`, pos);
}

class Parser {
  private i = 0;
  constructor(private readonly toks: Tok[]) {}

  private peek(): Tok {
    return this.toks[this.i];
  }
  private eat(): Tok {
    return this.toks[this.i++];
  }
  private isWord(w: string): boolean {
    const t = this.peek();
    return t.kind === "ident" && t.text.toLowerCase() === w;
  }

  parse(): Node {
    const n = this.parseOr();
    if (this.peek().kind !== "end") throw new RuleError(`unexpected "${this.peek().text}"`, this.peek().pos);
    return n;
  }

  private parseOr(): Node {
    let l = this.parseAnd();
    while (this.isWord("or")) {
      this.eat();
      l = { t: "or", l, r: this.parseAnd() };
    }
    return l;
  }

  private parseAnd(): Node {
    let l = this.parseNot();
    while (this.isWord("and")) {
      this.eat();
      l = { t: "and", l, r: this.parseNot() };
    }
    return l;
  }

  private parseNot(): Node {
    if (this.isWord("not")) {
      this.eat();
      return { t: "not", x: this.parseNot() };
    }
    return this.parseCmp();
  }

  /** A chain `a < b < c` becomes `(a<b) and (b<c)`, which is what writing it means. */
  private parseCmp(): Node {
    const first = this.parseAdd();
    const ops: string[] = [];
    const operands: Node[] = [first];
    while (this.peek().kind === "op" && CMP_OPS.has(this.peek().text)) {
      ops.push(this.eat().text);
      operands.push(this.parseAdd());
    }
    if (ops.length === 0) return first;
    let out: Node = { t: "cmp", op: ops[0], l: operands[0], r: operands[1] };
    for (let k = 1; k < ops.length; k++) {
      out = { t: "and", l: out, r: { t: "cmp", op: ops[k], l: operands[k], r: operands[k + 1] } };
    }
    return out;
  }

  private parseAdd(): Node {
    let l = this.parseMul();
    while (this.peek().kind === "op" && (this.peek().text === "+" || this.peek().text === "-")) {
      const op = this.eat().text;
      l = { t: "arith", op, l, r: this.parseMul() };
    }
    return l;
  }

  private parseMul(): Node {
    let l = this.parseUnary();
    while (this.peek().kind === "op" && (this.peek().text === "*" || this.peek().text === "/")) {
      const op = this.eat().text;
      l = { t: "arith", op, l, r: this.parseUnary() };
    }
    return l;
  }

  private parseUnary(): Node {
    if (this.peek().kind === "op" && this.peek().text === "-") {
      this.eat();
      return { t: "neg", x: this.parseUnary() };
    }
    return this.parsePrimary();
  }

  private parsePrimary(): Node {
    const t = this.eat();
    if (t.kind === "num") return { t: "num", v: Number(t.text) };
    if (t.kind === "lparen") {
      const n = this.parseOr();
      if (this.peek().kind !== "rparen") throw new RuleError("expected )", this.peek().pos);
      this.eat();
      return n;
    }
    if (t.kind === "ident") {
      if (WORD_OPS.has(t.text.toLowerCase())) throw new RuleError(`"${t.text}" needs something on its left`, t.pos);
      if (this.peek().kind === "lparen") {
        this.eat();
        const args: number[] = [];
        if (this.peek().kind !== "rparen") {
          for (;;) {
            const a = this.parseAdd();
            if (a.t !== "num" && !(a.t === "neg" && a.x.t === "num")) {
              throw new RuleError(`${t.text}(...) takes plain numbers, not expressions`, t.pos);
            }
            args.push(a.t === "num" ? a.v : -(a.x as { t: "num"; v: number }).v);
            if (this.peek().kind !== "comma") break;
            this.eat();
          }
        }
        if (this.peek().kind !== "rparen") throw new RuleError("expected )", this.peek().pos);
        this.eat();
        if (!REGISTRY[t.text]) throw new RuleError(`unknown indicator "${t.text}"`, t.pos);
        return { t: "ind", name: t.text, args, pos: t.pos };
      }
      const { name, args } = splitIdent(t.text, t.pos);
      return { t: "ind", name, args, pos: t.pos };
    }
    throw new RuleError(`unexpected "${t.text || "end of rule"}"`, t.pos);
  }
}

type Val = { bool: false; data: Float64Array } | { bool: true; data: Uint8Array };

function evalNode(node: Node, ctx: IndicatorContext, n: number): Val {
  switch (node.t) {
    case "num": {
      const d = new Float64Array(n).fill(node.v);
      return { bool: false, data: d };
    }
    case "ind":
      return { bool: false, data: get(ctx, node.name, node.args) };
    case "neg": {
      const x = numeric(evalNode(node.x, ctx, n), "negation");
      const d = new Float64Array(n);
      for (let i = 0; i < n; i++) d[i] = -x[i];
      return { bool: false, data: d };
    }
    case "arith": {
      const l = numeric(evalNode(node.l, ctx, n), node.op);
      const r = numeric(evalNode(node.r, ctx, n), node.op);
      const d = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        const a = l[i];
        const b = r[i];
        d[i] = node.op === "+" ? a + b : node.op === "-" ? a - b : node.op === "*" ? a * b : a / b;
      }
      return { bool: false, data: d };
    }
    case "cmp": {
      const l = numeric(evalNode(node.l, ctx, n), node.op);
      const r = numeric(evalNode(node.r, ctx, n), node.op);
      const d = new Uint8Array(n);
      for (let i = 0; i < n; i++) {
        const a = l[i];
        const b = r[i];
        // NaN on either side is FALSE, so a rule does not fire while its indicators warm up
        if (Number.isNaN(a) || Number.isNaN(b)) continue;
        const ok =
          node.op === "<" ? a < b : node.op === ">" ? a > b : node.op === "<=" ? a <= b : node.op === ">=" ? a >= b : node.op === "==" ? a === b : a !== b;
        d[i] = ok ? 1 : 0;
      }
      return { bool: true, data: d };
    }
    case "and":
    case "or": {
      const l = boolean(evalNode(node.l, ctx, n), node.t);
      const r = boolean(evalNode(node.r, ctx, n), node.t);
      const d = new Uint8Array(n);
      for (let i = 0; i < n; i++) d[i] = node.t === "and" ? (l[i] && r[i] ? 1 : 0) : l[i] || r[i] ? 1 : 0;
      return { bool: true, data: d };
    }
    case "not": {
      const x = boolean(evalNode(node.x, ctx, n), "not");
      const d = new Uint8Array(n);
      for (let i = 0; i < n; i++) d[i] = x[i] ? 0 : 1;
      return { bool: true, data: d };
    }
  }
}

function numeric(v: Val, where: string): ArrayLike<number> {
  if (!v.bool) return v.data;
  const d = new Float64Array(v.data.length);
  for (let i = 0; i < d.length; i++) d[i] = v.data[i];
  void where;
  return d;
}

function boolean(v: Val, where: string): ArrayLike<number> {
  if (v.bool) return v.data;
  throw new RuleError(`"${where}" needs a condition on both sides — compare it to something, e.g. "... > 0"`, 0);
}

/** Compile once; the AST is cheap to keep and the indicator arrays are memoised on the context. */
export function parseRule(src: string): Node {
  return new Parser(tokenize(src)).parse();
}

/**
 * Evaluate a rule to a per-bar mask. An empty rule (or "always") fires on every bar, which is the
 * baseline every filter has to beat.
 */
export function ruleMask(src: string, ctx: IndicatorContext): Uint8Array {
  const n = ctx.bars.length;
  const s = src.trim();
  if (s === "" || s.toLowerCase() === "always" || s === "1") return new Uint8Array(n).fill(1);
  const v = evalNode(parseRule(s), ctx, n);
  if (!v.bool) {
    throw new RuleError(`this rule is a number, not a condition — compare it to something, e.g. "${s} > 0"`, 0);
  }
  return v.data;
}

/** Substitute {name} placeholders, so one rule string becomes a sweep axis. */
export function fillTemplate(src: string, params: Record<string, number>): string {
  return src.replace(/\{(\w+)\}/g, (m, k: string) => {
    if (!(k in params)) throw new RuleError(`no value given for {${k}}`, src.indexOf(m));
    return String(params[k]);
  });
}

export function templateKeys(src: string): string[] {
  return Array.from(new Set(Array.from(src.matchAll(/\{(\w+)\}/g)).map((m) => m[1])));
}
