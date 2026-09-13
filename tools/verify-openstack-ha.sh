#!/usr/bin/env bash
set -euo pipefail

passwords_file="${CONFIG_DIR:-/etc/icinga-ansible}/passwords.yml"
api_password="$(sudo python3 -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["icinga2_api_user_password"])' "$passwords_file")"
api_url="${API_URL:-https://127.0.0.1:5665}"
host_name="${1:-openstack-devstack}"

curl --noproxy '*' --silent --show-error --insecure \
  --user "icingaweb2:${api_password}" \
  --header 'Accept: application/json' \
  --request POST "${api_url}/v1/actions/reschedule-check" \
  --data "{\"type\":\"Service\",\"filter\":\"host.name==\\\"${host_name}\\\"\",\"force\":true}" \
  >/dev/null

sleep 10

curl --noproxy '*' --silent --show-error --insecure \
  --user "icingaweb2:${api_password}" \
  --header 'Accept: application/json' \
  --header 'X-HTTP-Method-Override: GET' \
  --request POST "${api_url}/v1/objects/services" \
  --data "{\"filter\":\"host.name==\\\"${host_name}\\\"\",\"attrs\":[\"name\",\"state\",\"last_check_result\"]}" \
  | python3 -c '
import json
import os
import sys

payload = json.load(sys.stdin)
if os.environ.get("DEBUG"):
    print(json.dumps(payload, sort_keys=True))
results = payload.get("results", [])
if not results:
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit("No matching OpenStack services returned by the Icinga API")
errors = [item for item in results if item.get("code", 200) != 200]
if errors:
    print(json.dumps(errors, sort_keys=True))
    raise SystemExit("Icinga API returned an error for one or more services")
for item in sorted(results, key=lambda value: value.get("name", "")):
    attrs = item.get("attrs", {})
    check = attrs.get("last_check_result") or {}
    output = str(check.get("output", "no result")).splitlines()[0]
    name = item.get("name", attrs.get("name"))
    state = attrs.get("state")
    source = check.get("check_source")
    print(f"{name} | state={state} | source={source} | {output}")
'
