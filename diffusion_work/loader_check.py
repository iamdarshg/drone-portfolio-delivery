"""CPU import/format support test, no GPU allocation or weight download."""
import sys
from pathlib import Path
from storage import configure_storage

configure_storage(create=True)
sys.path.insert(0, "E:/OneLine_diffusion/ComfyUI")
sys.argv = [sys.argv[0], "--cpu"]
import comfy.sd
import comfy.text_encoders.wan
import comfy.text_encoders.sd3_clip

source = Path("E:/OneLine_diffusion/ComfyUI/comfy/text_encoders/wan.py").read_text()
assert "t5xxl_scaled_fp8" in source
print("CPU loader import OK; CLIPType.WAN:", comfy.sd.CLIPType.WAN)
print("Wan te accepts t5xxl_scaled_fp8; actual checkpoint load remains a separate test")
