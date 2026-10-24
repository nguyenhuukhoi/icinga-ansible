# Quickstart icinga-ansible

Tài liệu này chỉ mô tả hạ tầng. Host, Service, CheckCommand, apply rule và Notification là nội dung
monitoring do operator tự tạo sau khi stack hoạt động.

## 1. Chuẩn bị deployment node

```bash
sudo apt update
sudo apt install -y python3-venv
sudo install -d -o "$(id -un)" -g "$(id -gn)" /path/to/venv
python3 -m venv /path/to/venv
source /path/to/venv/bin/activate
python -m pip install -U pip ansible
ansible-galaxy collection install -r ansible/requirements.yml
```

Managed node cần Ubuntu, SSH từ deployment node và user có passwordless sudo. Không trỏ
`ansible_python_interpreter` về venv của deployment node.

## 2. Tạo config và secret

```bash
./tools/icinga-ansible init-config
./tools/icinga-ansible genpwd
chmod 600 /etc/icinga-ansible/passwords.yml
```

Sửa `/etc/icinga-ansible/globals.yml`, tối thiểu kiểm tra:

- `icinga_image_versions`;
- `icinga_master_zone_name` (chỉ đổi trước deploy đầu tiên);
- `icinga_database_type` và `managed_db`/`external_db`;
- `enable_icingaweb2_modules`;
- proxy/registry CA nếu môi trường yêu cầu.

Các biến `docker_http_proxy`, `docker_https_proxy` và `docker_no_proxy` hoạt động cùng phạm vi với
Kolla-Ansible: chỉ cấu hình Docker Engine pull image. Tool không dùng chúng cho APT/download, không
ghi `/etc/environment`, không truyền vào container và không liên quan `/var/run/docker.sock`.

Có thể mã hoá secret bằng `ansible-vault encrypt /etc/icinga-ansible/passwords.yml` và truyền
tuỳ chọn Vault qua CLI.

## 3. Tạo inventory

Copy một file trong `ansible/inventory/` rồi sửa. Mỗi host có vai trò triển khai phải thuộc
`all_hosts`. Hai master và ba Galera độc lập có dạng:

```ini
[all_hosts]
icinga-master01 ansible_host=10.0.0.11 ansible_user=ubuntu
icinga-master02 ansible_host=10.0.0.12 ansible_user=ubuntu
galera01 ansible_host=10.0.0.21 ansible_user=ubuntu
galera02 ansible_host=10.0.0.22 ansible_user=ubuntu
galera03 ansible_host=10.0.0.23 ansible_user=ubuntu

[master]
icinga-master01
icinga-master02

[satellite]

[client]

[galera]
galera01
galera02
galera03

[icinga:children]
master
satellite
```

`master[0]` là CA host. Tên inventory của endpoint phải ổn định; không đổi tên node đang chạy như
một thay đổi thông thường.

## 4. Deploy

```bash
source /path/to/venv/bin/activate
./tools/validate
./tools/icinga-ansible bootstrap-servers -i ansible/inventory/my-cluster
./tools/icinga-ansible prechecks         -i ansible/inventory/my-cluster
./tools/icinga-ansible deploy            -i ansible/inventory/my-cluster
./tools/icinga-ansible check             -i ansible/inventory/my-cluster
./tools/icinga-ansible post-deploy       -i ansible/inventory/my-cluster
```

Web mặc định tại `http://<master>:8080/authentication/login`. User và password nằm trong
`/etc/icinga-ansible/passwords.yml`.

Sau deploy, nên chạy lại `reconfigure` một lần để kiểm tra idempotency và `check` lần nữa.

### 4.1. Cây config trên từng managed node

Role mount nguyên thư mục config với `rw`; không mount rời từng file:

| Service | Host | Container |
|---|---|---|
| Icinga 2 | `/etc/icinga-ansible/icinga2/` | `/data/etc/icinga2/` |
| Icinga Web 2 (Director chỉ trên `ca_host`/`icinga-master01`) | `/etc/icinga-ansible/icingaweb2/` | `/data/etc/icingaweb2/` |
| Icinga DB | `/etc/icinga-ansible/icingadb/` | `/etc/icingadb/` |
| Redis | `/etc/icinga-ansible/icingadb-redis/` | `/usr/local/etc/redis/` |
| MariaDB/Galera | `/etc/icinga-ansible/mariadb/` | `/etc/mysql/conf.d/` |

Ví dụ, khi tạo hoặc sửa Resource trên Icinga Web UI, `resources.ini` được ghi thẳng tại
`/etc/icinga-ansible/icingaweb2/resources.ini` của đúng master đang phục vụ request. HA Web hiện không
đồng bộ filesystem giữa hai master; nếu truy cập trực tiếp từng master thì phải giữ config hai phía
nhất quán hoặc dùng VIP/stickiness phù hợp. Template Web chỉ seed khi file chưa tồn tại nên
`reconfigure` không ghi đè thay đổi từ UI.

`/var/lib/icinga-ansible` vẫn chỉ chứa runtime/data. Lần deploy đầu sau khi nâng cấp thiết kế này sẽ
migrate file còn thiếu từ cây config cũ trong `/var/lib` sang `/etc`, giữ file đang có trong `/etc` làm
bản ưu tiên.

## 5. Nội dung monitoring do operator quản lý

