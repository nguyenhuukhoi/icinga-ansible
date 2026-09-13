# OpenStack service monitoring without an admin role

The `check_openstack_service.py` plugin needs three administrative inventory
endpoints, but it never needs an API that changes cloud state. These example
overrides grant a dedicated `monitoring` role access only to:

- Nova `GET /os-services`
- Neutron `GET /agents`
- Cinder `GET /os-services`

Create a dedicated project and assign the project-scoped role before removing
the old admin assignment:

```bash
openstack role create monitoring
openstack project create --domain Default monitoring
openstack role add --user icinga-monitor --project monitoring monitoring
```

Set `project_name: monitoring` in the `devstack` entry of the Icinga
`clouds.yaml`. If that file is bind-mounted into the Icinga container, recreate
or restart the container after replacing the host file so the mount resolves
the new inode.

Install the policy files at the paths selected by each service configuration.
For the verified DevStack deployment these are:

```text
/etc/nova/policy.yaml
/etc/neutron/policy.json
/etc/cinder/policy.yaml
```

Restart only the API processes after installing the files.

## Cinder's second authorization gate

Cinder applies `volume_extension:services:index` at the API layer and then
applies `require_admin_context` again in `cinder.db.api.service_get_all`.
Consequently, a policy override alone still returns HTTP 403.

Do not relax the DB decorator or teach Cinder about a deployment-specific role.
Until the upstream fix is merged and available in the deployed release, apply
`cinder-service-list-policy.patch` to the exact Cinder source/package revision
in use. It keeps the DB admin gate intact and uses an internally elevated
context only for the global service lookup, after the named API policy has
authorized the request. This makes the fix work with any operator-selected
read-only role. Update, disable, freeze, thaw, failover, and other write paths
retain their normal admin policies.

Treat this as a temporary, version-controlled backport: validate it after every
Cinder upgrade and remove it once the upstream change is present. Do not
replace the global `context_is_admin` rule with `role:monitoring`, because that
would grant the role every Cinder admin API.

After all three read checks pass, remove the admin role:

```bash
openstack role remove --user icinga-monitor --project admin admin
openstack role remove --user icinga-monitor --project admin monitoring
openstack role assignment list --user icinga-monitor --names
```

Before production rollout, use a canary user containing only `monitoring` to
confirm that all three GET calls succeed and Nova/Neutron/Cinder update calls
return HTTP 403.
