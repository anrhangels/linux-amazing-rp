#!/usr/bin/env python3
"""Start the installed compatibility profile on workspace 1 without activating it."""
from pathlib import Path
import json,shlex,subprocess
command="python3 "+shlex.quote(str(Path.home()/".local/share/linux-amazing-rp/compat-20261109/run.py"))
raise SystemExit(subprocess.call(["hyprctl","eval","hl.exec_cmd("+json.dumps(command)+", {workspace=\"1 silent\", no_initial_focus=true})"]))
