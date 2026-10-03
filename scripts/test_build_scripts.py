"""Exercise layer discovery and argv handling without starting a build."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildScriptsTest(unittest.TestCase):
    def run_layer(self, *args, listing=None):
        with tempfile.TemporaryDirectory() as directory:
            mock = Path(directory) / "colcon"
            mock.write_text("#!/usr/bin/env python3\nimport os,sys\n"
                            "if sys.argv[1:] == ['list','--base-paths','src']:\n"
                            " print(os.environ['MOCK_LIST'])\n"
                            "else:\n print(repr(sys.argv[1:]))\n")
            mock.chmod(0o755)
            env = dict(os.environ, PATH=directory + ':' + os.environ['PATH'],
                       MOCK_LIST=listing if listing is not None else
                       '\n'.join(f'{name}\tsrc/{layer}/folder\t(ros.ament_cmake)'
                                 for name, layer in [('actual_driver', 'communication'),
                                                     ('actual_sensor', 'perception'),
                                                     ('actual_control', 'execution'),
                                                     ('actual_app', 'application')]))
            return subprocess.run(['bash', str(ROOT / 'build_layer.bash'), *args],
                                  cwd=directory, env=env, capture_output=True, text=True)

    def test_aliases_discover_names_from_paths(self):
        for short, long, name in [('c', 'communication', 'actual_driver'),
                                  ('p', 'perception', 'actual_sensor'),
                                  ('e', 'execution', 'actual_control'),
                                  ('a', 'application', 'actual_app')]:
            for alias in (short, long):
                result = self.run_layer(alias, '--dry-run')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('--packages-up-to ' + name, result.stdout)

    def test_empty_invalid_and_multiple_layers_fail(self):
        for args, listing in [(('c',), ''), (('invalid',), None),
                              ((), None), (('c', 'p'), None)]:
            self.assertNotEqual(self.run_layer(*args, listing=listing).returncode, 0)

    def test_build_passes_all_selected_packages_as_separate_arguments(self):
        result = self.run_layer('e', listing=
                               'flight_control\tsrc/execution/one\t(type)\n'
                               'ego;echo BAD\tsrc/execution/two\t(type)\n'
                               'outside\tsrc/third_party/three\t(type)')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("'--packages-up-to', 'flight_control', 'ego;echo BAD'", result.stdout)
        self.assertNotIn("'outside'", result.stdout)


if __name__ == '__main__':
    unittest.main()
