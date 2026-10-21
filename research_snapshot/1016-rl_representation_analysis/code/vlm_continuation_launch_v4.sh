#!/usr/bin/env bash
set -euo pipefail
task_root=/mnt/workspace/ReCogDrive/1016-rl_representation_analysis
cd "$task_root"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONPATH="$task_root/code${PYTHONPATH:+:$PYTHONPATH}"
exec python -u -B code/vlm_continuation_node_v4.py --node "${1:?node}" --resume "${2:?resume directory}"
