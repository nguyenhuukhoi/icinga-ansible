#!/opt/icinga-venv/bin/python3
# Check OpenStack service health (compute/volume/network/masakari) via openstacksdk, multi-cloud.
# Credentials come from a clouds.yaml-style file (NOT env vars) so 1 script instance can monitor
# ANY number of clouds -- CheckCommand passes "-c <cloud_name> -s <service_type>", the script looks
# up the matching entry under "clouds:" in CONFIG_FILE. See design.md section 9.7.
import argparse
import sys

import yaml

OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

# Mounted through the master-only layered secret directory. This is standard clouds.yaml format,
# the same format understood by python-openstackclient.
CONFIG_FILE = "/etc/icinga-ansible/icinga2/clouds.yaml"


def load_auth(cloud_name):
    try:
        with open(CONFIG_FILE, "r") as f:
            data = yaml.safe_load(f) or {}
    except OSError as exc:
        print(f"UNKNOWN - could not read {CONFIG_FILE}: {exc}")
        sys.exit(UNKNOWN)
    except yaml.YAMLError as exc:
        print(f"UNKNOWN - could not parse {CONFIG_FILE}: {exc}")
        sys.exit(UNKNOWN)

    cloud = (data.get("clouds") or {}).get(cloud_name)
    if cloud is None:
        print(f"UNKNOWN - cloud '{cloud_name}' not found in {CONFIG_FILE}")
        sys.exit(UNKNOWN)

    auth = dict(cloud.get("auth") or {})
    if "auth_url" not in auth or "username" not in auth or "password" not in auth:
        print(f"UNKNOWN - cloud '{cloud_name}' in {CONFIG_FILE} is missing auth_url/username/password")
        sys.exit(UNKNOWN)
    auth.setdefault("region_name", cloud.get("region_name", "RegionOne"))
    return auth


def connect(auth):
    import openstack

    try:
        return openstack.connection.Connection(
            auth_url=auth["auth_url"],
            project_name=auth.get("project_name"),
            system_scope=auth.get("system_scope"),
            username=auth["username"],
            password=auth["password"],
            user_domain_name=auth.get("user_domain_name", "Default"),
            project_domain_name=auth.get("project_domain_name", "Default"),
            region_name=auth.get("region_name", "RegionOne"),
            identity_api_version="3",
        )
    except Exception as exc:
        print(f"UNKNOWN - could not connect to OpenStack: {exc}")
        sys.exit(UNKNOWN)


def report(label, problems, total):
    if problems:
        print(f"CRITICAL - {len(problems)}/{total} {label} down: " + "; ".join(problems))
        sys.exit(CRITICAL)
    if total == 0:
        print(f"WARNING - no {label} found")
        sys.exit(WARNING)
    print(f"OK - {total}/{total} {label} up")
    sys.exit(OK)


def check_compute(conn):
    try:
        services = list(conn.compute.services())
    except Exception as exc:
        print(f"UNKNOWN - error listing compute services: {exc}")
        sys.exit(UNKNOWN)

    problems = [
        f"{svc.binary} on {svc.host} (status={svc.status}, state={svc.state})"
        for svc in services
        if svc.status != "enabled" or svc.state != "up"
    ]
    report("nova compute service", problems, len(services))


def check_volume(conn):
    try:
        services = list(conn.block_storage.services())
    except Exception as exc:
        print(f"UNKNOWN - error listing volume services: {exc}")
        sys.exit(UNKNOWN)

    problems = [
        f"{svc.binary} on {svc.host} (status={svc.status}, state={svc.state})"
        for svc in services
        if svc.status != "enabled" or svc.state != "up"
    ]
    report("cinder volume service", problems, len(services))


