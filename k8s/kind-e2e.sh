#!/usr/bin/env bash
# Build the image, run it on a local kind cluster, and run the SDK smoke test through the Service.
# Note: replicas=2 keep separate in-memory state, so the smoke test uses one replica (see docs).
set -euo pipefail
CLUSTER=${CLUSTER:-integration-kit}
kind get clusters | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER" --wait 90s
docker build -t integration-kit:local .
kind load docker-image integration-kit:local --name "$CLUSTER"
kubectl --context "kind-$CLUSTER" apply -f k8s/deployment.yaml
kubectl --context "kind-$CLUSTER" -n integration-kit scale deploy/integration-kit --replicas=1
kubectl --context "kind-$CLUSTER" -n integration-kit rollout status deploy/integration-kit --timeout=120s
kubectl --context "kind-$CLUSTER" -n integration-kit port-forward svc/integration-kit 18080:80 >/dev/null 2>&1 &
PF=$!; trap 'kill $PF' EXIT; sleep 3
IK_BASE_URL=http://127.0.0.1:18080 python3 examples/quickstart.py