Role hạ tầng không sinh và không vận chuyển object monitoring. Hai package operator dưới
`monitoring/` chỉ chạy khi bạn chủ động gọi playbook; `deploy`, `reconfigure`, thêm hoặc xóa node
không tự chạy chúng.

### Director

Bật `director` trong `enable_icingaweb2_modules`. Ansible chỉ tạo DB, migrate schema và enable
module trên `ca_host` (host đầu tiên trong `[master]`, ví dụ `icinga-master01`). Các master khác
vẫn phục vụ Icinga DB Web nhưng không có module, resource DB, config hay daemon Director.
Operator truy cập Web UI của `ca_host` để quản lý thủ công. Với baseline hiện tại, chạy package
`monitoring/openstack-director`: Director quản lý 6 Host dùng `check_icmp` và 18 Service CPU/RAM/disk
dùng `check_by_ssh`; Nova/Cinder/Neutron không nằm trong Director.

### Static DSL

Static DSL nằm ngoài role hạ tầng. `/etc/icinga-ansible/config/icinga2/zones.d` trên deployment node
không phải nguồn cấu hình. Package `monitoring/openstack-file` trích ba credential service lúc chạy,
ghi plugin/`clouds.yaml` lên cả hai master, chỉ ghi object Nova/Cinder/Neutron vào
`zones.d/<master-zone>` của `icinga-master01`, rồi để Icinga native config-sync sang `icinga-master02`.

Credential API là local trên từng master. Role tạo thư mục
`/etc/icinga-ansible/icinga2/secrets/` ngay trong cây config chính thức đã được mount RW vào container;
không cần volume riêng. Core role không render file bên trong; operator package nói trên mới ghi
`clouds.yaml`. `remove-*` và `destroy` xóa toàn bộ config của target, gồm cả credential local, nên phải
chạy `backup-full` trước.

### Triển khai baseline OpenStack

Inventory cần có nhóm `[linuxfabrik_targets]` cho 6 node OpenStack và SSH key quản trị để provision.
Sau khi cài đúng Linuxfabrik v8.0.0 trên các target, chạy:

```bash
ansible-playbook -i "$INV" monitoring/openstack-director/provision-targets.yml
ansible-playbook -i "$INV" monitoring/openstack-director/kickstart-director.yml  # lần đầu/topology đổi
ansible-playbook -i "$INV" monitoring/openstack-director/apply-monitoring.yml

ansible-playbook -i "$INV" monitoring/openstack-file/stage-static-config.yml \
  -e @/etc/icinga-ansible/globals.yml -e @/etc/icinga-ansible/passwords.yml

./tools/icinga-ansible check -i "$INV"
./tools/icinga-ansible verify-monitoring -i "$INV" \
  -e monitoring_expected_service_count=21
```

`apply-monitoring.yml` force-run và kiểm tra 6 Host ICMP cùng 18 Service SSH. Package static test API
Nova/Cinder/Neutron từ từng master, validate config trước reload và chờ ba object sync sang cả hai
master. Threshold CPU/RAM/disk hiện thành Data Fields trong từng Service Apply Rule trên Director UI;
giá trị sửa trên UI được giữ nguyên ở các lần reconcile sau. Chi tiết biến, đường dẫn và mô hình bảo
mật nằm trong [`monitoring/README.md`](monitoring/README.md).

## 6. Thêm, sửa và xoá node

Các lệnh trong phần này chỉ quản lý **node hạ tầng** chạy container Icinga. Chúng không tạo, sửa hay
xóa Host/Service/CheckCommand của operator, không triển khai `zones.d` và không import object vào
Director.

Quy ước ví dụ:

```bash
cd /opt/icinga-ansible
source /path/to/venv/bin/activate
INV=ansible/inventory/my-cluster
```

Trước mỗi thay đổi topology, lưu một bản inventory, backup cluster và kiểm tra trạng thái ban đầu:

```bash
cp -a "$INV" "$INV.before-$(date +%Y%m%d-%H%M%S)"
./tools/icinga-ansible check       -i "$INV"
./tools/icinga-ansible backup-full -i "$INV"
```

### 6.1. Thêm master thứ hai

Project hỗ trợ tối đa hai master. Nếu inventory đã có hai master, `prechecks` sẽ chặn việc thêm
master thứ ba. Tên logic của node, ví dụ `icinga-master02`, phải ổn định dù IP có thể thay đổi.

1. Tạo VM mới và xác nhận deployment node SSH/sudo được vào VM.
2. Thêm node vào cả `[all_hosts]` và `[master]`. Giữ master đang làm CA ở dòng đầu tiên.
3. Chỉ bootstrap host mới bằng `--limit`.
4. Chạy `prechecks` và `add-master` với **inventory đầy đủ**, không dùng `--limit`. Các endpoint cũ
   cũng cần được render lại `zones.conf`.
5. Chạy `check` trên toàn cụm.

Ví dụ inventory sau khi sửa:

```ini
[all_hosts]
icinga-master01 ansible_host=10.0.0.11 ansible_user=ubuntu
icinga-master02 ansible_host=10.0.0.12 ansible_user=ubuntu

[master]
icinga-master01
icinga-master02
```

Thực hiện:

```bash
ansible -i "$INV" icinga-master02 -m ping
./tools/icinga-ansible bootstrap-servers -i "$INV" --limit icinga-master02
./tools/icinga-ansible prechecks         -i "$INV"
./tools/icinga-ansible add-master        -i "$INV"
./tools/icinga-ansible check             -i "$INV"
```

