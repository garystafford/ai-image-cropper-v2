"""Quick GPU test script"""

import torch

print("=" * 60)
print("GPU STATUS CHECK")
print("=" * 60)
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f">>> GPU WORKING: {torch.cuda.get_device_name(0)}")
    print(f"CUDA version: {torch.version.cuda}")
else:
    print(">>> GPU NOT DETECTED")
    print("\nTo fix:")
    print(
        "uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121"
    )
print("=" * 60)
