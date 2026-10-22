#!/bin/bash
set -euo pipefail
TASK_ROOT=$(cd "$(dirname "$0")/.." && pwd)
exec bash "$TASK_ROOT/scripts/deploy.sh" -e anyapps_repair_conflicts=true "$@"
