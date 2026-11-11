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

echo "*** Provider deployment ***"

# certificate defaults
COUNTRY=""
STATE=""
LOCALITY=""
ORGNAME=""
ORGUNIT=""
COMMONNAME=""
DAYS="365"

# default provider root folder
provider_root="$(builtin cd $(pwd)/..; pwd)/charts/spvs-dsc-provider"

# til host
TIL_HOST="til.127.0.0.1.nip.io:80"

# parse command line arguments
# -p - provider chart folder (default: ../provider)
# -c - certificate configuration file (optional)
while getopts ':c:p:' opt; do
    case $opt in
        p)
            if [ -d "$OPTARG" ]; then
                provider_root=$OPTARG
            else
                break
            fi
            ;;
        c)
            if [ -f "$OPTARG" ]; then
                source $OPTARG
                echo "Certificate configuration file $OPTARG loaded."
            else
                echo "Certificate configuration file not found."
                exit 1
            fi
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            exit 1
            ;;
    esac
done
echo "Provider root folder set: $provider_root"

provider_name=$(basename $provider_root)
provider_identity_path="$provider_root/identity"
DID_HELPER="$(pwd)/did-helper"

PRIVATE_KEY="$provider_identity_path/private-key.pem"
PUBLIC_KEY="$provider_identity_path/public-key.pem"
CERTIFICATE="$provider_identity_path/cert.pem"
KEYSTORE="$provider_identity_path/cert.pfx"
DID_KEY="$provider_identity_path/did.key"

echo "Updating .participants.tmp file..."
echo "$provider_name" >> .participants.tmp

echo "Creating provider identity..."

mkdir -p "$provider_identity_path"

# create a new provider identity, if not already exists

# private key
if [ -f $PRIVATE_KEY ]; then
    echo "Private key already exists"
else
    echo "Generating private key..."
    openssl ecparam -name prime256v1 -genkey -noout -out $PRIVATE_KEY
fi

# public key
if [ -f $PUBLIC_KEY ]; then
    echo "Public key already exists"
else
    echo "Generating public key for the private key..."
    openssl ec -in $PRIVATE_KEY -pubout -out $PUBLIC_KEY
fi

# certificate
if [ -f $CERTIFICATE ]; then
    echo "Certificate already exists"
else
    echo "Creating a (self-signed) certificate..."

    subject="/C=$COUNTRY/ST=$STATE/L=$LOCALITY/O=$ORGNAME/OU=$ORGUNIT/CN=$COMMONNAME"
    openssl req -new -x509 -key $PRIVATE_KEY -out $CERTIFICATE -days $DAYS --subj "$subject"
fi

# keystore
if [ -f $KEYSTORE ]; then
    echo "Keystore already exported."
else
    echo "Exporting keystore..."
    openssl pkcs12 -export -inkey $PRIVATE_KEY -in $CERTIFICATE -out $KEYSTORE -name didPrivateKey -passout pass:test
fi

echo "Verifying keystore content..."
keytool -v -keystore $KEYSTORE -list -alias didPrivateKey -storepass test

# did key
if [ -f $DID_KEY ]; then
    echo "Did key already generated"
else
    if [ ! -f $DID_HELPER ]; then
        echo "Did helper not found. Downloading did-helper..."
        wget https://github.com/wistefan/did-helper/releases/download/0.1.1/did-helper
        chmod +x did-helper
    fi

    echo "Generating did key..."
    ./did-helper -keystorePath $KEYSTORE -keystorePassword=test | grep -o 'did:key:.*' > $DID_KEY

    echo "Provider identity created."
fi

provider_did_key=$(cat $DID_KEY)
echo "Provider DID key: $provider_did_key"

# apply provider identity to values.yaml
echo "Applying provider identity to values.yaml..."
sed -i "s/did:key:.*\"/$provider_did_key\"/g" $provider_root/values.yaml


echo "Creating $provider_name namespace..."
kubectl create namespace $provider_name 2>/dev/null

echo "Deploying the key into the cluster"
kubectl create secret generic $provider_name-identity --from-file=$KEYSTORE -n $provider_name 2>/dev/null

echo "Deploying $provider_name..."
helm install $provider_name-dsc data-space-connector/data-space-connector --version 7.37.4 -f $provider_root/values.yaml --namespace=$provider_name

echo -e "Deploying rainbow for the provider..."
helm install rainbow -f $provider_root/values.rainbow.yaml $provider_root/templates/rainbow/ -n $provider_name

kubectl wait pod --selector=job-name!='tmf-api-registration' --all --for=condition=Ready -n $provider_name --timeout=300s &>/dev/null && kill -INT $(pidof watch) 2>/dev/null &
watch kubectl get pods -n $provider_name

echo -e "*** $provider_name deployed! ***\n"


echo "Registering $provider_name at the Trust Anchor..."

curl -X POST http://$TIL_HOST/issuer \
-H "Content-Type: application/json" \
-d '{
    "did": "'"$provider_did_key"'",
    "credentials": []
}' 2> /dev/null

echo "Provider $provider_name registered at the Trust Anchor."

echo -e "Patching IoTAgent to enable LD support..."
kubectl patch deployment data-service-iota -n $depl_namespace --patch-file $depl_root/templates/iota-ingress/iota-deployment-patch.yaml



cat <<EOF
Next steps:
1. Configure and register policies to access data services
  - Policy Manager API URL: http://pap-provider.127.0.0.1.nip.io:8080/policy
  - Provide the policy details in the request body
EOF