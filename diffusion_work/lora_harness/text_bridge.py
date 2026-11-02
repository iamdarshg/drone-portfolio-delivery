"""Zero-new-weight experimental CPU export; opt-in, never called by preflight.

Exports only fixed literal Darsh. Runtime verification remains necessary before
lifting the harness training block. Does not load the unsupported FP8 file in Musubi.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from harness import ROOT, PIN, digest, environment, epath

COMFY_PIN = "9aac21f894a122ddb8d825c57ad61c0db5e630db"


def context_tensor(conditioning, token_count):
    import torch
    if len(conditioning) != 1:
        raise ValueError("Only one unscheduled fixed prompt supported")
    tensor = conditioning[0][0]
    if tensor.ndim != 3 or tensor.shape[0] != 1 or tensor.shape[2] != 4096:
        raise ValueError("Expected Comfy [1,L,4096] final UMT5 hidden states")
    if not 1 <= token_count <= 512 or tensor.shape[1] != 512:
        raise ValueError("Wan text length must be 512 before mask trimming")
    if not torch.isfinite(tensor).all():
        raise ValueError("Nonfinite conditioning")
    # Upstream zip(batch, context) strips batch dimension before writing each cache.
    # Trainer's varlen collator returns list[Li,4096], NOT [B,Li,4096].
    return tensor[0, :token_count].detach().cpu().to(torch.bfloat16).contiguous()


def export(dest):
    import psutil
    busy = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
            if p.pid != os.getpid() and ("blender" in (p.info["name"] or "").lower() or
                                        any(x in cmd for x in ("wan_compact.py", "wan_train_network.py"))):
                busy.append(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if busy or (ROOT / "GPU_INFERENCE.lock").exists():
        raise ValueError(f"Defer even CPU encoding while inference/Blender active: {busy}")
    checkout = ROOT / "ComfyUI"
    rev = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if rev != COMFY_PIN:
        raise ValueError("Comfy pin changed")
    weights = ROOT / "models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    manifest = json.loads((ROOT / "models/manifest.json").read_text())
    entry = next(x for x in manifest["files"] if Path(x["path"]).resolve() == weights.resolve())
    if not entry["verified"] or weights.stat().st_size != entry["size"]:
        raise ValueError("Approved encoder not verified")
    dest.mkdir(parents=True, exist_ok=False)
    os.environ.update(environment())
    for name in ("tmp", "hf", "torch", "cache"):
        (ROOT / name).mkdir(exist_ok=True)
    sys.path.insert(0, str(checkout))
    sys.argv = [sys.argv[0], "--cpu", "--disable-auto-launch", "--use-pytorch-cross-attention"]
    import torch
    import comfy.sd
    from transformers import T5Tokenizer
    from safetensors.torch import save_file, load_file
    torch.manual_seed(42)
    torch.set_num_threads(1)
    clip = comfy.sd.load_clip([str(weights)], clip_type=comfy.sd.CLIPType.WAN)
    tokenized = clip.tokenize("Darsh")
    pairs = tokenized["umt5xxl"]
    if len(pairs) != 1 or any(float(p[1]) != 1.0 for p in pairs[0]):
        raise ValueError("Only unweighted, one-chunk Darsh supported")
    comfy_ids = [int(p[0]) for p in pairs[0]]
    spiece = clip.tokenizer.umt5xxl.tokenizer.serialize_model()
    vocab = dest / "spiece.model"
    vocab.write_bytes(spiece.numpy().tobytes())
    # Same embedded UMT5 SentencePiece vocabulary. No remote tokenizer/config fetch.
    tokenizer = T5Tokenizer(vocab_file=str(vocab), extra_ids=0, legacy=True)
    hf = tokenizer("Darsh", padding="max_length", truncation=True, max_length=512,
                   add_special_tokens=True, return_attention_mask=True)
    if hf["input_ids"] != comfy_ids:
        raise ValueError("Tokenizer ID disagreement; cannot export semantic context")
    n = sum(hf["attention_mask"])
    if hf["attention_mask"] != [1]*n + [0]*(512-n) or comfy_ids[n-1] != 1:
        raise ValueError("Expected contiguous nonpadding tokens ending EOS=1")
    with torch.inference_mode():
        first = context_tensor(clip.encode_from_tokens_scheduled(tokenized), n)
        second = context_tensor(clip.encode_from_tokens_scheduled(tokenized), n)
    if not torch.equal(first, second):
        raise ValueError("Repeated fixed-prompt encoding differs")
    output = dest / "Darsh_wan_te.safetensors"
    save_file({"varlen_t5_bfloat16": first}, str(output), metadata={
        "architecture": "wan", "caption1": "Darsh", "format_version": "1.0.1"})
    if not torch.equal(first, load_file(str(output))["varlen_t5_bfloat16"]):
        raise ValueError("Cache roundtrip mismatch")
    report = {"prompt": "Darsh", "comfy_pin": COMFY_PIN, "musubi_pin": PIN,
              "encoder_sha256": digest(weights), "tokenizer_sha256": digest(vocab),
              "token_ids": comfy_ids, "attention_mask": hf["attention_mask"],
              "shape": list(first.shape), "dtype": str(first.dtype), "finite": True,
              "repeat_bit_equal": True, "cache_sha256": digest(output),
              "schema_verified": True, "native_bf16_numeric_equivalence": False,
              "note": "Scaled-FP8 quantized final hidden states, not exact native BF16 outputs; trainer consumption still untested"}
    (dest / "bridge_report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "text_bridge/Darsh_001")
    p.add_argument("--execute-cpu", action="store_true")
    a = p.parse_args()
    if not a.execute_cpu:
        print(json.dumps({"execute": False, "new_weight_bytes": 0,
                          "output": str(epath(a.output)), "requires_idle_gpu_workers": True}))
    else:
        print(json.dumps(export(epath(a.output)), indent=2))
