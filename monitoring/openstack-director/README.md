# OpenStack monitoring through Director

This operator-owned package monitors the OpenStack nodes listed in inventory group
`[linuxfabrik_targets]`. It is intentionally separate from the `icinga-ansible` infrastructure role
and never writes or synchronizes `zones.d`.

Director owns six Host objects checked with `check_icmp` and three Service Apply Rules. The rules
generate 18 checks:

- CPU, RAM, and disk on every node through native `check_by_ssh` and Linuxfabrik v8.0.0.

Initial thresholds are CPU/RAM 80/90% and disk 85/95%. `apply-monitoring.yml` exposes six numeric
Data Fields on the three Apply Services. Change them in Director on master1:

1. Open **Icinga Director → Services → Service Apply Rules**.
2. Open `Linux CPU via SSH`, `Linux RAM via SSH`, or `Linux Disk via SSH`.
3. Change the corresponding warning/critical fields and deploy the pending Director configuration.

Warning must remain lower than critical and both must be between 1 and 100; the restricted SSH
dispatcher rejects invalid values. Later package reconciliation preserves threshold values changed in
the UI instead of resetting them to the template defaults. All three checks run every minute.
Nova, Cinder and Neutron are intentionally absent from Director; see `../openstack-file/`.

The `icinga-monitor` SSH account is unprivileged and its key is accepted only from the two Icinga
masters. A forced-command dispatcher allows only the three Linuxfabrik binaries and validates that
warning is lower than critical and both are percentages. No generic remote shell is allowed.

Run from the repository root on the deployment node:

```bash
cd /opt/icinga-ansible
source /path/to/venv/bin/activate
INV=/path/to/inventory

ansible-playbook -i "$INV" monitoring/openstack-director/provision-targets.yml
ansible-playbook -i "$INV" monitoring/openstack-director/kickstart-director.yml  # one-time/topology change
ansible-playbook -i "$INV" monitoring/openstack-director/apply-monitoring.yml
```

`apply-monitoring.yml` is the normal update path after editing `director-objects.json.j2`. It upserts
objects from `[linuxfabrik_targets]`, deploys with Director, force-runs every ICMP Host check and all
SSH Service checks, and
fails unless all are OK. Director's Web UI can still be used for later host/service changes; reconcile
those changes back into the JSON template if it remains the desired source of truth.

Install pinned Linuxfabrik v8.0.0 on every target before `provision-targets.yml`. Use the official
project and verify the downloaded artifact checksum: <https://github.com/Linuxfabrik/monitoring-plugins>.
The `by-ssh` guidance is at <https://docs.linuxfabrik.ch/monitoring-plugins/by-ssh.html>.
