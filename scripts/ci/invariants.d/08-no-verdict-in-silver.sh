#!/usr/bin/env bash
#
# REQ-D-07 — the silver read models carry inputs, not verdicts.
#
# Candidate G owns verdicts; D owns the numbers they are computed from. A threshold
# baked into a read model moves that decision into Pod 3's DDL, where nobody
# reviewing a detection rule would think to look for it.
#
# WHAT THIS CAN AND CANNOT PROVE. It proves no *literal* threshold, band, severity
# or escalation appears in the DDL. It cannot prove the models encode no *opinion* —
# "does this read model decide what is anomalous?" is a review question, not a grep.
# A column named `p99_over_budget` would pass this assert and still be a verdict.
#
# Numbered 08: the ticket (T29) asked for 07, which is now
# 07-silver-mv-determinism.sh, which in turn asked for 06, already taken by T16.
#
# Comments are stripped before matching, deliberately. The migration's header says
# "no threshold, band, severity or escalation literal appears below" — prose
# documenting the property is evidence of it, not a violation. Matching comments
# would make the file fail for explaining itself.

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
TARGET="$ROOT/infra/clickhouse/migrations/0005_silver_watcher_models.sql"

#: Words that only appear in DDL if the model is deciding something.
VERDICT='threshold|severity|escalat|verdict|anomal|alert|breach|sla|slo|z_?score|is_bad|too_(high|low|slow)|warn|critical'

if [[ ! -f "$TARGET" ]]; then
    echo "missing: ${TARGET#"$ROOT"/}"
    exit 1
fi

# `--` comments out, then one record per statement so a hit names its object.
stripped="$(sed 's/--.*$//' "$TARGET")"

if hits="$(printf '%s' "$stripped" | grep -inE "($VERDICT)" || true)"; [[ -n "$hits" ]]; then
    echo "verdict literal in the silver read models (REQ-D-07):"
    printf '%s\n' "$hits" | sed 's/^/  /'
    echo "  Candidate G owns verdicts; D owns the inputs they read."
    exit 1
fi

echo "no verdict literal in the silver read models; D carries inputs only"
exit 0
