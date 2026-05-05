#!/usr/bin/env bash
# =============================================================================
# validate_config.sh — NexShop Pre-Deployment Configuration Validator
# Assignment 6: Automation in SRE and Capacity Planning
#
# Usage: bash scripts/validate_config.sh
# Run this script from the project root BEFORE any `terraform apply`.
# =============================================================================

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Colour

PASS=0
FAIL=0

pass() { echo -e "${GREEN}  [PASS]${NC} $1"; ((PASS++)); }
fail() { echo -e "${RED}  [FAIL]${NC} $1"; ((FAIL++)); }
info() { echo -e "${CYAN}  [INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}  [WARN]${NC} $1"; }

echo ""
echo -e "${CYAN}=================================================================${NC}"
echo -e "${CYAN}   NexShop — Pre-Deployment Configuration Validator              ${NC}"
echo -e "${CYAN}=================================================================${NC}"
echo ""

# ── Step 1: Locate the .env file ─────────────────────────────────────────────
ENV_FILE=".env"

echo "── Step 1: Checking .env file existence ──"
if [[ -f "$ENV_FILE" ]]; then
  pass ".env file found at: $(realpath "$ENV_FILE")"
else
  fail ".env file NOT found. Expected at: $(pwd)/.env"
  echo ""
  echo -e "${RED}  Cannot continue without .env. Aborting.${NC}"
  exit 1
fi
echo ""

# ── Step 2: Source the .env and validate critical variables ───────────────────
echo "── Step 2: Validating critical environment variables ──"

# Load variables (ignore export/comment lines safely)
set -a
# shellcheck disable=SC1090
source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$')
set +a

# List of required variable names
REQUIRED_VARS=(
  "POSTGRES_USER"
  "POSTGRES_PASSWORD"
  "POSTGRES_DB"
  "SECRET_KEY"
)

for var in "${REQUIRED_VARS[@]}"; do
  value="${!var:-}"
  if [[ -z "$value" ]]; then
    fail "Variable '$var' is MISSING or EMPTY in .env"
  else
    # Mask secrets — show only first 3 chars
    masked="${value:0:3}$(printf '*%.0s' $(seq 1 $((${#value} - 3))))"
    pass "Variable '$var' is set → ${masked}"
  fi
done
echo ""

# ── Step 3: Validate SECRET_KEY strength ─────────────────────────────────────
echo "── Step 3: Secret strength check ──"
SECRET_KEY="${SECRET_KEY:-}"
if [[ ${#SECRET_KEY} -lt 32 ]]; then
  fail "SECRET_KEY is shorter than 32 characters — use a stronger key!"
else
  pass "SECRET_KEY length is ${#SECRET_KEY} characters — OK"
fi
echo ""

# ── Step 4: Check required files exist ───────────────────────────────────────
echo "── Step 4: Checking required config files ──"
REQUIRED_FILES=(
  "prometheus/prometheus.yml"
  "prometheus/alert.rules.yml"
  "nginx/nginx.conf"
  "terraform/main.tf"
  "grafana/datasources.yml"
)

for f in "${REQUIRED_FILES[@]}"; do
  if [[ -f "$f" ]]; then
    pass "File exists: $f"
  else
    fail "File MISSING: $f"
  fi
done
echo ""

# ── Step 5: Validate prometheus.yml references alert.rules.yml ───────────────
echo "── Step 5: Checking Prometheus alert rules reference ──"
if grep -q "alert.rules.yml" "prometheus/prometheus.yml" 2>/dev/null; then
  pass "prometheus.yml references alert.rules.yml"
else
  warn "prometheus.yml does NOT reference alert.rules.yml — alerts won't fire!"
fi
echo ""

# ── Step 6: Docker daemon reachability ───────────────────────────────────────
echo "── Step 6: Checking Docker daemon ──"
if docker info &>/dev/null; then
  pass "Docker daemon is reachable"
else
  fail "Docker daemon is NOT reachable. Is Docker running?"
fi
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────
echo -e "${CYAN}=================================================================${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  |  ${RED}${FAIL} failed${NC}"
echo -e "${CYAN}=================================================================${NC}"
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo -e "${RED}  Pre-deployment validation FAILED. Fix the issues above before applying Terraform.${NC}"
  exit 1
else
  echo -e "${GREEN}  All checks passed. Safe to run: terraform apply${NC}"
  exit 0
fi
