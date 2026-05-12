"""Smoke tests for the auto_expected rewriter.

These tests exercise the deterministic literal formatter, AST-based
EXPECTED_BY_CHAT rewrite, and the policy filter so the script can be
trusted before pointing it at real expected_results.py files.
"""

from __future__ import annotations

import argparse
import ast
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harness.auto_expected import (
    EXPECTED_DICT_NAME,
    _apply_policy,
    format_python_literal,
    load_expected_dict,
    rewrite_expected_file,
)


def _opts(**overrides) -> argparse.Namespace:
    base = {
        "only_missing": False,
        "overwrite_existing": False,
        "sort_keys": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class FormatPythonLiteralTests(unittest.TestCase):
    def test_scalar_repr(self) -> None:
        self.assertEqual(format_python_literal(None), "None")
        self.assertEqual(format_python_literal(True), "True")
        self.assertEqual(format_python_literal(False), "False")
        self.assertEqual(format_python_literal(42), "42")
        self.assertEqual(format_python_literal(25.0), "25.0")
        self.assertEqual(format_python_literal("hello"), '"hello"')

    def test_string_escaping_uses_double_quotes(self) -> None:
        out = format_python_literal({"k": 'a "quoted" word'})
        self.assertIn('"k": "a \\"quoted\\" word"', out)
        self.assertNotIn("'", out)

    def test_dict_preserves_insertion_order(self) -> None:
        value = {"b": 1, "a": 2}
        out = format_python_literal(value)
        self.assertEqual(out.index('"b"') < out.index('"a"'), True)

    def test_empty_containers(self) -> None:
        self.assertEqual(format_python_literal({}), "{}")
        self.assertEqual(format_python_literal([]), "[]")

    def test_nested_round_trip(self) -> None:
        value = {
            "file.json": {
                "data": [
                    {"items": [{"sr_no": 1, "qty": 5.0, "tags": ["a", "b"]}], "vendor": "X"},
                ],
            }
        }
        rendered = format_python_literal(value)
        parsed = ast.literal_eval(rendered)
        self.assertEqual(parsed, value)

    def test_unsupported_type_raises(self) -> None:
        with self.assertRaises(TypeError):
            format_python_literal({"k": object()})


SAMPLE_HEADER = '"""Expected results module docstring."""\n\n'


def _write_sample(tmp: Path, body: str) -> Path:
    src = SAMPLE_HEADER + body
    path = tmp / "expected_results.py"
    path.write_text(src, encoding="utf-8")
    return path


class LoadExpectedDictTests(unittest.TestCase):
    def test_loads_assign(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            path = _write_sample(
                tmp,
                f'{EXPECTED_DICT_NAME} = {{\n    "a.json": {{"k": 1}},\n}}\n',
            )
            data = load_expected_dict(path)
            self.assertEqual(data, {"a.json": {"k": 1}})

    def test_loads_annotated_assign(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            path = _write_sample(
                tmp,
                f'{EXPECTED_DICT_NAME}: dict[str, list[str]] = {{\n    "a.json": ["d1", "d2"],\n}}\n',
            )
            data = load_expected_dict(path)
            self.assertEqual(data, {"a.json": ["d1", "d2"]})

    def test_missing_assignment_raises(self) -> None:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            path = _write_sample(tmp, "SOMETHING_ELSE = {}\n")
            with self.assertRaises(SystemExit):
                load_expected_dict(path)


class RewriteExpectedFileTests(unittest.TestCase):
    def test_preserves_prologue_and_helper_function(self) -> None:
        body = textwrap.dedent(
            f"""\
            {EXPECTED_DICT_NAME} = {{
                "a.json": {{"k": 1}},
            }}


            def get_expected_for_chat(name):
                return {EXPECTED_DICT_NAME}.get(name)
            """
        )
        with TemporaryDirectory() as td:
            tmp = Path(td)
            path = _write_sample(tmp, body)

            new_value = {"a.json": {"k": 2}, "b.json": {"k": 3}}
            updated = rewrite_expected_file(path, new_value)

            self.assertTrue(updated.startswith(SAMPLE_HEADER))
            self.assertIn("def get_expected_for_chat", updated)

            tree = ast.parse(updated)
            ns: dict[str, object] = {}
            exec(compile(tree, str(path), "exec"), ns)
            self.assertEqual(ns[EXPECTED_DICT_NAME], new_value)

    def test_preserves_annotation(self) -> None:
        body = (
            f'{EXPECTED_DICT_NAME}: dict[str, list[str]] = {{\n'
            f'    "a.json": ["d1"],\n'
            f'}}\n'
        )
        with TemporaryDirectory() as td:
            tmp = Path(td)
            path = _write_sample(tmp, body)
            updated = rewrite_expected_file(path, {"a.json": ["d1", "d2"]})
            self.assertIn(f"{EXPECTED_DICT_NAME}: dict[str, list[str]] = {{", updated)
            ns: dict[str, object] = {}
            exec(compile(ast.parse(updated), str(path), "exec"), ns)
            self.assertEqual(ns[EXPECTED_DICT_NAME], {"a.json": ["d1", "d2"]})


class ApplyPolicyTests(unittest.TestCase):
    def test_new_entries_added(self) -> None:
        merged, actions = _apply_policy({}, {"a.json": 1}, _opts())
        self.assertEqual(merged, {"a.json": 1})
        self.assertEqual(actions, [("a.json", "new")])

    def test_existing_unchanged_is_noop(self) -> None:
        merged, actions = _apply_policy({"a.json": 1}, {"a.json": 1}, _opts(overwrite_existing=True))
        self.assertEqual(merged, {"a.json": 1})
        self.assertEqual(actions, [("a.json", "skip:unchanged")])

    def test_existing_changed_requires_overwrite(self) -> None:
        merged, actions = _apply_policy({"a.json": 1}, {"a.json": 2}, _opts())
        self.assertEqual(merged, {"a.json": 1})
        self.assertEqual(actions, [("a.json", "skip:exists")])

        merged, actions = _apply_policy({"a.json": 1}, {"a.json": 2}, _opts(overwrite_existing=True))
        self.assertEqual(merged, {"a.json": 2})
        self.assertEqual(actions, [("a.json", "replace")])

    def test_only_missing_skips_existing(self) -> None:
        merged, actions = _apply_policy({"a.json": 1}, {"a.json": 2}, _opts(only_missing=True))
        self.assertEqual(merged, {"a.json": 1})
        self.assertEqual(actions, [("a.json", "skip:only-missing")])

    def test_sort_keys_orders_output(self) -> None:
        merged, _ = _apply_policy({"b.json": 2}, {"a.json": 1}, _opts(sort_keys=True))
        self.assertEqual(list(merged.keys()), ["a.json", "b.json"])


if __name__ == "__main__":
    unittest.main()
