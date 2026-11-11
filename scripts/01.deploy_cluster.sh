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

echo "*** k3s cluster deployment ***"

echo "Stopping k3s.service..."
sudo systemctl stop k3s.service
echo "k3s.service stopped."

echo "Deploying cluster..."
mvn clean deploy -f ../base-cluster/pom.xml
echo "Cluster deployed."


# check if the script is sourced and export KUBECONFIG in case
if $(return 0 2>/dev/null); then
    echo "Exporting KUBECONFIG..."
    export KUBECONFIG=$(builtin cd $(pwd)/..; pwd)/base-cluster/target/k3s.yaml
    echo "KUBECONFIG exported -> $KUBECONFIG"

    echo "Enabling local path storage..."
    kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml
    kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
    echo "Local path storage enabled."
else
    echo -e "Please run\n\nexport KUBECONFIG=$(builtin cd $(pwd)/..; pwd)/base-cluster/target/k3s.yaml\n\nto make kubectl environment available."
    echo -e "Once the KUBECONFIG is exported, run\n\nkubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml\n\nto enable local path storage."
fi

echo -e "\n*** k3s cluster is ready! ***"