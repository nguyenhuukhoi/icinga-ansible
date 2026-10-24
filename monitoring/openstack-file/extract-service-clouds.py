#!/usr/bin/env python3
"""Build clouds.yaml-compatible JSON from active Kolla service configs."""

import configparser
import json
import os
from pathlib import Path


SERVICES = {
    "monitoring-nova": Path("/etc/kolla/nova-api/nova.conf"),
    "monitoring-cinder": Path("/etc/kolla/cinder-api/cinder.conf"),
    "monitoring-neutron": Path("/etc/kolla/neutron-server/neutron.conf"),
}
OUTPUT = Path("/tmp/icinga-openstack-clouds.json")


def read_cloud(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    if not parser.read(path):
        raise RuntimeError(f"cannot read {path}")
    section = parser["keystone_authtoken"]
    required = ("auth_url", "username", "password", "project_name")
    missing = [key for key in required if not section.get(key)]
    if missing:
        raise RuntimeError(f"{path} is missing {','.join(missing)}")
    return {
        "auth": {
            **{key: section[key] for key in required},
            "user_domain_name": section.get("user_domain_name", "Default"),
            "project_domain_name": section.get("project_domain_name", "Default"),
        },
        "region_name": "RegionOne",
        "interface": "internal",
        "identity_api_version": 3,
    }


def main():
    document = {"clouds": {name: read_cloud(path) for name, path in SERVICES.items()}}
    old_umask = os.umask(0o077)
    try:
        with OUTPUT.open("w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
    finally:
        os.umask(old_umask)
    OUTPUT.chmod(0o600)


if __name__ == "__main__":
    main()
