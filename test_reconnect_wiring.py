"""The 8/17 lesson: a filter that exists but is never called is prose.

These assert the sweep is wired into bot.py's startup path, not just present
on disk. A module can be perfect and unreachable.
"""
import ast
import unittest
from pathlib import Path


class TestWiredIntoStartup(unittest.TestCase):
    def setUp(self):
        self.src = Path(__file__).parent.joinpath("bot.py").read_text()
        self.tree = ast.parse(self.src)

    def test_module_is_imported(self):
        self.assertIn("import reconnect_sweep", self.src)

    def test_startup_is_called_from_main(self):
        main = next(
            n for n in ast.walk(self.tree)
            if isinstance(n, ast.FunctionDef) and n.name == "main"
        )
        calls = [
            n for n in ast.walk(main)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "startup"
            and getattr(n.func.value, "id", None) == "reconnect_sweep"
        ]
        self.assertEqual(len(calls), 1, "reconnect_sweep.startup() not called exactly once in main()")

    def test_startup_runs_before_the_blocking_server_loop(self):
        # flask_app.run() never returns; anything after it is dead code.
        self.assertLess(
            self.src.index("reconnect_sweep.startup("),
            self.src.index("flask_app.run("),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
