# icinga-ansible

Ansible project để triển khai và vận hành **hạ tầng Icinga** trên Docker:

- Icinga 2 master/satellite/client topology, PKI và API;
- Icinga DB, Redis và Icinga Web 2;
- MariaDB standalone hoặc Galera 3+ node;
- Director module/schema (tuỳ chọn), backup/restore và rolling upgrade;
- vòng đời node: thêm, cấu hình lại và xoá master/satellite.

## Ranh giới quản lý

Project này **không tạo, đọc, đồng bộ hoặc xoá nội dung monitoring**. Ansible không quản lý
`Host`, `Service`, `CheckCommand`, `Notification`, apply rule hoặc bất kỳ file nào trong `zones.d`.
Operator tự quản lý object bằng Icinga Director/Web UI hoặc một quy trình static DSL độc lập ngoài
project này. Đặt file dưới `/etc/icinga-ansible/config/icinga2/zones.d` trên deployment node không có
tác dụng và `reconfigure` không vận chuyển chúng xuống node.

Với static HA, operator có thể đặt file trực tiếp trong `zones.d/<ZoneName>` trên master đầu tiên;
Icinga tự config-sync sang master peer. Đây là đồng bộ nội bộ của Icinga, không phải deployment node
ghi đè `zones.d`.

Credential của plugin chạy trên master được operator đặt trực tiếp trên từng master tại
`/etc/icinga-ansible/config/icinga2/secrets/`. Role chỉ tạo và bind-mount nguyên thư mục local này
vào container; không đọc hoặc sao chép secret từ deployment node.

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

[loadbalancer]

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
| `add-master` / `add-node` | Thêm master hoặc satellite đã có trong inventory |
| `remove-master` / `remove-node` | Xoá runtime của node được chỉ định |
| `backup-full` | Backup config, database, PKI và Web |
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
trước thao tác phá huỷ. Inventory trong repo và nội dung `conf.d/operator` không thuộc bundle này;
phải backup bằng SCM/pipeline operator riêng.

## Tự quản lý Host/Service/Check

Khuyến nghị dùng Director. Project chỉ enable module và migrate schema; operator tự Kickstart và
quản lý object trong UI. Ansible không import hoặc reconcile object Director.

Nếu dùng static DSL, hãy quản lý và triển khai bằng quy trình riêng của operator. Project cố ý không
đọc, validate, copy, mount hoặc xoá `zones.d`; sửa file monitoring không yêu cầu chạy `reconfigure`.

Xem mục 6–7 trong [QUICKSTART.md](QUICKSTART.md) để làm theo từng lệnh thêm/xóa node và dựng lại cụm
từ full backup; [OPERATIONS-RUNBOOK-VI.md](OPERATIONS-RUNBOOK-VI.md) là runbook vận hành/sự cố đầy
đủ. Ranh giới kỹ thuật nằm ở [design.md](design.md); giới hạn còn lại được ghi tại [TODO.md](TODO.md).
