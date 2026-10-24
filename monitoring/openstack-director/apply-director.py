#!/usr/bin/env python3
"""Idempotently apply file-backed objects through the Director REST API."""

import base64
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = os.environ.get("ICINGA_DIRECTOR_URL", "http://127.0.0.1:8080/director")
MASTER = os.environ.get("ICINGA_DIRECTOR_MASTER", "127.0.0.1")
MASTER_KEY = os.environ.get("ICINGA_DIRECTOR_SSH_KEY", os.path.expanduser("~/.ssh/id_ed25519"))


def admin_password(path="/etc/icinga-ansible/passwords.yml"):
    with open(path, encoding="utf-8") as source:
        for line in source:
            match = re.match(r"^icingaweb2_admin_password:\s*(.*?)\s*$", line)
            if match:
                return match.group(1).strip("'\"")
    raise RuntimeError("icingaweb2_admin_password was not found")


AUTH = base64.b64encode(("admin:" + admin_password()).encode()).decode()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(kind, name, method, document=None):
    # Icinga Web treats '+' literally in this route, so spaces must be %20.
    query = urllib.parse.urlencode({"name": name}, quote_via=urllib.parse.quote)
    url = f"{BASE_URL}/{kind}?" + query
    data = json.dumps(document).encode() if document is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": "Basic " + AUTH, "Accept": "application/json",
                 "Content-Type": "application/json"},
    )
    try:
        with OPENER.open(req, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        if exc.code == 404 and method == "GET":
            return 404, None
        raise RuntimeError(f"{method} {kind} {name} returned HTTP {exc.code}: {body[:500]}")


def normalize(document):
    cleaned = dict(document)
    cleaned.pop("uuid", None)
    cleaned.pop("customVariables", None)
    cleaned.pop("fields", None)
    for key in ("max_check_attempts", "check_interval", "retry_interval", "timeout"):
        value = cleaned.get(key)
        if isinstance(value, str) and value.isdigit():
            cleaned[key] = int(value)
    return cleaned


def upsert(kind, name, properties):
    payload = dict(properties)
    payload["object_name"] = name
    status, current = request(kind, name, "GET")
    if status == 200 and normalize(current) == normalize(payload):
        print(f"{kind} {name}: unchanged")
        return
    if status == 404:
        remote_command = " ".join([
            "sudo", "docker", "exec", "-i", "icingaweb2", "icingacli",
            "director", shlex.quote(kind), "create", shlex.quote(name), "--json",
        ])
        command = [
            "ssh", "-i", MASTER_KEY, "-o", "BatchMode=yes", MASTER,
            remote_command,
        ]
        result = subprocess.run(
            command, input=json.dumps(properties), text=True,
            capture_output=True, check=False,
        )
        if result.returncode:
            raise RuntimeError(
                f"could not create {kind} {name}: {(result.stderr or result.stdout).strip()}"
            )
        print(f"{kind} {name}: created")
        return
    status, result = request(kind, name, "PUT", payload)
    if status not in {200, 201} or result.get("object_name") != name:
        raise RuntimeError(
            f"Director did not persist {kind} {name}: HTTP {status}, response={result!r}"
        )
    print(f"{kind} {name}: {'updated' if current else 'created'}")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} director-objects.json")
    with open(sys.argv[1], encoding="utf-8") as source:
        config = json.load(source)
    if set(config) != {"hosts", "services"}:
        raise RuntimeError("configuration must contain exactly hosts and services")
    for name, properties in config["hosts"].items():
        upsert("host", name, properties)
    for name, properties in config["services"].items():
        upsert("service", name, properties)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
