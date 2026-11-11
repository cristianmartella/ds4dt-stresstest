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

depl_name="spvs-core"
depl_namespace="spvs-dsc-provider"
depl_root=$(builtin cd $(pwd)/..; pwd)/charts/spvs-core

echo "*** Deployment of spvs-core services ***"

echo "Creating $depl_namespace namespace..."
kubectl create namespace $depl_namespace 2>/dev/null || echo "Namespace $depl_namespace already exists, skipping creation."

echo "Deploying $depl_name..."
helm install $depl_name $depl_root -n $depl_namespace

kubectl wait pod --all --for=condition=Ready -n $depl_namespace --timeout=300s && kill -INT $(pidof watch) 2>/dev/null &
watch kubectl get pods -n $depl_namespace

echo -e "Patching IoTAgent to enable LD support..."
kubectl patch deployment data-service-iota -n $depl_namespace --patch-file $depl_root/templates/iota-ingress/iota-deployment-patch.yaml

echo "*** spvs-core services deployed ***"