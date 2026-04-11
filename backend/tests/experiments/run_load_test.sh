#!/usr/bin/env bash
# M5-4: Locust load test at multiple K values.
# Collects p50 / p95 / p99 / RPS per endpoint and prints a summary table.
#
# Usage:
#   export ALB_URL=http://<your-alb-dns-name>
#   bash tests/experiments/run_load_test.sh
#
# K values: 10, 50, 100, 500, 1000, 10000
# For large K, spawn-rate is capped at 200/s and run-time is extended
# so all users have time to start before measurements begin.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCUSTFILE="$SCRIPT_DIR/locustfile.py"
RESULTS_DIR="$(cd "$SCRIPT_DIR/../../docs/load-test-results" 2>/dev/null || \
               { mkdir -p "$SCRIPT_DIR/../../docs/load-test-results" && \
                 cd "$SCRIPT_DIR/../../docs/load-test-results"; } && pwd)"

mkdir -p "$RESULTS_DIR"

if [ -z "${ALB_URL:-}" ]; then
    echo "ERROR: Set ALB_URL first:"
    echo "  export ALB_URL=http://\$(aws elbv2 describe-load-balancers \\"
    echo "    --region us-west-2 \\"
    echo "    --query 'LoadBalancers[?LoadBalancerName==\`flair2-dev-alb\`].DNSName' \\"
    echo "    --output text)"
    exit 1
fi

echo "=== M5-4 Locust Load Test ==="
echo "Target:  $ALB_URL"
echo "Results: $RESULTS_DIR"
echo "K values: 10, 50, 100, 500, 1000, 10000"
echo ""

# ── Per-K config ────────────────────────────────────────────────────────────
# spawn_rate: how fast users are added per second (capped for large K)
# run_time: total test duration — large K needs more time to fully ramp up

declare -A SPAWN_RATE=( [10]=10 [50]=50 [100]=100 [500]=100 [1000]=200 [10000]=200 )
declare -A RUN_TIME=(   [10]="60s" [50]="60s" [100]="60s" [500]="90s" [1000]="120s" [10000]="180s" )

for K in 10 50 100 500 1000 10000; do
    echo "--- K=${K} users  spawn-rate=${SPAWN_RATE[$K]}/s  run-time=${RUN_TIME[$K]} ---"
    locust -f "$LOCUSTFILE" \
        --host "$ALB_URL" \
        --users "$K" \
        --spawn-rate "${SPAWN_RATE[$K]}" \
        --run-time "${RUN_TIME[$K]}" \
        --headless \
        --csv="$RESULTS_DIR/k${K}" \
        --csv-full-history \
        2>&1 | grep -E "(Aggregated|POST|GET|failures)" | head -10
    echo ""
done

# ── Summary table ────────────────────────────────────────────────────────────
# Parse *_stats.csv files (Locust CSV columns):
#   Method,Name,# Requests,# Failures,Median,Average,Min,Max,
#   Average size,Current RPS,Current Failures/s,
#   50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo " M5-4 Summary — POST /api/pipeline/start"
echo "════════════════════════════════════════════════════════════════════════"
printf "%-8s %8s %8s %8s %8s %10s %8s\n" "K" "p50(ms)" "p95(ms)" "p99(ms)" "Avg(ms)" "RPS" "Errors"
echo "------------------------------------------------------------------------"

for K in 10 50 100 500 1000 10000; do
    CSV="$RESULTS_DIR/k${K}_stats.csv"
    if [ ! -f "$CSV" ]; then
        printf "%-8s  (no results file)\n" "K=$K"
        continue
    fi
    # Find the POST /api/pipeline/start row (or Aggregated if not found)
    ROW=$(grep "pipeline/start" "$CSV" 2>/dev/null | head -1 || \
          grep "Aggregated"     "$CSV" 2>/dev/null | tail -1 || true)
    if [ -z "$ROW" ]; then
        printf "%-8s  (no data)\n" "K=$K"
        continue
    fi
    # CSV column indices (0-based):
    #  0=Method 1=Name 2=#Req 3=#Fail 4=Median 5=Avg 6=Min 7=Max
    #  8=AvgSize 9=CurrentRPS 10=CurrentFails/s
    #  11=50% 12=66% 13=75% 14=80% 15=90% 16=95% 17=98% 18=99% ...
    P50=$(echo "$ROW"  | awk -F',' '{print $12}')
    P95=$(echo "$ROW"  | awk -F',' '{print $17}')
    P99=$(echo "$ROW"  | awk -F',' '{print $19}')
    AVG=$(echo "$ROW"  | awk -F',' '{print $6}')
    RPS=$(echo "$ROW"  | awk -F',' '{print $10}')
    FAILS=$(echo "$ROW" | awk -F',' '{print $4}')
    REQS=$(echo "$ROW"  | awk -F',' '{print $3}')
    ERR_RATE=$(awk "BEGIN { if ($REQS>0) printf \"%.1f%%\", $FAILS/$REQS*100; else print \"N/A\" }")
    printf "%-8s %8s %8s %8s %8s %10s %8s\n" \
        "K=$K" "$P50" "$P95" "$P99" "$AVG" "$RPS" "$ERR_RATE"
done

echo "════════════════════════════════════════════════════════════════════════"
echo ""
echo "Full CSV results: $RESULTS_DIR/"
echo "Done."