Không dùng `add-master --limit icinga-master02`: node mới có thể lên nhưng master/satellite cũ vẫn giữ
topology cũ.

### 6.2. Thêm một hoặc hai satellite

Mỗi satellite phải có trong `[all_hosts]`, `[satellite]` và xuất hiện đúng một lần trong
`satellite_zones` tại `/etc/icinga-ansible/globals.yml`. Mỗi zone có một hoặc hai member.

Ví dụ thêm hai node HA trong cùng zone:

```ini
[all_hosts]
icinga-satellite01 ansible_host=10.0.0.31 ansible_user=ubuntu
icinga-satellite02 ansible_host=10.0.0.32 ansible_user=ubuntu

[satellite]
icinga-satellite01
icinga-satellite02
```

```yaml
satellite_zones:
  - name: "openstack-zone"
    members: ["icinga-satellite01", "icinga-satellite02"]
    parent: "master"
```

Thực hiện:

```bash
ansible -i "$INV" 'icinga-satellite01:icinga-satellite02' -m ping
./tools/icinga-ansible bootstrap-servers -i "$INV" --limit 'icinga-satellite01,icinga-satellite02'
./tools/icinga-ansible prechecks         -i "$INV"
./tools/icinga-ansible add-node          -i "$INV"
./tools/icinga-ansible check             -i "$INV"
```

`add-node` phải dùng inventory đầy đủ và dùng được cho cả satellite lẫn client. Nội dung monitoring
phải được operator triển khai bằng pipeline riêng sau khi hạ tầng đã PASS.

### 6.3. Xoá satellite

Thứ tự là bắt buộc: **remove khi target vẫn còn trong inventory**, sau đó mới sửa inventory và
`satellite_zones`. Lệnh `remove-node` phá huỷ container, dữ liệu và config Icinga 2 trên đúng target;
nó không xóa VM.

```bash
# 1. Target vẫn phải còn trong [all_hosts] và [satellite].
./tools/icinga-ansible remove-node -i "$INV" \
  -e target_host=icinga-satellite02 -e confirm=yes

# 2. Chỉ sau khi lệnh trên thành công:
#    - xóa icinga-satellite02 khỏi [satellite] và [all_hosts];
#    - xóa icinga-satellite02 khỏi satellite_zones[].members;
#    - nếu zone hết member, xóa cả zone.
nano "$INV"
sudo nano /etc/icinga-ansible/globals.yml

# 3. Hội tụ toàn bộ endpoint còn lại. Không dùng --limit.
./tools/icinga-ansible prechecks   -i "$INV"
./tools/icinga-ansible reconfigure -i "$INV" -t icinga2
./tools/icinga-ansible check       -i "$INV"
```

Chỉ xóa VM sau khi `check` PASS. Xóa satellite cuối cùng của một zone không ảnh hưởng database hoặc
Web, nhưng object monitoring do operator tự quản lý có thể còn tham chiếu `command_endpoint`; hãy
kiểm tra và sửa phần đó trong pipeline monitoring riêng.

Client dùng cùng lệnh `remove-node`. Target phải còn trong `[client]` và `[all_hosts]` lúc chạy;
sau khi PASS, xóa khỏi hai group rồi `reconfigure -t icinga2`. Client không thuộc
`satellite_zones`, nên không sửa biến đó.

Để xóa đồng thời hai satellite, giữ cả hai trong inventory và `satellite_zones`, truyền danh sách
phân cách bằng dấu phẩy. Playbook kiểm tra toàn bộ target trước rồi thực thi song song theo Ansible
forks:

```bash
./tools/icinga-ansible remove-node -i "$INV" \
  -e target_host=icinga-satellite01,icinga-satellite02 -e confirm=yes
# Sau khi PASS mới xóa cả hai khỏi inventory/satellite_zones rồi reconfigure toàn cụm còn lại.
```

### 6.4. Xoá master

Không được xóa master cuối cùng. `master[0]` là `ca_host`, vì vậy playbook chặn xóa trực tiếp node
này. Quy trình thông thường chỉ xóa master thứ hai:

```bash
# 1. icinga-master02 vẫn còn trong inventory.
./tools/icinga-ansible remove-master -i "$INV" \
  -e target_host=icinga-master02 -e confirm=yes

# 2. Sau khi thành công, xóa icinga-master02 khỏi [master] và [all_hosts].
nano "$INV"

# 3. Cập nhật topology trên tất cả endpoint còn lại.
./tools/icinga-ansible prechecks   -i "$INV"
./tools/icinga-ansible reconfigure -i "$INV" -t icinga2
./tools/icinga-ansible check       -i "$INV"
```

`remove-master` xóa workload Icinga 2, Redis, Icinga DB và Web trên target, nhưng giữ MariaDB nếu
host đó kiêm role `[galera]`. Không đổi thứ tự `[master]` chỉ để vượt guard CA. Muốn thay `ca_host`
phải lập kế hoạch chuyển CA riêng và xác nhận master mới có đủ `ca.crt`/`ca.key` trước khi xóa CA cũ.

### 6.5. Sửa IP hoặc membership topology

