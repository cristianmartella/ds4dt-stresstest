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

echo "*** Consumer deployment ***"

consumer_root="$(builtin cd $(pwd)/..; pwd)/charts/spvs-dsc-consumer"
consumer_name=$(basename $consumer_root)
consumer_identity_path="$consumer_root/identity"
DID_HELPER="$(pwd)/did-helper"

PRIVATE_KEY="$consumer_identity_path/private-key.pem"
PUBLIC_KEY="$consumer_identity_path/public-key.pem"
CERTIFICATE="$consumer_identity_path/cert.pem"
KEYSTORE="$consumer_identity_path/cert.pfx"
DID_KEY="$consumer_identity_path/did.key"

echo "Creating $consumer_name identity..."

mkdir -p "$consumer_identity_path"
# create a new consumer identity, if not already exists

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

    # certificate defaults
    COUNTRY=""
    STATE=""
    LOCALITY=""
    ORGNAME=""
    ORGUNIT=""
    COMMONNAME=""
    DAYS="365"

    # verify the certificate configuration file, if provided
    while getopts ':c:' opt; do
        echo $opt
        echo $OPTARG
        case $opt in
            c)
                if [ -f "$OPTARG" ]; then
                    source $OPTARG
                    echo "Certificate configuration file $OPTARG loaded."
                else
                    echo "Certificate configuration file $OPTARG not found."
                    break
                fi
                ;;
            \?)
                echo "Invalid option: -$OPTARG" >&2
                ;;
        esac
    done

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

    echo "Consumer identity created."
fi

consumer_did_key=$(cat $DID_KEY)
echo "Consumer DID key: $consumer_did_key"

# apply consumer identity to values.yaml
echo "Applying consumer identity to values.yaml..."
sed -i "s/did:key:.*\"/$consumer_did_key\"/g" $consumer_root/values.yaml


echo "Creating consumer namespace..."
kubectl create namespace $consumer_name 2>/dev/null

echo "Deploying the key into the cluster"
kubectl create secret generic consumer-identity --from-file=$KEYSTORE -n $consumer_name 2>/dev/null

echo "Updating .participants.tmp file..."
echo "$consumer_name" >> .participants.tmp

echo "Deploying $consumer_name..."
helm install consumer-dsc data-space-connector/data-space-connector --version 7.37.4 -f $consumer_root/values.yaml --namespace=$consumer_name

kubectl wait pod --all --for=condition=Ready -n $consumer_name --timeout=300s && kill -INT $(pidof watch) 2>/dev/null &
watch kubectl get pods -n $consumer_name

echo -e "*** Consumer deployed! ***\n"

echo -e "Next steps:\nObtain a valid credential for $consumer_name and export it to USER_CREDENTIAL"

cat <<EOF
Next steps:
1. Register $consumer_name at the Trust Anchor
  - $consumer_name DID key is $consumer_did_key
  - Trusted Issuers List API URL: http://til.127.0.0.1.nip.io:8080/issuer
2. Get user and operator verifiable credentials for $consumer_name
  - export USER_CREDENTIAL=\$(./get_credential_for_consumer.sh http://keycloak-consumer.127.0.0.1.nip.io:8080 user-credential); echo \${USER_CREDENTIAL}
  - export OPERATOR_CREDENTIAL=\$(./get_credential_for_consumer.sh http://keycloak-consumer.127.0.0.1.nip.io:8080 operator-credential); echo \${OPERATOR_CREDENTIAL}
EOF