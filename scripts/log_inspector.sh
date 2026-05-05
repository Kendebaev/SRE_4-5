#!/usr/bin/env bash
# =============================================================================
# log_inspector.sh — NexShop Automated Log Inspector
# Assignment 6: Automation in SRE and Capacity Planning
#
# Fetches the last 500 lines from every NexShop container and greps for
# critical error patterns, producing a structured incident report.
#
# Usage: bash scripts/log_inspector.sh [--tail N] [--save]
#   --tail N   : Override number of log lines to fetch (default: 500)
#   --save     : Save the full report to logs/incident_report_<timestamp>.txt
# =============================================================================

set -uo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Configuration ─────────────────────────────────────────────────────────────
TAIL_LINES=500
SAVE_REPORT=false
REPORT_FILE=""
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')

# Target containers (must match Terraform `name` values)
CONTAINERS=(
  "auth-service"
  "product-service"
  "order-service"
  "user-service"
  "user-chat-service"
  "nginx-gateway"
  "prometheus"
  "postgres"
)

# Critical patterns to grep for
PATTERNS=(
  "Exception"
  "Error"
  "error"
  "CRITICAL"
  "Connection refused"
  "password authentication failed"
  "Traceback"
  "OOM"
  "killed"
  "panic"
  "fatal"
  "timeout"
)

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tail)   TAIL_LINES="$2"; shift 2 ;;
    --save)   SAVE_REPORT=true; shift ;;
    *)        echo "Unknown option: $1"; exit 1 ;;
  esac
done

if $SAVE_REPORT; then
  mkdir -p logs
  REPORT_FILE="logs/incident_report_${TIMESTAMP}.txt"
  exec > >(tee -a "$REPORT_FILE") 2>&1
fi

# Build the grep pattern string (pipe-separated for -E)
GREP_PATTERN=$(IFS='|'; echo "${PATTERNS[*]}")

# ── Helpers ───────────────────────────────────────────────────────────────────
section() {
  echo ""
  echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${CYAN}${BOLD}  $1${NC}"
  echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}=================================================================${NC}"
echo -e "${BOLD}   NexShop Log Inspector — $(date '+%Y-%m-%d %H:%M:%S')         ${NC}"
echo -e "${BOLD}   Fetching last ${TAIL_LINES} lines per container              ${NC}"
echo -e "${BOLD}=================================================================${NC}"

TOTAL_HITS=0
declare -A CONTAINER_HITS

# ── Main loop ─────────────────────────────────────────────────────────────────
for container in "${CONTAINERS[@]}"; do
  section "Container: $container"

  # Check if container exists and is running
  STATUS=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "not_found")

  if [[ "$STATUS" == "not_found" ]]; then
    echo -e "${YELLOW}  [SKIP] Container '$container' does not exist on this host.${NC}"
    CONTAINER_HITS[$container]=0
    continue
  fi

  echo -e "  Status: ${BOLD}$STATUS${NC}"

  # Fetch logs and grep for critical patterns
  MATCHES=$(docker logs --tail "$TAIL_LINES" "$container" 2>&1 | grep -E "$GREP_PATTERN" || true)

  if [[ -z "$MATCHES" ]]; then
    echo -e "${GREEN}  [CLEAN]${NC} No critical patterns found in last ${TAIL_LINES} lines."
    CONTAINER_HITS[$container]=0
  else
    HIT_COUNT=$(echo "$MATCHES" | wc -l)
    CONTAINER_HITS[$container]=$HIT_COUNT
    TOTAL_HITS=$((TOTAL_HITS + HIT_COUNT))
    echo -e "${RED}  [!] Found ${HIT_COUNT} critical log line(s):${NC}"
    echo ""
    # Print each match with line numbering
    echo "$MATCHES" | head -50 | nl -ba | sed 's/^/    /'
    if [[ $HIT_COUNT -gt 50 ]]; then
      echo ""
      echo -e "${YELLOW}  ... (truncated — showing first 50 of ${HIT_COUNT} matches)${NC}"
    fi
  fi
done

# ── Summary Report ────────────────────────────────────────────────────────────
section "SUMMARY REPORT"

echo -e "  Timestamp : $TIMESTAMP"
echo -e "  Log lines : $TAIL_LINES per container"
echo ""
printf "  %-25s %s\n" "CONTAINER" "CRITICAL HITS"
printf "  %-25s %s\n" "─────────────────────────" "─────────────"

for container in "${CONTAINERS[@]}"; do
  hits="${CONTAINER_HITS[$container]:-0}"
  if [[ "$hits" -gt 0 ]]; then
    printf "  ${RED}%-25s %s${NC}\n" "$container" "$hits"
  else
    printf "  ${GREEN}%-25s %s${NC}\n" "$container" "$hits"
  fi
done

echo ""
echo -e "  Total critical lines found: ${BOLD}${TOTAL_HITS}${NC}"
echo ""

if [[ $TOTAL_HITS -gt 0 ]]; then
  echo -e "${RED}  ⚠  Action required: Review the containers flagged above.${NC}"
  echo -e "${YELLOW}  Tip: Run 'docker logs --tail 100 <container>' for full context.${NC}"
else
  echo -e "${GREEN}  ✓  All containers look clean. No critical patterns detected.${NC}"
fi

if $SAVE_REPORT; then
  echo ""
  echo -e "${CYAN}  Full report saved to: ${REPORT_FILE}${NC}"
fi

echo ""
