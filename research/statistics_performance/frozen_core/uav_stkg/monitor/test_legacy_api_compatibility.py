"""Run frozen legacy semantic/contract tests against the formal v33 imports.

Only import destinations change in memory. Test fixtures and assertions remain
the original bytes, and no historical test writes an output in these three suites.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    fixtures = Path(__file__).resolve().parents[3] / "data" / "monitor"
    for name in ["legacy_test_sampled_monitor.py", "legacy_test_sampled_data_contract.py", "legacy_test_metamorphic_monitor.py"]:
        path = fixtures / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("sampled_monitor", "sampled_data_contract"):
                node.module = "uav_stkg.monitor." + node.module
        namespace = {"__file__": str(path), "__name__": "legacy_import_compatibility"}
        exec(compile(tree, str(path), "exec"), namespace)
        for key, function in namespace.items():
            if key.startswith("test_") and callable(function):
                suite.addTest(unittest.FunctionTestCase(function, description=name + ":" + key))
    return suite
