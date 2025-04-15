import random
import re
import time

import pytest

from regex_engine import DFA, NFA, RegexError


def matches(pattern, text):
    nfa = NFA(pattern)
    a, b = nfa.fullmatch(text), DFA(nfa).fullmatch(text)
    assert a == b, (pattern, text)
    return a


@pytest.mark.parametrize('pattern, text, expected', [
    ('abc', 'abc', True), ('abc', 'ab', False),
    ('a|bc', 'bc', True), ('ab|cd', 'ad', False),
    ('a*', '', True), ('a*', 'aaaa', True), ('a+', '', False),
    ('colou?r', 'color', True), ('colou?r', 'colour', True),
    ('(ab)*c', 'ababc', True), ('(ab)*c', 'abac', False),
    ('a.c', 'axc', True), ('a.c', 'a\nc', False),
    ('[a-c]+', 'cab', True), ('[a-c]+', 'cad', False),
    ('[^a-c]x', 'zx', True), ('[^a-c]x', 'bx', False),
    ('[-a]', '-', True), ('[]a]', ']', True), (r'a\*b', 'a*b', True),
    ('(a|)b', 'b', True), ('()', '', True), ('(a|b)*abb', 'babaabb', True),
])
def test_examples(pattern, text, expected):
    assert matches(pattern, text) == expected


@pytest.mark.parametrize('bad', ['(', 'a)', '*a', 'a|+', '[ab', '[z-a]', 'a\\'])
def test_parse_errors(bad):
    with pytest.raises(RegexError):
        NFA(bad)


def test_pathological_pattern_is_fast():
    n = 100
    t = time.perf_counter()
    assert matches('a?' * n + 'a' * n, 'a' * n)
    assert not matches('a?' * n + 'a' * n, 'a' * (n - 1))
    assert time.perf_counter() - t < 5


ATOMS = ['a', 'b', 'c', '.', '[ab]', '[^a]', '[a-b]', '[b-d]', '[^bc]', r'\.']


def random_pattern(rng, depth):
    r = rng.random()
    if depth == 0 or r < 0.25:
        return rng.choice(ATOMS)
    sub = lambda: random_pattern(rng, depth - 1)
    if r < 0.5:
        return sub() + sub()
    if r < 0.65:
        return f'({sub()}|{sub()})'
    if r < 0.7:
        return f'({sub()}|)'
    if r < 0.95:
        return f'({sub()}){rng.choice("*+?")}'
    return f'({sub()})'


def test_agrees_with_python_re():
    rng = random.Random(1234)
    checked = 0
    for _ in range(800):
        pattern = random_pattern(rng, 4)
        nfa = NFA(pattern)
        dfa = DFA(nfa)
        py = re.compile(pattern)
        for _ in range(25):
            text = ''.join(rng.choice('abcd.\n') for _ in range(rng.randint(0, 7)))
            want = py.fullmatch(text) is not None
            assert nfa.fullmatch(text) == want, (pattern, text)
            assert dfa.fullmatch(text) == want, (pattern, text)
            checked += 1
    assert checked == 20000
