#!/usr/bin/env bash
# Run Locust load test at K=1, 5, 10, 20 and save results.
#
# Usage:
#   export ALB_URL=http://<your-alb-dns-name>
#   bash tests/load/run_all_k.sh

set -euo pipefail

if [ -z "${ALB_URL:-}" ]; then
    echo "ERROR: Set ALB_URL first:"
    echo "  export ALB_URL=http://\$(aws elbv2 describe-load-balancers --region us-west-2 --query 'LoadBalancers[?LoadBalancerName==\`flair2-dev-alb\`].DNSName' --output text)"
    exit 1
fi

RESULTS_DIR="$(cd "$(dirname "$0")/../../docs/load-test-results" && pwd)"
mkdir -p "$RESULTS_DIR"

echo "=== Locust Load Test ==="
echo "Target: $ALB_URL"
echo "Results: $RESULTS_DIR"
echo ""

for K in 1 5 10 20; do
    echo "--- K=$K users, 60s run ---"
    locust -f "$(dirname "$0")/locustfile.py" \
        --host "$ALB_URL" \
        --users "$K" \
        --spawn-rate "$K" \
        --run-time 60s \
        --headless \
        --csv="$RESULTS_DIR/k${K}" \
        2>&1 | tail -5
    echo ""
done

echo "=== Done. Results in $RESULTS_DIR ==="
ls -la "$RESULTS_DIR"
