#!/opt/icinga-venv/bin/python3
"""Nagios-compatible Nova, Cinder and Neutron control-plane health check."""

import argparse
import sys

import yaml


OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3
DEFAULT_CONFIG = "/data/etc/icinga2/secrets/clouds.yaml"
SERVICE_ALIASES = {
    "nova": "compute",
    "cinder": "volume",
    "neutron": "network",
    "compute": "compute",
    "volume": "volume",
    "network": "network",
}


def finish(code, message):
    labels = {OK: "OK", WARNING: "WARNING", CRITICAL: "CRITICAL", UNKNOWN: "UNKNOWN"}
    print(f"{labels[code]} - {message}")
    raise SystemExit(code)


def load_auth(config_file, cloud_name):
    try:
        with open(config_file, encoding="utf-8") as stream:
            document = yaml.safe_load(stream) or {}
    except (OSError, yaml.YAMLError) as exc:
        finish(UNKNOWN, f"cannot read clouds file: {exc}")

    cloud = (document.get("clouds") or {}).get(cloud_name)
    if not isinstance(cloud, dict):
        finish(UNKNOWN, f"cloud profile '{cloud_name}' not found")

    auth = dict(cloud.get("auth") or {})
    required = ("auth_url", "username", "password")
    missing = [key for key in required if not auth.get(key)]
    if missing:
        finish(UNKNOWN, f"cloud profile '{cloud_name}' is missing {','.join(missing)}")

    auth["region_name"] = cloud.get("region_name", auth.get("region_name", "RegionOne"))
    auth["verify"] = cloud.get("verify", True)
    if cloud.get("cacert"):
        auth["verify"] = cloud["cacert"]
    return auth


def connect(auth):
    try:
        import openstack

        return openstack.connection.Connection(
            auth_url=auth["auth_url"],
            project_name=auth.get("project_name"),
            project_id=auth.get("project_id"),
            system_scope=auth.get("system_scope"),
            username=auth["username"],
            password=auth["password"],
            user_domain_name=auth.get("user_domain_name", "Default"),
            user_domain_id=auth.get("user_domain_id"),
            project_domain_name=auth.get("project_domain_name", "Default"),
            project_domain_id=auth.get("project_domain_id"),
            region_name=auth.get("region_name", "RegionOne"),
            identity_api_version="3",
            verify=auth.get("verify", True),
        )
    except Exception as exc:  # SDK/auth failures must become a monitoring result.
        finish(UNKNOWN, f"cannot connect to OpenStack: {exc}")


def report(label, problems, total):
    if problems:
        finish(CRITICAL, f"{len(problems)}/{total} {label} unhealthy: " + "; ".join(problems))
    if total == 0:
        finish(WARNING, f"no {label} found")
    finish(OK, f"{total}/{total} {label} healthy")


def check_compute(connection):
    try:
        services = list(connection.compute.services())
    except Exception as exc:
        finish(UNKNOWN, f"cannot list Nova services: {exc}")
    problems = [
        f"{service.binary}@{service.host}(status={service.status},state={service.state})"
        for service in services
        if service.status != "enabled" or service.state != "up"
    ]
    report("Nova services", problems, len(services))


def check_volume(connection):
    try:
        services = list(connection.block_storage.services())
    except Exception as exc:
        finish(UNKNOWN, f"cannot list Cinder services: {exc}")
    problems = [
        f"{service.binary}@{service.host}(status={service.status},state={service.state})"
        for service in services
        if service.status != "enabled" or service.state != "up"
    ]
    report("Cinder services", problems, len(services))


def check_network(connection):
    try:
        agents = list(connection.network.agents())
    except Exception as exc:
        finish(UNKNOWN, f"cannot list Neutron agents: {exc}")
    problems = [
        f"{agent.binary}@{agent.host}(alive={agent.is_alive},admin={agent.is_admin_state_up})"
        for agent in agents
        if not agent.is_alive or not agent.is_admin_state_up
    ]
    report("Neutron agents", problems, len(agents))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--cloud", required=True)
    parser.add_argument("-s", "--service", required=True, choices=sorted(SERVICE_ALIASES))
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args()

    connection = connect(load_auth(args.config, args.cloud))
    service = SERVICE_ALIASES[args.service]
    if service == "compute":
        check_compute(connection)
    elif service == "volume":
        check_volume(connection)
    else:
        check_network(connection)


if __name__ == "__main__":
    main()
