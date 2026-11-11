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

echo "*** Wallet identity creation ***"

wallet_path=$(builtin cd $(pwd)/..; pwd)/wallet-identity
vc_issuer="consumer"

while getopts 'p:n:' opt; do
    echo "Option: $opt"
    echo "OPTARG: $OPTARG"
    case $opt in
        p)
            if [ ! -z $OPTARG ] && [ -d $OPTARG ]; then
                wallet_path=$(cd $OPTARG; pwd)
            else
                echo "No wallet path provided."
                return 1
            fi
            ;;
        n)
            if [ ! -z $OPTARG ]; then
                vc_issuer=$OPTARG
            else
                echo "No participant name provided. Defaulting to '$vc_issuer'."
            fi
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            return 1
            ;;
    esac
done

echo "Preparing wallet identity (identity of the user that acts on behalf of $vc_issuer)..."
mkdir -p "$wallet_path"
chmod o+rw "$wallet_path"

docker run -v $wallet_path:/cert quay.io/wi_stefan/did-helper:0.1.1

KEYCLOAK_URL="http://keycloak-$vc_issuer.127.0.0.1.nip.io:80"


echo -e "\nIssuing verifiable credential for: SPVS Manager"
spvs_manager=$(./get_credential_for_consumer.sh "$KEYCLOAK_URL" spvsmanager-credential)
if $(return 0 2>/dev/null); then
    echo "Exporting SPVS_MANAGER..."
    export SPVS_MANAGER=$spvs_manager
    echo -e "SPVS Manager Credential:\n$SPVS_MANAGER\n"
else
    echo -e "SPVS Manager Credential issued. You can export it by running\n\nexport SPVS_MANAGER=$spvs_manager\n"
fi



echo -e "\n*** Wallet identity created! ***"

cat <<EOF
Now it is possible to create and embed access token as bearer token in the Authorization header of the HTTP requests to the Data Provider.
Next steps:

  export SPVS Manager VC:
    ./get_access_token_oid4vp.sh http://scorpio.127.0.0.1.nip.io:80 \$SPVS_MANAGER spvs-manager $wallet_path
EOF
