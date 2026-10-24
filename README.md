# icinga-ansible

Ansible project để triển khai và vận hành **hạ tầng Icinga** trên Docker:

- Icinga 2 master/satellite/client topology, PKI và API;
- Icinga DB, Redis và Icinga Web 2;
- MariaDB standalone hoặc Galera 3+ node;
- Director và FileShipper trên `ca_host` (tuỳ chọn), backup/restore và rolling upgrade;
- vòng đời node: thêm, cấu hình lại và xoá master/satellite/client.

## Ranh giới quản lý

Các role hạ tầng **không tạo hoặc reconcile nội dung monitoring**. FileShipper là transport tuỳ chọn:
nó chỉ đưa file operator-owned vào package khi operator chủ động Director deploy. Vì vậy `deploy`,
`reconfigure` và vòng đời node không tự ý sửa `Host`, `Service`, `CheckCommand`, `Notification`, apply
rule hay file nguồn. Hai operator package tách biệt trong [`monitoring/`](monitoring/README.md) triển
khai đúng baseline OpenStack của dự án khi người vận hành chủ động chạy chúng. Đặt file dưới
`/etc/icinga-ansible/config/icinga2/zones.d` trên deployment node không có tác dụng.

Với static HA, operator có thể đặt file trực tiếp trong `zones.d/<ZoneName>` trên master đầu tiên;
Icinga tự config-sync sang master peer. Đây là đồng bộ nội bộ của Icinga, không phải deployment node
ghi đè `zones.d`.

Credential của plugin chạy trên master được operator đặt trực tiếp trên từng master tại
`/etc/icinga-ansible/icinga2/secrets/`. Thư mục này nằm sẵn trong cây config chính thức đang được
bind-mount RW vào `/data/etc/icinga2`, nên không có volume riêng và không sao chép secret qua node khác.

## Cấu trúc

```text
ansible/                 playbook, inventory mẫu, roles và playbook vận hành
etc/examples/            template globals.yml và passwords.yml
tools/icinga-ansible     CLI chính
tools/validate           syntax-check toàn bộ playbook
```

Repo chứa code. Cấu hình thật nằm riêng tại `/etc/icinga-ansible` (có thể đổi bằng
`ICINGA_ANSIBLE_CONFIG_DIR`) và không nên commit vào Git.

Trên managed node, mỗi service dùng một cây config bind-mount nguyên thư mục với `rw`:
`icinga2/`, `icingaweb2/`, `icingadb/`, `icingadb-redis/` và `mariadb/`. Ví dụ
`/etc/icinga-ansible/icingaweb2` được mount vào `/data/etc/icingaweb2`; file tạo hoặc sửa từ Web UI
được lưu trực tiếp trên host và không mất khi container được tạo lại.

## Khởi tạo nhanh

Yêu cầu: deployment node Linux, Python venv có Ansible, managed node Ubuntu có SSH/sudo.

```bash
python3 -m venv /path/to/venv
source /path/to/venv/bin/activate
python -m pip install -U pip ansible
ansible-galaxy collection install -r ansible/requirements.yml

./tools/icinga-ansible init-config
./tools/icinga-ansible genpwd
$EDITOR /etc/icinga-ansible/globals.yml
$EDITOR ansible/inventory/my-cluster

./tools/icinga-ansible bootstrap-servers -i ansible/inventory/my-cluster
./tools/icinga-ansible prechecks         -i ansible/inventory/my-cluster
./tools/icinga-ansible deploy            -i ansible/inventory/my-cluster
./tools/icinga-ansible check             -i ansible/inventory/my-cluster
```

Không chạy CLI bằng `sudo`; playbook tự `become` khi cần. Mỗi shell mới cần activate lại venv.

Ví dụ inventory 2 master + 3 Galera:

```ini
[all_hosts]
master1 ansible_host=10.0.0.11 ansible_user=ubuntu
master2 ansible_host=10.0.0.12 ansible_user=ubuntu
db1     ansible_host=10.0.0.21 ansible_user=ubuntu
db2     ansible_host=10.0.0.22 ansible_user=ubuntu
db3     ansible_host=10.0.0.23 ansible_user=ubuntu

[master]
master1
master2

[satellite]

[client]

[galera]
db1
db2
db3

[icinga:children]
master
satellite
```

Đặt `icinga_master_zone_name` trong `globals.yml` trước lần deploy đầu. Với `managed_db`, group
`galera` phải có đúng 1 node hoặc số lẻ từ 3 node trở lên.

