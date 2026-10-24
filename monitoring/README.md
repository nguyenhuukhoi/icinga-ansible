# Operator monitoring

The active model deliberately splits ownership:

- [`openstack-director/`](openstack-director/README.md): six OpenStack Host objects checked by ICMP
  and the CPU, RAM and disk Apply Services. They use native `check_by_ssh` plus Linuxfabrik plugins.
- [`openstack-file/`](openstack-file/README.md): Nova, Cinder and Neutron API checks. The authoritative
  object file exists only in `zones.d/<master-zone>` on `master[0]`; native Icinga zone sync sends it
  to the peer. Credentials and the local plugin exist on both possible executor masters.

These are operator packages, not infrastructure roles. `icinga-ansible deploy/reconfigure` neither
creates nor deletes their monitoring objects. `backup-full` preserves both packages' runtime state,
and `restore-director` republishes the restored Director database after disaster recovery.
