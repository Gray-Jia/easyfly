# Copyright 2026 EasyFly Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Run only as the parent of a newly started, isolated diagnostic process.
# Usage: gdb -q -batch --return-child-result -x scripts/shutdown_capture.gdb --args EXEC ARGS
set pagination off
set confirm off
set print thread-events off
handle SIGINT nostop noprint pass
handle SIGTERM nostop noprint pass
handle SIGSEGV stop print pass
handle SIGABRT stop print pass
run
python
import os
import pathlib

inferior = gdb.selected_inferior()
if inferior.threads():
    gdb.execute("bt 40")
    gdb.execute("thread apply all bt 20")
    gdb.execute("info registers")
    gdb.execute("x/i $pc")
    # Core files can be several GiB. Opt in and require an existing, explicitly
    # chosen output directory; never generate a core after normal child exit.
    if os.environ.get("EASYFLY_CAPTURE_CORE") == "1":
        directory = pathlib.Path(os.environ["EASYFLY_CAPTURE_DIR"]).resolve(strict=True)
        if not directory.is_dir():
            raise RuntimeError("EASYFLY_CAPTURE_DIR must be an existing directory")
        filename = pathlib.Path(gdb.current_progspace().filename).name
        target = directory / (filename + "." + str(inferior.pid) + ".core")
        if target.exists():
            raise RuntimeError("Refusing to overwrite an existing core: " + str(target))
        gdb.execute("generate-core-file " + str(target))
    # A stopped or crashed child is not a successful exit, irrespective of
    # launch's own return code or the default debugger return code.
    gdb.execute("quit 1")
end
