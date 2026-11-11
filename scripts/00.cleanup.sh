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

echo "*** Cleanup script ***"

if [ -f .participants.tmp ]; then
    for participant in $(cat .participants.tmp); do
        echo "Uninstalling $participant..."
        helm uninstall $participant-dsc -n $participant 2>/dev/null
        
        kubectl delete namespace $participant
    done

    echo "Removing .participants.tmp file..."
    rm .participants.tmp
fi


while getopts ':f:p:t:' opt; do
    case $opt in
        f)
            volumes=$(docker ps -a --format '{{ .ID }}' | xargs -I {} docker inspect -f '{{ .Name }}{{ range .Mounts }}{{ printf "\n " }}{{ .Type }} {{ if eq .Type "bind" }}{{ .Source }}{{ end }}{{ .Name }} => {{ .Destination }}{{ end }}' {} | sed 's/ => \/.*//g' | tr -d '\n' | sed -E 's/\/k3s-maven-plugin(.*)(\/.+ ).*/\1/gm' | sed -E 's/( volume )/\n/g' | tail -n +2)
            
            echo "Terminating k3s-maven-plugin container..."
            docker stop k3s-maven-plugin 2>/dev/null
            echo "k3s-maven-plugin container terminated."
            
            echo "Removing k3s-maven-plugin container..."
            docker rm k3s-maven-plugin 2>/dev/null
            echo "k3s-maven-plugin container removed."
            
            echo "Removing k3s-maven-plugin volumes..."
            echo $volumes | xargs -n 1 docker volume rm 2>/dev/null
            echo "k3s-maven-plugin volumes removed."
            ;;
        p)
            echo "Removing persistent volumes..."
            
            kubectl delete pvc data-data-service-postgis-0 -n spvs-dsc-provider 2>/dev/null
            kubectl delete pvc data-postgresql-0 -n consumer 2>/dev/null
            kubectl delete pvc data-trust-anchor-mysql-0 -n trust-anchor 2>/dev/null
            ;;
        t)
            echo "Uninstalling signoz k8s-infra Helm release..."
            helm uninstall k8s-infra-tel -n telemetry 2>/dev/null
            echo "k8s-infra-tel release uninstalled."
            echo "Uninstalling signoz..."
            helm uninstall signoz -n telemetry 2>/dev/null
            echo "signoz release uninstalled."
            echo "Force removing signoz-clickouse resources..."
            kubectl delete statefulset signoz-clickhouse -n telemetry --force --grace-period=0 2>/dev/null
            kubectl delete pvc data-signoz-clickhouse-0 -n telemetry --force --grace-period=0 2>/dev/null
            echo "signoz-clickhouse resources removed."
            echo "Removing telemetry namespace..."
            kubectl delete namespace telemetry 2>/dev/null
            echo "telemetry namespace removed."
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            ;;
    esac
done
echo -e "\n*** Cleanup completed! ***"

# if a default KUBECONFIG exists, check if the script is sourced and export default KUBECONFIG in case
if [ -f $HOME/.kube/config ]; then
    if $(return 0 2>/dev/null); then
            echo "Restoring default KUBECONFIG..."
            export KUBECONFIG=$HOME/.kube/config
            echo "KUBECONFIG exported -> $KUBECONFIG"
    else
        echo -e "Please run\n\nexport KUBECONFIG=$HOME/.kube/config\n\nto make kubectl environment available."
    fi
fi
