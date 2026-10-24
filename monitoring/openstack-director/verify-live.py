#!/usr/bin/env python3
"""Reschedule and verify every Director-managed OpenStack check via Icinga API."""

import base64
import json
import re
import ssl
import sys
import time
import urllib.request


HOSTS = sys.argv[1:]
NODE_SERVICES = ["Linux CPU via SSH", "Linux RAM via SSH", "Linux Disk via SSH"]
EXPECTED_SERVICES = {
    *(f"{host}!{service}" for host in HOSTS for service in NODE_SERVICES),
}


def api_password(path="/etc/icinga-ansible/icinga2/conf.d/api-users.conf"):
    with open(path, encoding="utf-8") as source:
        content = source.read()
    block = re.search(r'object ApiUser "icingadb-web"\s*\{(.*?)\}', content, re.S)
    password = re.search(r'password\s*=\s*"([^"]+)"', block.group(1)) if block else None
    if not password:
        raise RuntimeError("icingaweb2 API credential was not found")
    return password.group(1)


AUTH = base64.b64encode(("icingadb-web:" + api_password()).encode()).decode()
TLS = ssl._create_unverified_context()


def request(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        "https://127.0.0.1:5665" + path,
        data=data,
        method="POST" if data is not None else "GET",
        headers={"Authorization": "Basic " + AUTH, "Accept": "application/json",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, context=TLS, timeout=15) as response:
        return json.load(response)


def current_services():
    result = {}
    for item in request("/v1/objects/services").get("results", []):
        if item["name"] in EXPECTED_SERVICES:
            result[item["name"]] = item["attrs"]
    return result


def current_hosts():
    result = {}
    for item in request("/v1/objects/hosts").get("results", []):
        if item["name"] in HOSTS:
            result[item["name"]] = item["attrs"]
    return result


def main():
    if not HOSTS:
        raise RuntimeError("pass at least one Director-managed host name")
    initial = current_services()
    missing = EXPECTED_SERVICES - set(initial)
    if missing:
        raise RuntimeError("missing Service objects: " + ", ".join(sorted(missing)))
    initial_hosts = current_hosts()
    missing_hosts = set(HOSTS) - set(initial_hosts)
    if missing_hosts:
        raise RuntimeError("missing Host objects: " + ", ".join(sorted(missing_hosts)))

    for host in HOSTS:
        response = request("/v1/actions/reschedule-check", {
            "type": "Host",
            "filter": f'host.name=={json.dumps(host)}',
            "force": True,
        })
        results = response.get("results", [])
        if len(results) != 1 or results[0].get("code") != 200:
            raise RuntimeError(f"could not reschedule Host {host}")

    for full_name in sorted(EXPECTED_SERVICES):
        host, service = full_name.split("!", 1)
        response = request("/v1/actions/reschedule-check", {
            "type": "Service",
            "filter": f'host.name=={json.dumps(host)} && service.name=={json.dumps(service)}',
            "force": True,
        })
        results = response.get("results", [])
        if len(results) != 1 or results[0].get("code") != 200:
            raise RuntimeError(f"could not reschedule {full_name}")

    deadline = time.time() + 90
    service_states = {}
    host_states = {}
    while time.time() < deadline:
        service_states = current_services()
        host_states = current_hosts()
        if len(service_states) == len(EXPECTED_SERVICES) and all(
            (attrs.get("last_check_result") or {}).get("execution_end", 0)
            > ((initial.get(name, {}).get("last_check_result") or {}).get("execution_end", 0))
            for name, attrs in service_states.items()
        ) and len(host_states) == len(HOSTS) and all(
            (attrs.get("last_check_result") or {}).get("execution_end", 0)
            > ((initial_hosts.get(name, {}).get("last_check_result") or {}).get("execution_end", 0))
            for name, attrs in host_states.items()
        ):
            break
        time.sleep(3)

    failed = False
    for name in sorted(HOSTS):
        attrs = host_states.get(name, {})
        result = attrs.get("last_check_result") or {}
        output = (result.get("output") or "not checked").splitlines()[0]
        state = attrs.get("state")
        exit_status = result.get("exit_status")
        check_command = attrs.get("check_command")
        check_source = result.get("check_source")
        print(
            f"Host {name}: command={check_command} source={check_source} "
            f"state={state} exit={exit_status} {output}"
        )
        fresh = result.get("execution_end", 0) > (
            (initial_hosts.get(name, {}).get("last_check_result") or {}).get("execution_end", 0)
        )
        if exit_status is None or state != 0 or check_command != "icmp" or not fresh:
            failed = True
    print(f"hosts_verified={len(host_states)}/{len(HOSTS)}")

    for name in sorted(EXPECTED_SERVICES):
        attrs = service_states.get(name, {})
        result = attrs.get("last_check_result") or {}
        output = (result.get("output") or "not checked").splitlines()[0]
        state = attrs.get("state")
        exit_status = result.get("exit_status")
        print(f"{name}: state={state} exit={exit_status} {output}")
        fresh = result.get("execution_end", 0) > (
            (initial.get(name, {}).get("last_check_result") or {}).get("execution_end", 0)
        )
        if exit_status is None or state != 0 or not fresh:
            failed = True
    print(f"services_verified={len(service_states)}/{len(EXPECTED_SERVICES)}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
