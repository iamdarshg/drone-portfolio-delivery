"""Only the approved compact Wan bundle; resumable direct-to-E downloads."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
from storage import configure_storage

REPO = "Comfy-Org/Wan_2.1_ComfyUI_repackaged"
REV = "123acf1cc74bccbb9bfff8ac1ee72edc08c2341d"
FILES = {
    "split_files/diffusion_models/wan2.1_t2v_1.3B_bf16.safetensors": 2838104528,
    "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors": 6735906897,
    "split_files/vae/wan_2.1_vae.safetensors": 253815318,
}


def main():
    paths, free = configure_storage(create=True)
    root = paths["hf"].parent / "models"
    root.mkdir(exist_ok=True)
    data = json.load(urllib.request.urlopen(f"https://huggingface.co/api/models/{REPO}/revision/{REV}?blobs=true"))
    assert data["sha"] == REV and data["cardData"]["license"] == "apache-2.0"
    inventory = {f["rfilename"]: f for f in data["siblings"]}
    assert free > sum(FILES.values()) + 5_000_000_000, "Insufficient E: disk headroom"
    manifest = dict(repo=REPO, revision=REV, license="apache-2.0", total_bytes=sum(FILES.values()),
                    storage_policy="Direct .part then atomic rename, no second HF model cache copy", files=[])
    for name, size in FILES.items():
        item = inventory[name]
        assert item["size"] == size
        expected = item["lfs"]["sha256"]
        dest = root / name.removeprefix("split_files/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        if not dest.exists():
            url = f"https://huggingface.co/{REPO}/resolve/{REV}/{name}?download=true"
            # curl owns retry/resume; --fail prevents saving HTTP errors as weights.
            subprocess.run(["curl.exe", "--silent", "--show-error", "--fail", "--location", "--retry", "5", "--retry-delay", "5",
                            "--continue-at", "-", "--output", str(part), url], check=True)
            assert part.stat().st_size == size, "Incomplete download; resume on next run"
        check = dest if dest.exists() else part
        digest = hashlib.file_digest(check.open("rb"), "sha256").hexdigest()
        assert digest == expected, f"Hash mismatch: {check}; do not load"
        if not dest.exists():
            part.rename(dest)
        manifest["files"].append(dict(path=str(dest), size=size, sha256=digest, verified=True))
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("Verified", dest, size, flush=True)


if __name__ == "__main__":
    main()
