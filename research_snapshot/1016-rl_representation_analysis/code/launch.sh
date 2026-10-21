#!/usr/bin/env bash
set -euo pipefail
task_root=/mnt/workspace/ReCogDrive/1016-rl_representation_analysis
cd "$task_root"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONPATH="$task_root/code${PYTHONPATH:+:$PYTHONPATH}"
node_id="${1:?Pass independent node index}"
run_id="${2:?Pass frozen run id}"
exec python -B code/coordinate.py --node-id "$node_id" --run "$run_id" --devices 16 --nodes 2
