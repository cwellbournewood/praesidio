#!/usr/bin/env bash
# Seed the 1.1 backlog into GitHub Issues using the `gh` CLI.
#
# WHY THIS EXISTS
#   The roadmap in docs/roadmap.md is the source of truth for *what* is
#   on the plate. This script materialises the 1.1 line-items as real
#   GitHub issues with consistent labels so the GitHub Projects board
#   can sort, filter, and burn-down against them.
#
# WHAT IT DOES
#   For each entry below it runs `gh issue create` with:
#     * a deterministic title
#     * a body that links back to docs/roadmap.md#11
#     * the labels: roadmap, milestone-1.1, kind/<X>, area/<Y>
#     * the `1.1` milestone (created if missing)
#
# HOW TO USE
#   1. Install gh: https://cli.github.com/
#   2. `gh auth login`
#   3. `gh repo set-default <org>/praesidio` from inside the repo, OR
#      pass `--repo <org>/<name>` to every invocation below.
#   4. Dry-run first: `DRY_RUN=1 bash scripts/seed-roadmap-issues.sh`
#   5. For real: `bash scripts/seed-roadmap-issues.sh`
#
# CAVEATS
#   * Idempotent on title match: if an open issue with the same title
#     already exists, it is skipped (not updated).
#   * Requires `roadmap`, `kind/feature`, `kind/connector`,
#     `area/connectors`, `area/agents`, `area/policy`, `area/ui`,
#     `area/observability`, `area/perf` labels to exist; create them
#     up-front with `gh label create <name>` or use the
#     `--create-label-if-missing` shortcut below.
#
# This script is committed for repeatability but is NOT executed by CI.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRY_RUN="${DRY_RUN:-0}"
MILESTONE="${MILESTONE:-1.1}"
BODY_URL="${BODY_URL:-https://github.com/<org>/praesidio/blob/main/docs/roadmap.md#11--next-minor-q4-2026}"

# ---- helpers --------------------------------------------------------------

ensure_label() {
  local name="$1" color="$2" desc="$3"
  if ! gh label list --limit 200 | grep -qE "^${name}\b"; then
    if [ "$DRY_RUN" = "1" ]; then
      echo "[dry-run] gh label create '${name}' --color '${color}' --description '${desc}'"
    else
      gh label create "$name" --color "$color" --description "$desc" || true
    fi
  fi
}

ensure_milestone() {
  local title="$1"
  if ! gh api "repos/{owner}/{repo}/milestones?state=open" --jq '.[].title' | grep -qx "$title"; then
    if [ "$DRY_RUN" = "1" ]; then
      echo "[dry-run] gh api -X POST repos/{owner}/{repo}/milestones -f title='${title}'"
    else
      gh api -X POST "repos/{owner}/{repo}/milestones" -f title="$title" >/dev/null
    fi
  fi
}

create_issue() {
  local title="$1"; shift
  local body_extra="$1"; shift
  local labels_csv="$1"; shift

  # Idempotency: skip if an open issue with this title already exists.
  if gh issue list --state open --search "in:title \"$title\"" --json title --jq '.[].title' \
       | grep -Fxq "$title"; then
    echo "SKIP (exists): $title"
    return 0
  fi

  local body
  body=$(cat <<EOF
${body_extra}

---
Tracked under [Praesidio roadmap → 1.1](${BODY_URL}). Auto-created by
\`scripts/seed-roadmap-issues.sh\`. Edits made here do not flow back to
the roadmap doc — keep them in sync manually until the doc is generated
from issues (post-1.1).
EOF
)

  if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] gh issue create --title '$title' --label '$labels_csv' --milestone '$MILESTONE'"
    echo "          body: ${body_extra}"
    return 0
  fi
  gh issue create \
    --title "$title" \
    --body  "$body" \
    --label "$labels_csv" \
    --milestone "$MILESTONE"
}

# ---- preflight ------------------------------------------------------------

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found. Install from https://cli.github.com/" >&2
  exit 2
fi

ensure_label roadmap          5319e7 "Tracked on the public roadmap"
ensure_label milestone-1.1    006b75 "Targeted for the 1.1 release"
ensure_label kind/feature     a2eeef "New user-visible capability"
ensure_label kind/connector   bfd4f2 "New upstream provider / DB connector"
ensure_label kind/sdk         d4c5f9 "Public SDK / plugin ABI work"
ensure_label area/connectors  c5def5 ""
ensure_label area/agents      c5def5 ""
ensure_label area/policy      c5def5 ""
ensure_label area/ui          c5def5 ""
ensure_label area/observability c5def5 ""
ensure_label area/perf        c5def5 ""
ensure_label area/vault       c5def5 ""

ensure_milestone "$MILESTONE"

# ---- the 1.1 backlog ------------------------------------------------------

create_issue \
  "Graduate vector-DB connectors to stable (Pinecone, pgvector, Weaviate, Qdrant)" \
  "Today these connectors live in preview. For 1.1 we want a stable API surface, namespace-aware policy scoping, and acceptance tests for each backend in CI." \
  "roadmap,milestone-1.1,kind/connector,area/connectors"

create_issue \
  "Add vector-DB connectors: Milvus and Chroma" \
  "Round out the connector list with two more popular open-source vector DBs. Share the existing connector ABI; ship example policies." \
  "roadmap,milestone-1.1,kind/connector,area/connectors"

create_issue \
  "Graduate agent governance: tool-call argument scan + response-side scan" \
  "Both detectors are wired in 1.0 (response-side scan covered by tests). For 1.1 the surface freezes: stable label space, documented disabling/override knobs, and a benchmark in bench/eval/." \
  "roadmap,milestone-1.1,kind/feature,area/agents"

create_issue \
  "Native MCP server adapter (Anthropic Model Context Protocol)" \
  "Expose Praesidio's DLP + policy engine as an MCP server so MCP-aware clients can scan tool inputs/outputs out of the box. Reuse the orchestrator path." \
  "roadmap,milestone-1.1,kind/feature,area/agents"

create_issue \
  "Provider: AWS Bedrock (Claude / Llama 3 / Mistral)" \
  "Add a Bedrock proxy adapter with IAM role-assumption auth. Stream + non-stream parity with the direct Anthropic / OpenAI providers." \
  "roadmap,milestone-1.1,kind/connector,area/connectors"

create_issue \
  "Per-tenant token-vault key rotation CLI" \
  "Operators need a supported way to rotate a tenant's vault HKDF salt without re-keying every token. Ship \`praesidio-vault rotate --tenant <id> --new-key <ref>\` with an audited re-wrap." \
  "roadmap,milestone-1.1,kind/feature,area/vault"

create_issue \
  "Web UI: visual policy authoring (rule builder + CEL test pad)" \
  "Today policy edits round-trip through YAML. For 1.1 ship a visual builder that produces the same YAML, plus a live CEL test pad backed by /admin/simulate." \
  "roadmap,milestone-1.1,kind/feature,area/ui,area/policy"

create_issue \
  "Custom detector SDK — stable plugin ABI" \
  "A Python plugin protocol so operators can ship their own detector without forking. Includes cookiecutter, ABI versioning rule, and a CI matrix in bench/eval/." \
  "roadmap,milestone-1.1,kind/sdk,area/policy"

create_issue \
  "Hierarchical rate-limit buckets (tenant -> group -> user)" \
  "Today the limiter is per-principal flat. Add nesting so a tenant cap can be enforced alongside per-user fairness. Export a burst-headroom metric." \
  "roadmap,milestone-1.1,kind/feature,area/perf"

echo
echo "Done. Review the issues in the GitHub Projects 'Praesidio 1.1' board."
