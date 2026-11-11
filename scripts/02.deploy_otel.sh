# Copyright 2025 Cristian Martella
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#!/bin/sh

echo "*** Signoz deployment ***"

depl_namespace="telemetry"
signoz_chart_path="$(builtin cd $(pwd)/..; pwd)/charts/signoz"

echo "Adding Signoz Helm repository..."
helm repo add signoz https://signoz.github.io/helm-charts
helm repo update
echo "Signoz Helm repository added."


echo "Deploying Signoz..."
helm install signoz signoz/signoz --namespace telemetry --create-namespace --wait --timeout 1h -f $signoz_chart_path/values.yaml
echo "Waiting for Signoz pods to be ready..."
kubectl wait pod --all --for=condition=Ready -n $depl_namespace --timeout=180s &>/dev/null && kill -INT $(pidof watch) 2>/dev/null &
watch kubectl get pods -n $depl_namespace
echo "Signoz deployed."

echo "Deploying k8s infrastructure components for Signoz..."
helm install k8s-infra-tel signoz/k8s-infra -n $depl_namespace -f $signoz_chart_path/k8s-metrics/values.yaml
echo "Waiting for k8s-infra-tel pods to be ready..."
kubectl wait pod --all --for=condition=Ready -n $depl_namespace --timeout=180s &>/dev/null && kill -INT $(pidof watch) 2>/dev/null &
watch kubectl get pods -n $depl_namespace
echo "k8s-infra-tel deployed."

echo "Forwarding Signoz UI port to localhost:8444..."
nohup kubectl port-forward -n $depl_namespace svc/signoz 8444:8080 &>/dev/null &
echo "Signoz UI is available at http://localhost:8444"