Nếu chỉ đổi IP mà giữ nguyên node, giữ nguyên inventory hostname và sửa `ansible_host`. Nếu đổi
membership satellite, sửa đồng thời inventory và `satellite_zones`, sau đó:

```bash
./tools/icinga-ansible prechecks   -i "$INV"
./tools/icinga-ansible reconfigure -i "$INV" -t icinga2
./tools/icinga-ansible check       -i "$INV"
```

Không đổi `icinga_master_zone_name` trên cluster đã có dữ liệu. Các lệnh node cũng không thay đổi
membership Galera; thêm/xóa Galera cần kế hoạch quorum, SST/IST và backup riêng.

## 7. Backup, destroy và khôi phục

Mục này là tài liệu chính, có đủ ba quy trình: restore trên hệ thống hiện tại, VM sạch cùng IP và
VM sạch khác IP. [QUICKSTART-BACKUP-RESTORE.md](QUICKSTART-BACKUP-RESTORE.md) chỉ là checklist rút gọn;
khi hai tài liệu có khác biệt, làm theo file này.

### 7.1. Tạo và xác minh full backup

```bash
INV=ansible/inventory/my-cluster
./tools/icinga-ansible check       -i "$INV"
./tools/icinga-ansible backup-full -i "$INV"
```

Mặc định bundle nằm tại `/var/backups/icinga-ansible-config` trên deployment node:

```text
config-<timestamp>.tar.gz
inventory-<timestamp>.tar.gz
cluster-<timestamp>.json
nodes/icinga2-<endpoint>-<timestamp>.tar.gz
icingaweb2-<master>-<timestamp>.tar.gz
database/db-full-<timestamp>.xb.gz
database/LATEST_FULL
pki/pki-<timestamp>.tar.gz
manifest-<timestamp>.sha256
LATEST_COMPLETE
```

Chỉ dùng timestamp được công bố trong `LATEST_COMPLETE`. Xác minh toàn bộ artifact trước khi copy
ra storage độc lập:

```bash
BACKUP_ROOT=/var/backups/icinga-ansible-config
BACKUP_TS="$(cat "$BACKUP_ROOT/LATEST_COMPLETE")"

cd "$BACKUP_ROOT"
sha256sum --strict -c "manifest-$BACKUP_TS.sha256"
test "$(cat database/LATEST_FULL)" = "$BACKUP_TS"
find . -maxdepth 2 -type f -name "*$BACKUP_TS*" -ls
```

Copy **cả cây thư mục**, không chỉ file DB, sang storage ngoài deployment node. Inventory nằm trong
`inventory-*.tar.gz`; revision code, logical topology, IP và image version nằm trong
`cluster-*.json`. Với external DB, DBA phải backup/restore database bằng quy trình riêng;
`backup-full` vẫn backup inventory, node-state và CA/PKI.

`backup-full` backup nguyên `/etc/icinga-ansible` của mọi managed node và backup riêng identity
Icinga 2 của từng endpoint, nên có `zones.d`, `secrets`, custom plugin, certificate và `icingadb.env`
trên master. Nội dung nằm ngoài các cây đã nêu vẫn phải lưu trong Git/vault/storage riêng; backup
không thay thế source control.

Ví dụ copy off-site không xóa generation cũ ở đích:

```bash
rsync -a "$BACKUP_ROOT/" backup-host:/srv/backup/icinga/prod/
```

### 7.2. Trường hợp 1: restore trên hệ thống hiện tại

Dùng luồng này khi các VM và topology vẫn còn, nhưng cần đưa toàn bộ config, CA/PKI, identity endpoint,
Web và database về đúng generation backup. `restore_mode=existing` chỉ chấp nhận khi CA đang chạy khớp
CA trong bundle. Trước khi ghi đè, tool tự lưu node-state hiện tại vào
`/var/backups/icinga-ansible-pre-restore/` trên từng endpoint.

```bash
cd /opt/icinga-ansible
source /path/to/venv/bin/activate
INV=ansible/inventory/my-cluster
BACKUP_ROOT=/var/backups/icinga-ansible-config
BACKUP_TS="$(cat "$BACKUP_ROOT/LATEST_COMPLETE")"
MONITORING_SERVICE_COUNT=21    # thay bằng baseline thật

cd "$BACKUP_ROOT"
sha256sum --strict -c "manifest-$BACKUP_TS.sha256"
cd /opt/icinga-ansible

CONFIRM=yes-i-really-really-mean-it ./tools/icinga-ansible restore-config \
  --config-backup "$BACKUP_ROOT/config-$BACKUP_TS.tar.gz"

./tools/icinga-ansible restore-node-state -i "$INV" \
  -e restore_mode=existing -e restore_backup_ts="$BACKUP_TS" \
  -e confirm=yes-i-really-really-mean-it

# restore-node-state để service dừng; dựng runtime tạm trước khi restore DB.
./tools/icinga-ansible deploy -i "$INV"

./tools/icinga-ansible mariadb-recovery -i "$INV" \
  -e recovery_mode=restore-backup -e restore_backup_tag=full \
  -e restore_backup_ts="$BACKUP_TS" -e confirm=yes

./tools/icinga-ansible recover-db-only -i "$INV" -e confirm=yes
./tools/icinga-ansible restore-web -i "$INV" \
  -e restore_backup_ts="$BACKUP_TS" -e confirm=yes

./tools/icinga-ansible deploy -i "$INV"
./tools/icinga-ansible restore-director -i "$INV" -e confirm=yes
./tools/icinga-ansible check -i "$INV"
./tools/icinga-ansible verify-monitoring -i "$INV" \
  -e monitoring_expected_service_count="$MONITORING_SERVICE_COUNT"
```

