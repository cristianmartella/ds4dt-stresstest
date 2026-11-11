#!/bin/bash

# get_username() {
#   case "$1" in
#     user-credential)       echo "user" ;;
#     operator-credential)       echo "operator" ;;
#     spvsmanager-credential)       echo "spvs-user" ;;
#     *) echo "Error: credential_configuration_id '$1' not found." >&2 ; exit 1 ;;
#   esac
# }

KEYCLOAK_URL="$1"
CREDENTIAL_ID="$2"
USERNAME="spvs-user"
# USERNAME=$(get_username "$2")


access_token=$(curl -s -X POST "$KEYCLOAK_URL/realms/test-realm/protocol/openid-connect/token" \
  --header 'Accept: */*' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data grant_type=password \
  --data client_id=admin-cli \
  --data username=$USERNAME \
  --data password=test | jq '.access_token' -r)

offer_uri=$(curl -s -X GET "$KEYCLOAK_URL/realms/test-realm/protocol/oid4vc/credential-offer-uri?credential_configuration_id=$CREDENTIAL_ID" \
  --header "Authorization: Bearer ${access_token}" | jq '"\(.issuer)\(.nonce)"' -r)

pre_authorized_code=$(curl -s -X GET ${offer_uri} \
  --header "Authorization: Bearer ${access_token}" | jq '.grants."urn:ietf:params:oauth:grant-type:pre-authorized_code"."pre-authorized_code"' -r)

credential_access_token=$(curl -s -X POST "$KEYCLOAK_URL/realms/test-realm/protocol/openid-connect/token" \
  --header 'Accept: */*' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data grant_type=urn:ietf:params:oauth:grant-type:pre-authorized_code \
  --data pre-authorized_code=${pre_authorized_code} | jq '.access_token' -r)

curl -s -X POST "$KEYCLOAK_URL/realms/test-realm/protocol/oid4vc/credential" \
  --header 'Accept: */*' \
  --header 'Content-Type: application/json' \
  --header "Authorization: Bearer ${credential_access_token}" \
  --data "{\"credential_identifier\":\"$CREDENTIAL_ID\", \"format\":\"jwt_vc\"}" | jq '.credential' -r
