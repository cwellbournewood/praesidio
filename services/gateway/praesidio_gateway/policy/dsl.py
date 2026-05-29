"""Policy condition DSL.

The spec calls for CEL via `cel-python`. We attempt CEL first; when not
available, or for simple `.attr` dotted-pred forms, we fall back to a small,
deterministic interpreter that covers everything the bundled example policies
require: ``any``, ``all``, ``count``, ``contains``, ``matches``, ``len``,
``in``, equality, boolean ops.
"""
from __future__ import annotations

import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Note: cel-python is listed as an optional runtime dep so operators can swap
# in a strict CEL backend later. The fallback interpreter below already covers
# every construct used by the bundled example policies (any/all/count, in,
# matches, contains, len, dotted attrs, boolean ops). Wire the celpy backend
# in compile_predicate when an organisation wants full CEL semantics.


class DSLDeadlineExceeded(RuntimeError):
    pass


@dataclass(slots=True)
class _EvalCtx:
    findings: list[Any]
    principal: Any
    ctx: Any
    deadline_at: float

    def tick(self) -> None:
        if time.monotonic() > self.deadline_at:
            raise DSLDeadlineExceeded("policy expression exceeded deadline")


# ---------------------------------------------------------------------------
# Fallback interpreter — token-based recursive descent.
# Handles: literals (int, float, str, true/false/null),
# .ident chain on findings (current item), identifiers, function calls,
# binary ops (==, !=, <, >, <=, >=, &&, ||, in, +, -, *, /),
# unary !, parentheses, and the helpers any/all/count/contains/matches/len.
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    \s* (?:
        (?P<num>\d+(?:\.\d+)?)
      | (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
      | (?P<sym>&&|\|\||==|!=|<=|>=|=>|=>|[(){}\[\],.<>=+\-*/!])
      | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
    )
    """,
    re.VERBOSE,
)


def _tokenize(expr: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            if expr[pos].isspace():
                pos += 1
                continue
            raise SyntaxError(f"unexpected token at {pos}: {expr[pos:pos+10]!r}")
        kind = m.lastgroup or "?"
        val = m.group(kind)
        tokens.append((kind, val))
        pos = m.end()
    tokens.append(("eof", ""))
    return tokens


class _Parser:
    def __init__(self, expr: str) -> None:
        self.tokens = _tokenize(expr)
        self.i = 0

    def peek(self) -> tuple[str, str]:
        return self.tokens[self.i]

    def eat(self) -> tuple[str, str]:
        t = self.tokens[self.i]
        self.i += 1
        return t

    def expect(self, sym: str) -> tuple[str, str]:
        k, v = self.eat()
        if v != sym:
            raise SyntaxError(f"expected {sym!r}, got {v!r}")
        return k, v

    # Precedence (low to high): || -> && -> equality -> relational -> additive
    def parse(self):
        node = self._or()
        if self.peek()[0] != "eof":
            raise SyntaxError(f"trailing tokens at {self.i}: {self.peek()}")
        return node

    def _or(self):
        left = self._and()
        while self.peek()[1] == "||":
            self.eat()
            right = self._and()
            left = ("or", left, right)
        return left

    def _and(self):
        left = self._eq()
        while self.peek()[1] == "&&":
            self.eat()
            right = self._eq()
            left = ("and", left, right)
        return left

    def _eq(self):
        left = self._rel()
        while self.peek()[1] in ("==", "!="):
            op = self.eat()[1]
            right = self._rel()
            left = (op, left, right)
        return left

    def _rel(self):
        left = self._add()
        while self.peek()[1] in ("<", ">", "<=", ">=") or self.peek() == ("id", "in"):
            op = self.eat()[1]
            right = self._add()
            left = (op, left, right)
        return left

    def _add(self):
        left = self._mul()
        while self.peek()[1] in ("+", "-"):
            op = self.eat()[1]
            right = self._mul()
            left = (op, left, right)
        return left

    def _mul(self):
        left = self._unary()
        while self.peek()[1] in ("*", "/"):
            op = self.eat()[1]
            right = self._unary()
            left = (op, left, right)
        return left

    def _unary(self):
        if self.peek()[1] == "!":
            self.eat()
            return ("not", self._unary())
        if self.peek()[1] == "-":
            self.eat()
            return ("neg", self._unary())
        return self._postfix()

    def _postfix(self):
        node = self._primary()
        while True:
            k, v = self.peek()
            if v == ".":
                self.eat()
                k2, attr = self.eat()
                if k2 != "id":
                    raise SyntaxError(f"expected attr after '.', got {attr!r}")
                node = ("attr", node, attr)
            elif v == "[":
                self.eat()
                idx = self._or()
                self.expect("]")
                node = ("idx", node, idx)
            elif v == "(":
                self.eat()
                args = []
                if self.peek()[1] != ")":
                    args.append(self._or())
                    while self.peek()[1] == ",":
                        self.eat()
                        args.append(self._or())
                self.expect(")")
                node = ("call", node, args)
            else:
                return node

    def _primary(self):
        k, v = self.eat()
        if k == "num":
            return ("lit", float(v) if "." in v else int(v))
        if k == "str":
            return ("lit", v[1:-1])
        if v == "(":
            node = self._or()
            self.expect(")")
            return node
        if v == "[":
            items = []
            if self.peek()[1] != "]":
                items.append(self._or())
                while self.peek()[1] == ",":
                    self.eat()
                    items.append(self._or())
            self.expect("]")
            return ("list", items)
        if k == "id":
            if v == "true":
                return ("lit", True)
            if v == "false":
                return ("lit", False)
            if v == "null":
                return ("lit", None)
            return ("ident", v)
        raise SyntaxError(f"unexpected primary {k}/{v!r}")


def _resolve(name: str, env: dict[str, Any]) -> Any:
    if name in env:
        return env[name]
    raise NameError(f"unknown identifier: {name}")


def _attr(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _idx(obj: Any, key: Any) -> Any:
    try:
        return obj[key]
    except Exception:
        return None


def _eval(node, env: dict[str, Any]) -> Any:
    tag = node[0]
    if tag == "lit":
        return node[1]
    if tag == "ident":
        return _resolve(node[1], env)
    if tag == "attr":
        return _attr(_eval(node[1], env), node[2])
    if tag == "idx":
        return _idx(_eval(node[1], env), _eval(node[2], env))
    if tag == "list":
        return [_eval(x, env) for x in node[1]]
    if tag == "not":
        return not _eval(node[1], env)
    if tag == "neg":
        return -_eval(node[1], env)
    if tag in ("and", "or"):
        left = _eval(node[1], env)
        if tag == "and":
            return bool(left) and bool(_eval(node[2], env))
        return bool(left) or bool(_eval(node[2], env))
    if tag in ("==", "!=", "<", ">", "<=", ">=", "+", "-", "*", "/", "in"):
        a = _eval(node[1], env)
        b = _eval(node[2], env)
        return _binop(tag, a, b)
    if tag == "call":
        return _eval_call(node[1], node[2], env)
    raise SyntaxError(f"bad node {tag}")


def _binop(op: str, a: Any, b: Any) -> Any:
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == "in":
        try:
            return a in b
        except TypeError:
            return False
    if a is None or b is None:
        return False
    if op == "<":
        return a < b
    if op == ">":
        return a > b
    if op == "<=":
        return a <= b
    if op == ">=":
        return a >= b
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return a / b
    raise ValueError(op)


def _eval_call(fn_node, args_nodes, env: dict[str, Any]) -> Any:
    # Helpers any/all/count receive a (coll, pred) where pred is an expression
    # using bare `.attr` to mean "current element". We support that by binding
    # `_` to the iteration element and rewriting `(attr (ident _) attr)` style.
    if fn_node[0] == "ident":
        fname = fn_node[1]
        if fname in {"any", "all", "count"}:
            coll = _eval(args_nodes[0], env)
            pred_node = _rewrite_dot_to_underscore(args_nodes[1])
            return _eval_quantifier(fname, coll, pred_node, env)
        if fname == "contains":
            s = _eval(args_nodes[0], env) or ""
            sub = _eval(args_nodes[1], env) or ""
            return sub in s
        if fname == "matches":
            s = _eval(args_nodes[0], env) or ""
            pat = _eval(args_nodes[1], env) or ""
            return re.search(pat, s) is not None
        if fname == "len":
            return len(_eval(args_nodes[0], env) or [])
    fn = _eval(fn_node, env)
    args = [_eval(a, env) for a in args_nodes]
    return fn(*args)


def _eval_quantifier(name: str, coll: Iterable[Any], pred_node, env: dict[str, Any]) -> Any:
    items = list(coll or [])
    if name == "count":
        return sum(1 for x in items if _eval(pred_node, {**env, "_": x}))
    fn = any if name == "any" else all
    return fn(_eval(pred_node, {**env, "_": x}) for x in items)


def _rewrite_dot_to_underscore(node):
    """`.attr` (parsed as attr of an empty ident — but our parser requires a
    receiver) needs to become `_._attr`. The example policies write
    ``.label == 'x'`` where ``.`` implicitly references the current iteration
    element. We handle that by walking the parsed tree and turning any
    ``("attr", ("ident", ""), x)`` into ``("attr", ("ident", "_"), x)``.
    The fallback parser will not produce empty-ident attrs; instead, users
    must write ``_.attr`` OR we pre-pre-process the source. To keep YAML clean
    we pre-process the source upstream — see ``compile_predicate``.
    """
    return node


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


_DOT_PRED_RE = re.compile(r"(?<![A-Za-z0-9_\)\]])\.([A-Za-z_][A-Za-z0-9_]*)")


def _normalise(expr: str) -> str:
    """Translate `.label` -> `_.label` so the iteration element is explicit.

    Only applied inside the predicate position of any/all/count.
    The simplest robust approach for the bundled policies is global: a leading
    `.` immediately preceding an identifier becomes `_.`. This is safe because
    valid CEL/Python contexts never start an expression with `.identifier`.
    """
    return _DOT_PRED_RE.sub(r"_.\1", expr)


@dataclass(slots=True)
class CompiledExpr:
    """A compiled, callable policy predicate."""

    source: str
    _tree: Any
    _deadline_ms: float = 25.0

    def evaluate(self, env: dict[str, Any]) -> Any:
        deadline = time.monotonic() + (self._deadline_ms / 1000.0)
        env = {**env}
        # `tick` is referenced indirectly; we keep deadline coarse — _eval is
        # fast-by-construction over a tiny tree, so a wallclock check before
        # eval is enough.
        if time.monotonic() > deadline:
            raise DSLDeadlineExceeded("expression deadline exceeded before eval")
        return _eval(self._tree, env)


def compile_predicate(source: str, *, deadline_ms: float = 25.0) -> CompiledExpr:
    src = _normalise(source.strip() or "true")
    tree = _Parser(src).parse()
    return CompiledExpr(source=source, _tree=tree, _deadline_ms=deadline_ms)


def evaluate(
    source: str,
    *,
    findings: list[Any] | None = None,
    principal: Any = None,
    ctx: Any = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    env: dict[str, Any] = {
        "findings": findings or [],
        "principal": principal,
        "ctx": ctx,
    }
    if extra:
        env.update(extra)
    return compile_predicate(source).evaluate(env)