def check_network(conn):
    try:
        agents = list(conn.network.agents())
    except Exception as exc:
        print(f"UNKNOWN - error listing network agents: {exc}")
        sys.exit(UNKNOWN)

    # NOTE: openstacksdk field names are "is_alive"/"is_admin_state_up" (verified against the
    # actual Agent resource class), NOT "alive"/"admin_state_up" like the raw JSON keys from
    # `openstack network agent list` -- using the wrong names here would silently mask every real
    # failure (getattr default always wins), so do NOT "simplify" this back without re-checking.
    problems = [
        f"{agent.binary} on {agent.host} (alive={agent.is_alive}, admin_state_up={agent.is_admin_state_up})"
        for agent in agents
        if not agent.is_alive or not agent.is_admin_state_up
    ]
    report("neutron network agent", problems, len(agents))


def check_masakari(conn, auth):
    # Masakari has no openstacksdk binding -- call the REST API directly via the same auth session.
    # NOT verified against a real Masakari deployment (none available in this environment) -- the
    # service_type below ("instance-ha", the value Masakari registers in Keystone by default) and
    # the "reserved"/"on_maintenance" -> CRITICAL mapping are best-effort. "reserved"/"on_maintenance"
    # are ADMIN-set states (can be intentional, e.g. planned maintenance), not necessarily failures --
    # review this logic against your real Masakari behavior before relying on it in production.
    from keystoneauth1 import loading, session

    try:
        loader = loading.get_plugin_loader("password")
        auth_plugin = loader.load_from_options(
            auth_url=auth["auth_url"],
            username=auth["username"],
            password=auth["password"],
            project_name=auth.get("project_name"),
            user_domain_name=auth.get("user_domain_name", "Default"),
            project_domain_name=auth.get("project_domain_name", "Default"),
        )
        sess = session.Session(auth=auth_plugin)
        endpoint = sess.get_endpoint(service_type="instance-ha", interface="public")
        if not endpoint:
            print("UNKNOWN - Masakari (instance-ha) endpoint not found in catalog")
            sys.exit(UNKNOWN)
        base_url = endpoint.rstrip("/")
        segment_resp = sess.get(f"{base_url}/segments")
        if segment_resp.status_code != 200:
            print(f"UNKNOWN - Masakari segments API returned HTTP {segment_resp.status_code}")
            sys.exit(UNKNOWN)
        segments = segment_resp.json().get("segments", [])
        hosts = []
        for segment in segments:
            segment_id = segment.get("uuid") or segment.get("id")
            if not segment_id:
                print("UNKNOWN - Masakari segment response has no uuid/id")
                sys.exit(UNKNOWN)
            host_resp = sess.get(f"{base_url}/segments/{segment_id}/hosts")
            if host_resp.status_code != 200:
                print(
                    "UNKNOWN - Masakari hosts API for segment "
                    f"{segment_id} returned HTTP {host_resp.status_code}"
                )
                sys.exit(UNKNOWN)
            hosts.extend(host_resp.json().get("hosts", []))
    except Exception as exc:
        print(f"UNKNOWN - error querying Masakari: {exc}")
        sys.exit(UNKNOWN)

    problems = [
        f"{h.get('name')} (reserved={h.get('reserved')}, on_maintenance={h.get('on_maintenance')})"
        for h in hosts
        if h.get("reserved") or h.get("on_maintenance") or h.get("failover_segment_id") is None
    ]
    report("masakari host", problems, len(hosts))


def main():
    parser = argparse.ArgumentParser(description="Check OpenStack service status (multi-cloud)")
    parser.add_argument("-c", "--cloud", required=True, help="Cloud name in clouds.yaml")
    parser.add_argument(
        "-s", "--service", required=True,
        choices=["compute", "volume", "network", "masakari"],
        help="Service type to check",
    )
    args = parser.parse_args()

    auth = load_auth(args.cloud)
    conn = connect(auth)

    if args.service == "compute":
        check_compute(conn)
    elif args.service == "volume":
        check_volume(conn)
    elif args.service == "network":
        check_network(conn)
    elif args.service == "masakari":
        check_masakari(conn, auth)


if __name__ == "__main__":
    main()