Không chạy `bootstrap-servers` trong case này. Nếu CA hiện tại không khớp bundle, dừng lại: hoặc chọn
đúng generation của chính cluster đó, hoặc dựng VM sạch theo case 2/3; không ép `restore_mode=existing`.

### 7.3. Trường hợp 2: VM sạch, cùng IP và topology

Quy trình dưới đây áp dụng khi dựng lại toàn bộ topology 2 master + 3 Galera trên VM sạch nhưng giữ
nguyên hostname logic, membership và IP. Dùng đúng version code, container image và MariaDB đã tạo
backup; chỉ upgrade sau khi restore PASS.

Trước khi bắt đầu, đưa nguyên cây backup từ storage ngoài về đúng layout, clone revision code ghi
trong `cluster-*.json`, tạo venv và cài collection. Tắt/xóa hoàn toàn VM cũ và bảo đảm không có hai VM
dùng cùng IP. Phải giữ nguyên tên logic, thứ tự và membership group để node archive ánh xạ đúng.

```bash
cd /opt/icinga-ansible
source /path/to/venv/bin/activate
BACKUP_ROOT=/var/backups/icinga-ansible-config
BACKUP_TS="$(cat "$BACKUP_ROOT/LATEST_COMPLETE")"
MONITORING_SERVICE_COUNT=21    # thay bằng baseline thật

mkdir -p restore-inventory
tar -xzf "$BACKUP_ROOT/inventory-$BACKUP_TS.tar.gz" -C restore-inventory
INV=restore-inventory/my-cluster    # thay bằng tên inventory vừa giải nén

cd "$BACKUP_ROOT"
sha256sum --strict -c "manifest-$BACKUP_TS.sha256"
cd /opt/icinga-ansible

# VM sạch có SSH host key mới; thay danh sách bằng IP thật trong inventory.
for ip in 10.0.0.11 10.0.0.12 10.0.0.21 10.0.0.22 10.0.0.23; do
  ssh-keygen -f ~/.ssh/known_hosts -R "$ip"
  ssh -o StrictHostKeyChecking=accept-new -i ~/.ssh/monitoring-lab-key ubuntu@"$ip" true
done
```

Khôi phục desired state trên deployment node. Nếu `/etc/icinga-ansible` đang có dữ liệu, bắt buộc
dùng đúng biến môi trường `CONFIRM`; đây không phải Ansible extra-var `-e confirm=...`:

```bash
CONFIRM=yes-i-really-really-mean-it ./tools/icinga-ansible restore-config \
  --config-backup "$BACKUP_ROOT/config-$BACKUP_TS.tar.gz"
```

Sau `restore-config`, kiểm tra lại `/etc/icinga-ansible/globals.yml`. Nếu topology mới không có các
satellite cũ, xóa chúng khỏi `satellite_zones`; nếu thêm satellite mới, khai mỗi node đúng một zone
trước khi chạy precheck. Không chạy `init-config` hoặc `genpwd`, vì làm vậy sẽ đổi secret cũ.

```bash
nano "$INV"
sudo nano /etc/icinga-ansible/globals.yml
ansible-inventory -i "$INV" --graph
ansible -i "$INV" all_hosts -m ping
```

Bootstrap toàn bộ host mới rồi restore CA, config, certificate và identity của từng endpoint trước
deploy đầu tiên:

```bash
./tools/icinga-ansible bootstrap-servers -i "$INV"
./tools/icinga-ansible prechecks         -i "$INV"
./tools/icinga-ansible restore-node-state -i "$INV" \
  -e restore_mode=clean -e restore_backup_ts="$BACKUP_TS" \
  -e confirm=yes-i-really-really-mean-it
```

`restore-node-state` từ chối VM đã có CA/cert/config trong mode `clean`, xác minh manifest, CA/key,
certificate từng endpoint và logical topology trước khi ghi dữ liệu.

Dựng runtime tạm, restore physical database, khôi phục environment ID rồi restore Web:

```bash
./tools/icinga-ansible pull   -i "$INV"
./tools/icinga-ansible deploy -i "$INV"

./tools/icinga-ansible mariadb-recovery -i "$INV" \
  -e recovery_mode=restore-backup \
  -e restore_backup_tag=full \
  -e restore_backup_ts="$BACKUP_TS" \
  -e confirm=yes

./tools/icinga-ansible recover-db-only -i "$INV" -e confirm=yes

./tools/icinga-ansible restore-web -i "$INV" \
  -e restore_backup_ts="$BACKUP_TS" -e confirm=yes

./tools/icinga-ansible deploy -i "$INV"
./tools/icinga-ansible restore-director -i "$INV" -e confirm=yes
./tools/icinga-ansible check  -i "$INV"
./tools/icinga-ansible verify-monitoring -i "$INV" \
  -e monitoring_expected_service_count="$MONITORING_SERVICE_COUNT"
```

`restore-web` yêu cầu tên các master mới khớp tên master trong bundle. Nếu đổi tên hoặc thêm master
so với thời điểm backup, không đổi tên archive để ép restore; hãy bỏ qua bước này, dựng Web config
mới rồi chuyển thủ công phần cần giữ sau khi review.

