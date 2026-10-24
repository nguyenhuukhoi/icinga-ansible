# OpenStack service checks through `zones.d`

This operator package monitors Nova, Cinder and Neutron from the Icinga masters themselves. It does
not use Director for these three checks and does not SSH to one controller as an execution point.
Both masters call the VIP parsed from the active service `auth_url`; loss of a controller or one
Icinga master therefore does not remove the checker.

`stage-static-config.yml` performs four bounded actions:

1. Reads the active `[keystone_authtoken]` credentials from Nova, Cinder and Neutron runtime configs
   on `openstack-controller01`. Secrets remain under `no_log` and temporary files are deleted.
2. Writes `/etc/icinga-ansible/icinga2/secrets/clouds.yaml` and the SDK plugin on both masters.
3. Writes `openstack-services.conf` only to
   `/etc/icinga-ansible/icinga2/zones.d/<icinga_master_zone_name>/` on `master[0]`.
4. Validates, reloads and waits until native Icinga zone sync exposes all three objects on each master.

The whole host directory is already mounted RW into the container, so no extra secret mount is needed.
The three profiles are `monitoring-nova`, `monitoring-cinder` and `monitoring-neutron`; Director never
stores these credentials.

Run independently from the infrastructure deploy:

```bash
cd /opt/icinga-ansible
source /path/to/venv/bin/activate
INV=/path/to/inventory

ansible-playbook -i "$INV" monitoring/openstack-file/stage-static-config.yml \
  -e @/etc/icinga-ansible/globals.yml -e @/etc/icinga-ansible/passwords.yml
./tools/icinga-ansible verify-monitoring -i "$INV" \
  -e monitoring_expected_service_count=21
```

The expected total `21` is 18 Director CPU/RAM/disk services plus these 3 `zones.d` services.
`backup-full` preserves the plugin, `clouds.yaml`, authoritative source file and Director DB.
