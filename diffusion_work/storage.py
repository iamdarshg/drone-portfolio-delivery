"""Process-local E: storage policy; never modifies persistent environment settings."""
import os
from pathlib import Path
import shutil

DEFAULT_ROOT = Path("E:/OneLine_diffusion")


def configure_storage(root=DEFAULT_ROOT, create=False):
    root = Path(root).resolve()
    if root.drive.upper() != "E:":
        raise ValueError("All diffusion bulk storage must be on E:")
    if not Path("E:/").is_dir():
        raise RuntimeError("E: is unavailable; refusing fallback to C: or D:")
    paths = {name: root / name for name in
             ("hf", "datasets", "checkpoints", "videos", "intermediates", "tmp", "pip", "torch")}
    if create:
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
    # Set before importing ML libraries. Overrides inherited cache paths for this
    # process and children only, never user/machine environment or global config.
    values = {"HF_HOME": paths["hf"], "HF_HUB_CACHE": paths["hf"] / "hub",
              "HUGGINGFACE_HUB_CACHE": paths["hf"] / "hub",
              "HF_DATASETS_CACHE": paths["datasets"] / "hf_cache",
              "HF_XET_CACHE": paths["hf"] / "xet", "TORCH_HOME": paths["torch"],
              "TORCHINDUCTOR_CACHE_DIR": paths["torch"] / "inductor",
              "TRITON_CACHE_DIR": paths["torch"] / "triton",
              "XDG_CACHE_HOME": root / "cache", "IMAGEIO_USERDIR": root / "imageio",
              "PIP_CACHE_DIR": paths["pip"], "TMP": paths["tmp"],
              "TEMP": paths["tmp"], "TMPDIR": paths["tmp"]}
    for key, value in values.items():
        os.environ[key] = str(value)
    return paths, shutil.disk_usage("E:/").free