`zones.d`, plugin và credential đã trở lại từ node archive; `deploy` giữ chúng và chỉ hội tụ phần hạ
tầng do role quản lý. `restore-director` chỉ publish lại object đã có trong Director DB; nó không tạo
hoặc sửa nội dung monitoring. `verify-monitoring` chờ đúng số service có kết quả live `OK` trên cả hai
master; thay `21` bằng baseline thật của cụm.

Bài destructive regression ngày 2026-10-24 đã xóa và dựng lại 2 master + 3 Galera bằng đúng năm IP
cũ, rồi lặp lại trên năm IP mới. Cả hai lần đều xác nhận CA/cert, environment ID, Icinga API, Web
login, Icinga DB heartbeat/config sync, Director chỉ `ca_host` và Galera 3/3 healthy.

### 7.4. Trường hợp 3: VM sạch, khác IP nhưng cùng topology

Thực hiện toàn bộ case 2, nhưng sau khi giải nén inventory và **trước** `bootstrap-servers`, tạo bản
inventory DR rồi chỉ đổi `ansible_host`. Giữ nguyên inventory hostname (`icinga-master01`,
`icinga-master02`...), thứ
tự và membership các group `master`, `satellite`, `client`, `galera`, `icinga_master_zone_name` và
`icinga_database_type`.

```bash
cp restore-inventory/my-cluster restore-inventory/my-cluster-new-ip
INV=restore-inventory/my-cluster-new-ip
nano "$INV"                            # chỉ đổi ansible_host
ansible-inventory -i "$INV" --graph
ansible -i "$INV" all_hosts -m ping
```

Sau đó chạy đúng chuỗi lệnh trong case 2, bắt đầu từ `restore-config`. `restore-node-state` kiểm tra
logical topology nhưng cho phép IP đổi; lần `deploy` đầu sẽ render lại `zones.conf` theo IP mới.
`restore-director` tự reconcile endpoint API sang `ansible_host` của `master[0]` mới trước khi publish.

Trước `verify-monitoring`, cập nhật allowlist nằm **trên các hệ thống được monitor** sang IP master mới:

- `from="..."` của monitoring key trong `authorized_keys`;
- `/etc/hosts.allow` nếu target dùng `sshd: ALL` trong `/etc/hosts.deny`;
- firewall, security group và ACL mạng liên quan.

Các file trên target OpenStack không thuộc full backup của cluster Icinga và tool không tự sửa chúng.
Chỉ coi restore thành công sau khi `check` không có host lỗi và `verify-monitoring` đạt đủ baseline.

### 7.5. Trường hợp chỉ import database ứng dụng vào cụm mới

Luồng này dựng Galera sạch, giữ nguyên system DB của cụm mới và chỉ mang theo:

- `icingadb`: dữ liệu current state và lịch sử Icinga DB;
- `icingaweb2`: user/preference nằm trong database;
- `director`: object/config của Director.

Tuyệt đối không dùng `--all-databases` và không import `mysql`, `sys`, `performance_schema` hoặc
`information_schema`. User/grant, root credential, system table và Galera state phải do cụm đích mới
tạo. Ví dụ dưới đây chạy trên deployment node bằng user thường đã activate virtualenv.

Khai biến và kiểm tra hai inventory trước:

```bash
cd /opt/icinga-ansible
source /path/to/venv/bin/activate

SOURCE_INV=inventory-source
TARGET_INV=inventory-new
SOURCE_DB_HOST=galera01      # galera[0] trong inventory nguồn
TARGET_DB_HOST=galera01      # galera[0] trong inventory đích
BACKUP_ROOT=/var/backups/icinga-ansible-config/logical
DUMP_TS="$(date +%Y%m%d-%H%M%S)"
DUMP_FILE="icinga-app-db-$DUMP_TS.sql.gz"

ansible-inventory -i "$SOURCE_INV" --graph
ansible-inventory -i "$TARGET_INV" --graph
ansible -i "$SOURCE_INV" all_hosts -m ping
ansible -i "$TARGET_INV" all_hosts -m ping
```

Tạo logical dump trên `galera[0]` nguồn. `--single-transaction` lấy snapshot nhất quán mà không cần
dừng cụm nguồn:

```bash
ansible -i "$SOURCE_INV" "$SOURCE_DB_HOST" -b -m shell -a \
  "docker exec mariadb mariadb-dump \
    --defaults-extra-file=/var/lib/mysql/.my-healthcheck.cnf \
    --single-transaction --quick --routines --events --triggers --hex-blob \
    --add-drop-database --databases icingadb icingaweb2 director \
    | gzip -1 > /tmp/$DUMP_FILE"

mkdir -p .tmp
ansible -i "$SOURCE_INV" "$SOURCE_DB_HOST" -b -m fetch -a \
  "src=/tmp/$DUMP_FILE dest=$PWD/.tmp/$DUMP_FILE flat=yes"

sudo install -d -m 0750 "$BACKUP_ROOT"
gzip -t ".tmp/$DUMP_FILE"
(cd .tmp && sha256sum "$DUMP_FILE") | tee ".tmp/$DUMP_FILE.sha256"
sudo install -m 0640 ".tmp/$DUMP_FILE" "$BACKUP_ROOT/$DUMP_FILE"
sudo install -m 0640 ".tmp/$DUMP_FILE.sha256" "$BACKUP_ROOT/$DUMP_FILE.sha256"
```

