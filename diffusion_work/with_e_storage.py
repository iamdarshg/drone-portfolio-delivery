"""Launch a reviewed trainer/tool with process-local E: caches and E: cwd.

Example: python diffusion_work/with_e_storage.py -- E:/OneLine_diffusion/venv/Scripts/python.exe E:/OneLine_diffusion/trainer/train.py --help
Output/data/checkpoint CLI arguments still MUST explicitly point to E:.
"""
import subprocess
import sys
from storage import configure_storage

if __name__ == "__main__":
    command = sys.argv[1:]
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise SystemExit("Pass an explicit reviewed command after --")
    paths, _ = configure_storage(create=True)
    raise SystemExit(subprocess.call(command, cwd=paths["intermediates"]))