## Lệnh vận hành

| Lệnh | Chức năng |
|---|---|
| `bootstrap-servers` | Cài Docker/chrony trên node hoàn toàn mới |
| `prechecks` | Kiểm tra inventory, topology, version và DB |
| `deploy` / `reconfigure` | Triển khai hoặc áp dụng lại cấu hình hạ tầng |
| `check` | Kiểm tra container, API, Web, Icinga DB, Redis và Galera |
| `add-master` / `add-node` | Thêm master hoặc satellite/client đã có trong inventory |
| `remove-master` / `remove-node` | Xoá runtime của node được chỉ định |
| `backup-full` | Backup inventory/topology, desired config, DB/PKI/Web và state từng Icinga endpoint |
| `restore-node-state` | Restore CA, config, cert và identity endpoint lên cụm hiện tại hoặc VM sạch |
| `upgrade-plan` / `upgrade` / `rollback` | Lập kế hoạch, nâng cấp và rollback |
| `destroy` | Xoá container/data/config runtime, giữ config/secrets trên deployment node |

Thêm node: thêm host vào inventory, bootstrap host nếu cần, rồi chạy `add-master` hoặc `add-node`.

Xoá node:

```bash
./tools/icinga-ansible remove-master -i ansible/inventory/my-cluster \
  -e target_host=master2 -e confirm=yes
# Sau khi lệnh thành công: xoá host khỏi inventory rồi đồng bộ topology còn lại.
./tools/icinga-ansible reconfigure -i ansible/inventory/my-cluster -t icinga2
./tools/icinga-ansible check       -i ansible/inventory/my-cluster
```

Không xoá CA host (`master[0]`) trước khi có kế hoạch chuyển CA/PKI. Với Galera, thay đổi membership
cần runbook DB riêng; các lệnh node ở trên dành cho endpoint Icinga.

`destroy` là thao tác không phục hồi:

```bash
./tools/icinga-ansible destroy -i ansible/inventory/my-cluster \
  -e confirm=yes-i-really-really-mean-it
```

Luôn chạy `backup-full`, kiểm tra `LATEST_COMPLETE`/manifest và copy cả bundle ra storage độc lập
trước thao tác phá huỷ. Bundle chứa inventory, metadata topology và nguyên cây Icinga 2 trên từng
endpoint, gồm `zones.d`, secrets/plugin, certificate và runtime identity. Git/vault vẫn là nguồn quản
lý khuyến nghị cho monitoring content; backup không biến project thành công cụ reconcile object.

## Tự quản lý Host/Service/Check

Khuyến nghị dùng Director. Core project chỉ enable module trên `ca_host` và migrate schema.
Operator có thể quản lý object trong UI, hoặc chạy package
[`monitoring/openstack-director`](monitoring/openstack-director/README.md) để reconcile 6 host ICMP và
18 CPU/RAM/disk checks qua `check_by_ssh`.

FileShipper có thể được bật cùng Director để ship DSL operator-owned mà vẫn có lịch sử deployment.
File nguồn nằm tại `/etc/icinga-ansible/icingaweb2/fileshipper/director-global/` trên `ca_host`; xem
phần “FileShipper trong Docker” của [QUICKSTART.md](QUICKSTART.md) để cài, thử thêm/sửa/xóa và dùng
Import Source.

Nếu dùng static DSL, hãy quản lý và triển khai bằng quy trình riêng của operator. Package
[`monitoring/openstack-file`](monitoring/openstack-file/README.md) là ví dụ đang dùng: nó chỉ ghi file
nguồn lên master1, để Icinga native config-sync sang master2, và không đi qua deployment/reconfigure.
Thư mục xuất hiện trong container vì toàn bộ cây config host được bind-mount RW. `remove-*`/`destroy`
xóa nguyên config của đúng target; hãy chạy `backup-full` và vẫn giữ monitoring content trong
Git/vault.

Xem [QUICKSTART-BACKUP-RESTORE.md](QUICKSTART-BACKUP-RESTORE.md) để làm theo ba kịch bản full restore;
mục 6–7 trong [QUICKSTART.md](QUICKSTART.md) có thêm/xóa node và giải thích chi tiết.
[OPERATIONS-RUNBOOK-VI.md](OPERATIONS-RUNBOOK-VI.md) là runbook vận hành/sự cố đầy đủ. Ranh giới kỹ
thuật nằm ở [design.md](design.md); giới hạn còn lại được ghi tại [TODO.md](TODO.md).
