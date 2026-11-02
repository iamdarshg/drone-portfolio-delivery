"""CLI import/flag smoke ONLY. Hides GPU; does not instantiate any model.

Wan's upstream T5 constructor evaluates cuda.current_device() in a default
argument at import. Stub that device-index query ONLY for this --help check.
This is not used by training/encoding and does not claim their feasibility.
"""
import json
import os
from pathlib import Path
import runpy
import sys
import traceback
from harness import ROOT, TRAINER, environment

os.environ.update(environment())
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
sys.path.insert(0, str(TRAINER / "src"))
import torch

torch.cuda.current_device = lambda: 0
sys.argv = ["wan_train_network.py", "--help"]
try:
    runpy.run_module("musubi_tuner.wan_train_network", run_name="__main__")
except SystemExit as exc:
    if exc.code not in (0, None):
        raise
finally:
    print(json.dumps({"cpu_help_only": True, "cuda_initialized": torch.cuda.is_initialized(),
                      "no_weights_loaded": True}), file=sys.stderr)
