# Copyright 2026 EasyFly Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Check compatibility build boundaries without compiling, launching or changing PX4."""

import importlib.util
from pathlib import Path
from unittest import mock

import pytest

SOURCE = Path(__file__).parents[1] / 'scripts/prepare_px4_hrt.py'
SPEC = importlib.util.spec_from_file_location('prepare_px4_hrt', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_compile_preserves_production_flags():
    """Do not substitute native-probe flags in the real lockstep binary."""
    entry = {'file': '/px4/drv_hrt.cpp',
             'command': 'c++ -DENABLE_LOCKSTEP_SCHEDULER -O2 -g '
                        '-o original.o -c /px4/drv_hrt.cpp'}
    assert MODULE.compile_command(entry, Path('/local/drv_hrt.cpp.o'), Path('/local/patched')) == [
        'c++', '-DENABLE_LOCKSTEP_SCHEDULER', '-O2', '-g', '-o', '/local/drv_hrt.cpp.o',
        '-c', '/local/patched']
    for cmd in ['c++ -o original.o /wrong.cpp', 'c++ -o a -o b -c /px4/drv_hrt.cpp']:
        with pytest.raises(ValueError):
            MODULE.compile_command({**entry, 'command': cmd}, Path('/obj'), Path('/patched'))


def test_both_link_group_passes_use_only_local_archive():
    """PX4 lists the archive twice to resolve static-library cycles; replace both."""
    line = f': && c++ main.o -o bin/px4 {MODULE.LAYER_PATH} {MODULE.LAYER_PATH} && cd /px4/bin'
    result = MODULE.link_command(line, Path('/local/px4'), Path('/local/layer.a'))
    assert result == ['c++', 'main.o', '-o', '/local/px4', '/local/layer.a', '/local/layer.a']
    for bad in ['c++ main.o -o bin/px4', ': && c++ -o bin/px4 ' + MODULE.LAYER_PATH]:
        with pytest.raises(ValueError):
            MODULE.link_command(bad, Path('/local/px4'), Path('/local/layer.a'))


def test_changed_input_never_patches_or_creates_output(tmp_path):
    """An unreviewed PX4 installation cannot silently receive this pinned patch."""
    source, output = tmp_path / 'source', tmp_path / 'output'
    source.mkdir()
    with mock.patch.object(MODULE, 'digest', return_value='wrong'), \
            mock.patch.object(MODULE.subprocess, 'run') as run:
        with pytest.raises(ValueError, match='unsupported PX4'):
            MODULE.prepare(source, output, tmp_path)
        run.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize('target', ['source', 'source/nested', 'occupied'])
def test_reused_or_overlapping_output_is_rejected(tmp_path, target):
    """No source tree, ancestor or existing user data becomes a writable build target."""
    source = tmp_path / 'source'
    source.mkdir()
    output = tmp_path / target
    if target == 'occupied':
        output.mkdir()
    values = [MODULE.HRT_SHA256, MODULE.BINARY_SHA256]
    with mock.patch.object(MODULE, 'digest', side_effect=values), \
            mock.patch.object(MODULE.subprocess, 'run') as run:
        with pytest.raises(ValueError, match='new independent'):
            MODULE.prepare(source, output, tmp_path)
        run.assert_not_called()
