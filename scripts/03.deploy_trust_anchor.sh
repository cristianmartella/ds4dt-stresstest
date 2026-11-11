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

#!/bin/bash

trust_anchor_root=$(builtin cd $(pwd)/..; pwd)/charts/trust-anchor
trust_anchor_name=$(basename $trust_anchor_root)

echo "Updating .participants.tmp file..."
echo "$trust_anchor_name" >> .participants.tmp

echo "*** Trust anchor deployment ***"

echo "Creating trust-anchor namespace..."
kubectl create namespace trust-anchor

echo "Deploying trust-anchor..."
helm repo add data-space-connector https://fiware.github.io/data-space-connector/
helm install trust-anchor-dsc data-space-connector/trust-anchor --version 0.3.0 -f $trust_anchor_root/values.yaml --namespace=trust-anchor

kubectl wait pod --all --for=condition=Ready -n trust-anchor --timeout=300s && kill -INT $(pidof watch) 2>/dev/null &
watch kubectl get pods -n trust-anchor

echo "*** Trust anchor deployed ***"