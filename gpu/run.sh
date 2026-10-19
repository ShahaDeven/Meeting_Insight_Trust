#!/usr/bin/env bash
# Puts pip-installed CUDA libs (cuDNN 9, cuBLAS 12) on the loader path for CTranslate2,
# then runs transcribe.py with whatever arguments were given.
set -euo pipefail
cd "$(dirname "$0")"

NV_LIBS=$(python -c "import glob, nvidia; print(':'.join(glob.glob(list(nvidia.__path__)[0] + '/*/lib')))" 2>/dev/null || true)
export LD_LIBRARY_PATH="${NV_LIBS}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

if [ -z "${HF_TOKEN:-}" ]; then
  echo "HF_TOKEN is not set. Run: export HF_TOKEN=hf_..." >&2
  exit 1
fi

python transcribe.py "$@"