Xác minh phạm vi dump. Lệnh `test` phải PASS; nếu không, dừng lại và không import:

```bash
ACTUAL_DATABASES="$(gzip -cd ".tmp/$DUMP_FILE" \
  | sed -n 's/^-- Current Database: `\([^`]*\)`$/\1/p' \
  | sort -u)"
EXPECTED_DATABASES="$(printf '%s\n' director icingadb icingaweb2)"

printf '%s\n' "$ACTUAL_DATABASES"
test "$ACTUAL_DATABASES" = "$EXPECTED_DATABASES"
```

Đồng bộ cả file dump và checksum sang storage ngoài deployment node trước khi tiếp tục.

Dựng cụm đích sạch bằng **đúng version nguồn**. Không nâng version đồng thời với DR; restore xong mới
dùng quy trình `upgrade` riêng:

```bash
./tools/icinga-ansible bootstrap-servers -i "$TARGET_INV"
./tools/icinga-ansible prechecks         -i "$TARGET_INV"
./tools/icinga-ansible pull              -i "$TARGET_INV"
./tools/icinga-ansible deploy            -i "$TARGET_INV"
./tools/icinga-ansible check             -i "$TARGET_INV"
```

Lần deploy sạch tạo service user/grant trong system DB đích. Ghi lại baseline trước import:

```bash
ansible -i "$TARGET_INV" "$TARGET_DB_HOST" -b -m shell -a \
  'docker exec mariadb mariadb \
    --defaults-extra-file=/var/lib/mysql/.my-healthcheck.cnf -N -e \
    "SELECT COUNT(*) FROM mysql.global_priv; CHECKSUM TABLE mysql.global_priv; \
     SELECT COUNT(*) FROM icingadb.host;"'
```

Dừng publisher/consumer DB trên mọi master. **Không dừng `icingadb-redis`** vì
`recover-db-only` cần Redis đang chạy để flush stream tạm:

```bash
ansible -i "$TARGET_INV" master -b -m shell -a '
  for c in icingaweb2-director-daemon icingaweb2 icingadb icinga2; do
    docker inspect "$c" >/dev/null 2>&1 && docker stop "$c" || true
  done'
```

Stage dump lên `galera[0]` đích, kiểm tra lại rồi import:

```bash
ansible -i "$TARGET_INV" "$TARGET_DB_HOST" -b -m copy -a \
  "src=$PWD/.tmp/$DUMP_FILE dest=/tmp/$DUMP_FILE mode=0600"

ansible -i "$TARGET_INV" "$TARGET_DB_HOST" -b -m shell -a \
  "gzip -t /tmp/$DUMP_FILE && sha256sum /tmp/$DUMP_FILE && \
   gzip -cd /tmp/$DUMP_FILE \
     | grep '^-- Current Database:'"

ansible -i "$TARGET_INV" "$TARGET_DB_HOST" -b -m shell -a \
  "gzip -dc /tmp/$DUMP_FILE \
    | docker exec -i mariadb mariadb \
        --defaults-extra-file=/var/lib/mysql/.my-healthcheck.cnf"
```

Ngay sau import, xác minh app DB đã có dữ liệu nhưng system DB không đổi. Count/checksum
`mysql.global_priv` phải khớp baseline đích, không phải cụm nguồn:

```bash
ansible -i "$TARGET_INV" "$TARGET_DB_HOST" -b -m shell -a \
  'docker exec mariadb mariadb \
    --defaults-extra-file=/var/lib/mysql/.my-healthcheck.cnf -N -e \
    "SELECT COUNT(*) FROM mysql.global_priv; CHECKSUM TABLE mysql.global_priv; \
     SELECT COUNT(*) FROM icingadb.host; \
     SELECT COUNT(*) FROM icingaweb2.icingaweb_user; \
     SELECT COUNT(*) FROM director.director_schema_migration; \
     SHOW STATUS LIKE '\''wsrep_cluster_size'\''; \
     SHOW STATUS LIKE '\''wsrep_ready'\'';"'
```

Phục hồi environment ID cũ lên mọi master, hội tụ service và chạy deep check:

```bash
./tools/icinga-ansible recover-db-only -i "$TARGET_INV" -e confirm=yes
./tools/icinga-ansible deploy           -i "$TARGET_INV"
./tools/icinga-ansible check            -i "$TARGET_INV"
```

Xác minh hai master dùng cùng environment ID và lịch sử vẫn đọc được:

```bash
ansible -i "$TARGET_INV" master -b \
  -a 'cat /var/lib/icinga-ansible/icinga2/data/var/lib/icinga2/icingadb.env'

ansible -i "$TARGET_INV" "$TARGET_DB_HOST" -b -m shell -a \
  'docker exec mariadb mariadb \
    --defaults-extra-file=/var/lib/mysql/.my-healthcheck.cnf -N -e \
    "SELECT '\''history'\'',COUNT(*) FROM icingadb.history \
     UNION ALL SELECT '\''state_history'\'',COUNT(*) FROM icingadb.state_history \
     UNION ALL SELECT '\''sla_history_state'\'',COUNT(*) FROM icingadb.sla_history_state;"'
```

Sau khi toàn bộ kiểm tra PASS, xóa bản stage trên Galera đích; giữ bản backup trên deployment node và
storage ngoài:

```bash
ansible -i "$TARGET_INV" "$TARGET_DB_HOST" -b -m file -a \
  "path=/tmp/$DUMP_FILE state=absent"
```

Giới hạn của DB-only restore:

1. Không restore CA/PKI. Nếu không chạy `restore-pki` riêng trước deploy đầu tiên, cụm có CA mới và
   agent/client cũ phải enroll lại.
2. Không restore filesystem config Web. Thay đổi UI nằm trong file INI chỉ trở lại qua `restore-web`.
3. Không restore `zones.d`, plugin, SSH key hoặc credential operator.
4. Icinga DB xem runtime config hiện tại là nguồn sự thật. Host/Service vừa import có thể bị xóa khỏi
   current state nếu cụm mới chưa có monitoring config tương ứng; dữ liệu lịch sử vẫn còn.
5. Với Director, schema `director` mang object/config về nhưng operator vẫn phải kiểm tra Kickstart và
   tự deploy chúng. Director chỉ chạy trên `ca_host`.

Regression thật ngày 2026-10-23 đã dựng cụm mới 2 master + 3 Galera, giữ system DB đích, import đúng
ba schema ứng dụng, phục hồi environment ID và chạy full `check` với `failed=0`. Chi tiết và checksum
nằm ở mục 14.8 và 19.4 của `OPERATIONS-RUNBOOK-VI.md`.

### 7.6. Kiểm tra sau restore

Tối thiểu phải xác nhận:

- `check` kết thúc `failed=0` trên hai master và ba Galera;
- `icinga2 daemon -C` hợp lệ trên mọi master/satellite;
- CA fingerprint sau restore khớp bản cũ nếu đã chọn giữ PKI;
- mọi master dùng cùng Icinga DB environment ID và lịch sử cũ đọc được trên Web;
- Galera ở trạng thái `Primary`, `wsrep_ready=ON`, cluster size đúng inventory;
- `sha256sum --strict -c manifest-<timestamp>.sha256` vẫn PASS;
- pipeline monitoring riêng đã phục hồi đủ Host/Service/CheckCommand cần thiết.

Các lệnh đối chiếu trực tiếp:

```bash
# Parse config trên mọi master/satellite.
ansible -i "$INV" icinga -b -a 'docker exec icinga2 icinga2 daemon -C'

# Hai master phải in cùng environment ID JSON.
ansible -i "$INV" master -b \
  -a 'cat /var/lib/icinga-ansible/icinga2/data/var/lib/icinga2/icingadb.env'

# Nếu giữ PKI, hai fingerprint dưới đây phải giống nhau.
CA_IP=10.0.0.11  # ansible_host của master[0]
tar -xOzf "$BACKUP_ROOT/pki/pki-$BACKUP_TS.tar.gz" \
  --wildcards '*/ca.crt' | openssl x509 -noout -fingerprint -sha256
ssh ubuntu@"$CA_IP" \
  'sudo openssl x509 -in /var/lib/icinga-ansible/icinga2/data/var/lib/icinga2/ca/ca.crt -noout -fingerprint -sha256'
```

Chỉ xóa hạ tầng cũ hoặc backup generation cũ sau khi toàn bộ checklist PASS và đã tạo một
`backup-full` baseline mới từ cluster vừa phục hồi.

### 7.7. Destroy rồi deploy lại cùng cluster

Nếu chỉ cần xóa runtime nhưng vẫn giữ deployment node, config và inventory hiện tại:

```bash
./tools/icinga-ansible destroy -i ansible/inventory/my-cluster \
  -e confirm=yes-i-really-really-mean-it
```

`destroy` xoá container, data và config runtime trên managed node. `globals.yml` và
`passwords.yml` trên deployment node được giữ để có thể deploy lại cùng identity/secrets. Docker,
chrony và network nền được giữ. Sau `destroy`, chạy `deploy` trực tiếp; chỉ chạy
`bootstrap-servers` nếu service node là máy mới.

## 8. Tiêu chí kiểm tra sau thay đổi

```bash
./tools/validate
./tools/icinga-ansible prechecks   -i ansible/inventory/my-cluster
./tools/icinga-ansible reconfigure -i ansible/inventory/my-cluster
./tools/icinga-ansible check       -i ansible/inventory/my-cluster
```

Kết quả mong đợi:

- `icinga2 daemon -C` hợp lệ trên mọi endpoint;
- hai master kết nối trong đúng master zone;
- Redis/Icinga DB/Web healthy;
- heartbeat/config sync của Icinga DB mới;
- Galera `Primary`, `wsrep_ready=ON`, cluster size đúng inventory;
- không có Host/Service do role tự tạo khi thư mục operator đang rỗng.

## 9. Nâng cấp

Sửa tag trong `icinga_image_versions`, sau đó:

```bash
./tools/icinga-ansible upgrade-plan -i ansible/inventory/my-cluster
./tools/icinga-ansible upgrade      -i ansible/inventory/my-cluster
./tools/icinga-ansible check        -i ansible/inventory/my-cluster
```

Không dùng `deploy` để vượt major/schema migration. `upgrade` tạo backup trước thay đổi; external DB
vẫn cần kế hoạch backup/migration của DBA.
