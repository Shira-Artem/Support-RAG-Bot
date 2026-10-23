"""Run the existing read-only Stage3 benchmark with HEAD's pre-P0.2 policy.

Loads two baseline Python modules from Git into memory; does not checkout,
reset, index or write the working tree. All other code and fixtures are shared
with the current benchmark, isolating the P0.2 policy change.
"""
from __future__ import annotations

import os
from pathlib import Path
import runpy
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["GROQ_API_KEY"] = ""


def load_head_module(name: str, path: str) -> None:
    source = subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT)
    module = types.ModuleType(name)
    module.__file__ = f"HEAD:{path}"
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)


load_head_module("app.procedure_policy", "app/procedure_policy.py")
load_head_module("app.retrieval_pipeline", "app/retrieval_pipeline.py")
runpy.run_module("scripts.compare_retrieval_stage3", run_name="__main__")
