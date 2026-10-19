#!/usr/bin/env bash
# One-time pod setup: ffmpeg + GPU deps, keeping the template's torch build untouched.
set -euo pipefail
cd "$(dirname "$0")"

apt-get update -qq && apt-get install -y -qq ffmpeg > /dev/null

TORCH=$(python -c "import torch; print(torch.__version__.split('+')[0])")
echo "Template torch: $TORCH"
pip install -q -r requirements-gpu.txt "torch==$TORCH"

python - <<'EOF'
import torch, ctranslate2, faster_whisper, pyannote.audio
print("torch", torch.__version__, "| cuda", torch.version.cuda, "| cudnn", torch.backends.cudnn.version())
print("gpu", torch.cuda.get_device_name(0), "capability", torch.cuda.get_device_capability(0))
print("ctranslate2", ctranslate2.__version__, "| cuda devices", ctranslate2.get_cuda_device_count())
print("faster-whisper", faster_whisper.__version__, "| pyannote.audio", pyannote.audio.__version__)
EOF
echo "Setup OK. Next: bash gpu/run.sh --smoke"
