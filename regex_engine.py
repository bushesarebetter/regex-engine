import subprocess
import sys
import time


class RegexError(ValueError):
    pass


# AST nodes are tuples:
#   ('chr', chars, negated)  one character: matches c when (c in chars) != negated
#   ('cat', [nodes]) ('alt', [nodes]) ('star', n) ('plus', n) ('opt', n) ('eps',)
def parse(pattern):
    pos = 0

    def peek():
        return pattern[pos] if pos < len(pattern) else None

    def take():
        nonlocal pos
        if pos == len(pattern):
            raise RegexError(f'unexpected end of pattern {pattern!r}')
        pos += 1
        return pattern[pos - 1]

    def alternation():
        branches = [concatenation()]
        while peek() == '|':
            take()
            branches.append(concatenation())
        return branches[0] if len(branches) == 1 else ('alt', branches)

    def concatenation():
        items = []
        while peek() not in (None, '|', ')'):
            items.append(repetition())
        if not items:
            return ('eps',)
        return items[0] if len(items) == 1 else ('cat', items)

    def repetition():
        node = atom()
        while peek() is not None and peek() in '*+?':
            node = ({'*': 'star', '+': 'plus', '?': 'opt'}[take()], node)
        return node

    def atom():
        c = take()
        if c == '(':
            node = alternation()
            if peek() != ')':
                raise RegexError(f'missing ) in {pattern!r}')
            take()
            return node
        if c == '[':
            return char_class()
        if c == '.':
            return ('chr', frozenset('\n'), True)
        if c in '*+?':
            raise RegexError(f'nothing to repeat at position {pos - 1}')
        if c == '\\':
            c = take()
        return ('chr', frozenset(c), False)

    def class_char():
        c = take()
        return take() if c == '\\' else c

    def char_class():
        negated = peek() == '^'
        if negated:
            take()
        chars = set()
        first = True
        while True:
            if peek() is None:
                raise RegexError(f'unterminated character class in {pattern!r}')
            if peek() == ']' and not first:  # a ']' right after '[' or '[^' is literal
                take()
                return ('chr', frozenset(chars), negated)
            first = False
            lo = class_char()
            if peek() == '-' and pos + 1 < len(pattern) and pattern[pos + 1] != ']':
                take()
                hi = class_char()
                if hi < lo:
                    raise RegexError(f'bad range {lo}-{hi}')
                chars.update(map(chr, range(ord(lo), ord(hi) + 1)))
            else:
                chars.add(lo)

    node = alternation()
    if pos != len(pattern):
        raise RegexError(f'unbalanced ) at position {pos}')
    return node


class NFA:
    """Thompson NFA. Each state has epsilon edges and character edges."""

    def __init__(self, pattern):
        self.eps = []    # state -> [target]
        self.moves = []  # state -> [(chars, negated, target)]
        self.start, self.accept = self._build(parse(pattern))

    def _state(self):
        self.eps.append([])
        self.moves.append([])
        return len(self.eps) - 1

    def _build(self, node):
        # Returns (start, end) of a fragment; end has no outgoing edges yet.
        kind = node[0]
        if kind == 'chr':
            s, e = self._state(), self._state()
            self.moves[s].append((node[1], node[2], e))
            return s, e
        if kind == 'eps':
            s = self._state()
            return s, s
        if kind == 'cat':
            start, end = self._build(node[1][0])
            for child in node[1][1:]:
                s, e = self._build(child)
                self.eps[end].append(s)
                end = e
            return start, end
        s, e = self._state(), self._state()
        if kind == 'alt':
            for child in node[1]:
                cs, ce = self._build(child)
                self.eps[s].append(cs)
                self.eps[ce].append(e)
            return s, e
        cs, ce = self._build(node[1])
        self.eps[s].append(cs)
        self.eps[ce].append(e)
        if kind in ('star', 'plus'):
            self.eps[ce].append(cs)
        if kind in ('star', 'opt'):
            self.eps[s].append(e)
        return s, e

    def closure(self, states):
        seen, stack = set(states), list(states)
        while stack:
            for t in self.eps[stack.pop()]:
                if t not in seen:
                    seen.add(t)
                    stack.append(t)
        return seen

    def step(self, states, c):
        return self.closure({t for s in states for chars, neg, t in self.moves[s] if (c in chars) != neg})

    def fullmatch(self, text):
        current = self.closure({self.start})
        for c in text:
            current = self.step(current, c)
            if not current:
                return False
        return self.accept in current


OTHER = None  # DFA symbol for every character the pattern never mentions


class DFA:
    """Subset construction over the characters the pattern mentions plus OTHER."""

    def __init__(self, nfa):
        self.alphabet = set().union(*(chars for moves in nfa.moves for chars, _, _ in moves))
        symbols = [*self.alphabet, OTHER]
        start = frozenset(nfa.closure({nfa.start}))
        sets, index, self.trans = [start], {start: 0}, []
        for S in sets:  # sets grows while we walk it
            row = {}
            for sym in symbols:
                T = frozenset(nfa.step(S, sym))  # OTHER is in no char set, so only negated edges fire
                if not T:
                    continue
                if T not in index:
                    index[T] = len(sets)
                    sets.append(T)
                row[sym] = index[T]
            self.trans.append(row)
        self.accepting = [nfa.accept in S for S in sets]

    def fullmatch(self, text):
        state = 0
        for c in text:
            state = self.trans[state].get(c if c in self.alphabet else OTHER)
            if state is None:
                return False
        return self.accepting[state]


RE_TIMER = '''
import re, sys, time
r = re.compile(sys.argv[1])
t = time.perf_counter()
r.fullmatch(sys.argv[2])
print(time.perf_counter() - t)
'''


def time_python_re(pattern, text, cap):
    # Run in a child process so a catastrophic backtrack can be killed after `cap` seconds.
    try:
        out = subprocess.run([sys.executable, '-c', RE_TIMER, pattern, text],
                             capture_output=True, text=True, timeout=cap, check=True)
    except subprocess.TimeoutExpired:
        return None
    return float(out.stdout)


def timed(f):
    t = time.perf_counter()
    result = f()
    return result, time.perf_counter() - t


def fmt(seconds):
    return f'{seconds * 1000:.2f} ms' if seconds < 1 else f'{seconds:.2f} s'


def benchmark(ns=(5, 10, 15, 20, 22, 24, 26, 28, 30, 50, 100), cap=3.0):
    print(f'pattern (a?){{n}}a{{n}} against a{{n}}, python re capped at {cap:.0f} s\n')
    print(f'{"n":>4}  {"NFA sim":>10}  {"DFA build+run":>14}  {"python re":>14}')
    re_gave_up = False
    for n in ns:
        pattern, text = 'a?' * n + 'a' * n, 'a' * n
        ok_nfa, t_nfa = timed(lambda: NFA(pattern).fullmatch(text))
        ok_dfa, t_dfa = timed(lambda: DFA(NFA(pattern)).fullmatch(text))
        assert ok_nfa and ok_dfa
        t_re = None if re_gave_up else time_python_re(pattern, text, cap)
        re_gave_up = t_re is None
        re_col = fmt(t_re) if t_re is not None else f'> {cap:.0f} s'
        print(f'{n:>4}  {fmt(t_nfa):>10}  {fmt(t_dfa):>14}  {re_col:>14}', flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3:
        print(NFA(sys.argv[1]).fullmatch(sys.argv[2]))
    else:
        benchmark()
