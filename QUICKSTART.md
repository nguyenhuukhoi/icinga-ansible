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

- `network_interface`;
- `icinga_image_versions`;
- `icinga_master_zone_name` (chỉ đổi trước deploy đầu tiên);
- `icinga_database_type` và `managed_db`/`external_db`;
- `enable_icingaweb2_modules`;
- proxy/registry CA nếu môi trường yêu cầu.

Có thể mã hoá secret bằng `ansible-vault encrypt /etc/icinga-ansible/passwords.yml` và truyền
tuỳ chọn Vault qua CLI.

## 3. Tạo inventory

Copy một file trong `ansible/inventory/` rồi sửa. Mỗi host có vai trò triển khai phải thuộc
`all_hosts`. Hai master và ba Galera độc lập có dạng:

```ini
[all_hosts]
master1 ansible_host=10.0.0.11 ansible_user=ubuntu
master2 ansible_host=10.0.0.12 ansible_user=ubuntu
galera1 ansible_host=10.0.0.21 ansible_user=ubuntu
galera2 ansible_host=10.0.0.22 ansible_user=ubuntu
galera3 ansible_host=10.0.0.23 ansible_user=ubuntu

[master]
master1
master2

[satellite]

[client]

[galera]
galera1
galera2
galera3

[loadbalancer]

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
| Icinga Web 2/Director | `/etc/icinga-ansible/icingaweb2/` | `/data/etc/icingaweb2/` |
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

Ansible không sinh và không vận chuyển object monitoring. Chọn Director hoặc một quy trình static
DSL hoàn toàn độc lập với project.

### Director

Bật `director` trong `enable_icingaweb2_modules`. Ansible chỉ tạo DB, migrate schema và enable
module. Operator tự chạy Kickstart trong UI rồi tự tạo Host/Service/CheckCommand; Ansible không
import hoặc reconcile object Director.

### Static DSL

Static DSL nằm ngoài phạm vi của project. Ansible không đọc, validate, copy, mount hoặc xoá file
trong `zones.d`. Đặc biệt, `/etc/icinga-ansible/config/icinga2/zones.d` trên deployment node không
còn là nguồn cấu hình và nội dung đặt tại đó sẽ bị bỏ qua. Operator phải dùng quy trình triển khai
riêng nếu không dùng Director.

Script riêng đặt trong `custom-plugins`; credential dùng chung cho mọi Icinga node đặt trong `secret/`,
còn `/etc/icinga-ansible/config/icinga2/secrets/` chỉ được chuyển tới master. Credential theo role/host
đặt dưới tầng `secret/` tương ứng. Những thư mục này chỉ là kênh vận chuyển an toàn, không phải object
generator.

### Monitor Nova/Cinder/Neutron bằng static file, thực thi HA từ hai master

Luồng này không dùng Director. Deployment node không đọc hoặc đồng bộ `zones.d`; operator đặt object trên
`master1` và để cơ chế config-sync gốc của Icinga chuyển sang `master2`. Đặt credential OpenStack trên
deployment node:

```bash
install -d -m 0700 /etc/icinga-ansible/config/icinga2/secrets
install -m 0600 ~/.config/openstack/clouds.yaml \
  /etc/icinga-ansible/config/icinga2/secrets/clouds.yaml
install -d -m 0750 /etc/icinga-ansible/config/icinga2/custom-plugins
install -m 0755 examples/openstack-file-monitoring/check_openstack_service.py \
  /etc/icinga-ansible/config/icinga2/custom-plugins/check_openstack_service.py
```

Role trộn secret và đưa `clouds.yaml` vào cả hai container master tại
`/etc/icinga-ansible/icinga2/clouds.yaml`. Plugin gọi API qua endpoint trong `clouds.yaml`; vì vậy khi
một controller hỏng, check vẫn chạy nếu OpenStack API/VIP còn hoạt động. Từ deployment node, thực hiện
một lần các lệnh operator sau để đặt file vào đúng zone trên `master1` (không copy lên master2 và không
được `reconfigure` quản lý lại):

```bash
INV=ansible/inventory/my-cluster
ZONE=csoc-monitoring  # phải bằng icinga_master_zone_name/ZoneName của cụm
ansible -i "$INV" master1 -b -m file \
  -a "path=/etc/icinga-ansible/icinga2/zones.d/$ZONE state=directory owner=5665 group=5665 mode=0750"
ansible -i "$INV" master1 -b -m copy \
  -a "src=examples/openstack-file-monitoring/openstack-nodes.conf dest=/etc/icinga-ansible/icinga2/zones.d/$ZONE/openstack-nodes.conf owner=5665 group=5665 mode=0640"
ansible -i "$INV" master1 -b -m copy \
  -a "src=examples/openstack-file-monitoring/openstack-services.conf dest=/etc/icinga-ansible/icinga2/zones.d/$ZONE/openstack-services.conf owner=5665 group=5665 mode=0640"
ansible -i "$INV" master1 -b -m command -a 'docker exec icinga2 icinga2 daemon -C'
ansible -i "$INV" master1 -b -m command -a 'docker kill --signal=HUP icinga2'
```

Icinga đồng bộ nội dung zone sang master peer; hai endpoint trong cùng `ZoneName` phối hợp HA và tự chọn
endpoint thực thi. Không đặt `command_endpoint` trỏ tới controller. File nguồn trên deployment node dưới
`config/icinga2/zones.d` vẫn bị bỏ qua; đây là chủ ý để tool không ghi đè monitoring DSL.

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
master thứ ba. Tên logic của node, ví dụ `master2`, phải ổn định dù IP có thể thay đổi.

1. Tạo VM mới và xác nhận deployment node SSH/sudo được vào VM.
2. Thêm node vào cả `[all_hosts]` và `[master]`. Giữ master đang làm CA ở dòng đầu tiên.
3. Chỉ bootstrap host mới bằng `--limit`.
4. Chạy `prechecks` và `add-master` với **inventory đầy đủ**, không dùng `--limit`. Các endpoint cũ
   cũng cần được render lại `zones.conf`.
5. Chạy `check` trên toàn cụm.

Ví dụ inventory sau khi sửa:

```ini
[all_hosts]
master1 ansible_host=10.0.0.11 ansible_user=ubuntu
master2 ansible_host=10.0.0.12 ansible_user=ubuntu

[master]
master1
master2
```

Thực hiện:

```bash
ansible -i "$INV" master2 -m ping
./tools/icinga-ansible bootstrap-servers -i "$INV" --limit master2
./tools/icinga-ansible prechecks         -i "$INV"
./tools/icinga-ansible add-master        -i "$INV"
./tools/icinga-ansible check             -i "$INV"
```

Không dùng `add-master --limit master2`: node mới có thể lên nhưng master/satellite cũ vẫn giữ
topology cũ.

### 6.2. Thêm một hoặc hai satellite

Mỗi satellite phải có trong `[all_hosts]`, `[satellite]` và xuất hiện đúng một lần trong
`satellite_zones` tại `/etc/icinga-ansible/globals.yml`. Mỗi zone có một hoặc hai member.

Ví dụ thêm hai node HA trong cùng zone:

```ini
[all_hosts]
satellite1 ansible_host=10.0.0.31 ansible_user=ubuntu
satellite2 ansible_host=10.0.0.32 ansible_user=ubuntu

[satellite]
satellite1
satellite2
```

```yaml
satellite_zones:
  - name: "openstack-zone"
    members: ["satellite1", "satellite2"]
    parent: "master"
```

Thực hiện:

```bash
ansible -i "$INV" 'satellite1:satellite2' -m ping
./tools/icinga-ansible bootstrap-servers -i "$INV" --limit 'satellite1,satellite2'
./tools/icinga-ansible prechecks         -i "$INV"
./tools/icinga-ansible add-node          -i "$INV"
./tools/icinga-ansible check             -i "$INV"
```

`add-node` phải dùng inventory đầy đủ. Role chỉ tạo thư mục `conf.d/operator` rỗng trên node mới;
nội dung monitoring phải được operator triển khai bằng pipeline riêng sau khi hạ tầng đã PASS.

### 6.3. Xoá satellite

Thứ tự là bắt buộc: **remove khi target vẫn còn trong inventory**, sau đó mới sửa inventory và
`satellite_zones`. Lệnh `remove-node` phá huỷ container, dữ liệu và config Icinga 2 trên đúng target;
nó không xóa VM.

```bash
# 1. Target vẫn phải còn trong [all_hosts] và [satellite].
./tools/icinga-ansible remove-node -i "$INV" \
  -e target_host=satellite2 -e confirm=yes

# 2. Chỉ sau khi lệnh trên thành công:
#    - xóa satellite2 khỏi [satellite] và [all_hosts];
#    - xóa satellite2 khỏi satellite_zones[].members;
#    - nếu zone hết member, xóa cả zone.
$EDITOR "$INV"
$EDITOR /etc/icinga-ansible/globals.yml

# 3. Hội tụ toàn bộ endpoint còn lại. Không dùng --limit.
./tools/icinga-ansible prechecks   -i "$INV"
./tools/icinga-ansible reconfigure -i "$INV" -t icinga2
./tools/icinga-ansible check       -i "$INV"
```

Chỉ xóa VM sau khi `check` PASS. Xóa satellite cuối cùng của một zone không ảnh hưởng database hoặc
Web, nhưng object monitoring do operator tự quản lý có thể còn tham chiếu `command_endpoint`; hãy
kiểm tra và sửa phần đó trong pipeline monitoring riêng.

### 6.4. Xoá master

Không được xóa master cuối cùng. `master[0]` là `ca_host`, vì vậy playbook chặn xóa trực tiếp node
này. Quy trình thông thường chỉ xóa master thứ hai:

```bash
# 1. master2 vẫn còn trong inventory.
./tools/icinga-ansible remove-master -i "$INV" \
  -e target_host=master2 -e confirm=yes

# 2. Sau khi thành công, xóa master2 khỏi [master] và [all_hosts].
$EDITOR "$INV"

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

### 7.1. Tạo và xác minh full backup

```bash
INV=ansible/inventory/my-cluster
./tools/icinga-ansible check       -i "$INV"
./tools/icinga-ansible backup-full -i "$INV"
```

Mặc định bundle nằm tại `/var/backups/icinga-ansible-config` trên deployment node:

```text
config-<timestamp>.tar.gz
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

Copy **cả cây thư mục**, không chỉ file DB, sang storage ngoài deployment node. Inventory thường nằm
trong repo nên không thuộc `config-*.tar.gz`; phải lưu inventory/host vars cùng phiên bản code ở SCM
hoặc backup riêng. Với external DB, DBA phải backup/restore database bằng quy trình riêng.

`backup-full` không backup object monitoring do operator đặt trực tiếp trong
`conf.d/operator`, package triển khai static hoặc credential nằm ngoài `/etc/icinga-ansible`. Hãy lưu
những phần đó trong Git/vault/storage riêng. Project không backup và không restore `zones.d`.

Ví dụ copy off-site không xóa generation cũ ở đích:

```bash
rsync -a "$BACKUP_ROOT/" backup-host:/srv/backup/icinga/prod/
rsync -a "$INV" backup-host:/srv/backup/icinga/prod/inventory/
```

### 7.2. Dựng lại cụm mới từ full backup

Quy trình dưới đây áp dụng khi mất toàn bộ service node và dựng lại topology 2 master + 3 Galera
trên VM/IP mới. Dùng đúng version code và MariaDB đã tạo backup; chỉ upgrade sau khi restore PASS.

Trước khi bắt đầu, đưa nguyên cây backup từ storage ngoài về đúng layout, clone đúng revision code,
tạo venv và cài collection. Đặt inventory đã backup thành `ansible/inventory/restore-cluster` rồi sửa
`ansible_host` sang IP mới. Nên giữ nguyên tên logic `master1`, `master2`, `galera1`... để archive Web
và identity endpoint ánh xạ đúng.

```bash
cd /opt/icinga-ansible
source /path/to/venv/bin/activate
INV=ansible/inventory/restore-cluster
BACKUP_ROOT=/var/backups/icinga-ansible-config
BACKUP_TS="$(cat "$BACKUP_ROOT/LATEST_COMPLETE")"

cd "$BACKUP_ROOT"
sha256sum --strict -c "manifest-$BACKUP_TS.sha256"
cd /opt/icinga-ansible
```

Khôi phục desired state trên deployment node. Nếu `/etc/icinga-ansible` đang có dữ liệu, bắt buộc
dùng đúng biến môi trường `CONFIRM`; đây không phải Ansible extra-var `-e confirm=...`:

```bash
CONFIRM=yes-i-really-mean-it ./tools/icinga-ansible restore-config \
  --config-backup "$BACKUP_ROOT/config-$BACKUP_TS.tar.gz"
```

Sau `restore-config`, kiểm tra lại `/etc/icinga-ansible/globals.yml`. Nếu topology mới không có các
satellite cũ, xóa chúng khỏi `satellite_zones`; nếu thêm satellite mới, khai mỗi node đúng một zone
trước khi chạy precheck. Không chạy `init-config` hoặc `genpwd`, vì làm vậy sẽ đổi secret cũ.

```bash
$EDITOR "$INV"
$EDITOR /etc/icinga-ansible/globals.yml
ansible-inventory -i "$INV" --graph
ansible -i "$INV" all_hosts -m ping
```

Bootstrap toàn bộ host mới:

```bash
./tools/icinga-ansible bootstrap-servers -i "$INV"
./tools/icinga-ansible prechecks         -i "$INV"
```

Để giữ trust chain cũ, copy archive PKI lên đúng `master[0]` rồi restore **trước deploy đầu tiên**.
Ví dụ CA host là `master1`:

```bash
CA_IP=10.0.0.11  # thay bằng ansible_host mới của master1
scp "$BACKUP_ROOT/pki/pki-$BACKUP_TS.tar.gz" ubuntu@"$CA_IP":/home/ubuntu/
./tools/icinga-ansible restore-pki -i "$INV" \
  -e pki_backup="/home/ubuntu/pki-$BACKUP_TS.tar.gz" -e confirm=yes
```

Nếu chủ động dùng CA mới, bỏ qua đúng bước `restore-pki`; mọi agent/client cũ sẽ phải enroll lại.
`restore-pki` sẽ từ chối chạy nếu CA host đã được deploy hoặc đã có một phần CA state.

Dựng runtime tạm, restore physical database, khôi phục environment ID rồi restore Web:

```bash
./tools/icinga-ansible pull   -i "$INV"
./tools/icinga-ansible deploy -i "$INV"

./tools/icinga-ansible mariadb-recovery -i "$INV" \
  -e recovery_mode=restore-backup \
  -e restore_backup_ts="$BACKUP_TS" \
  -e confirm=yes

./tools/icinga-ansible recover-db-only -i "$INV" -e confirm=yes

./tools/icinga-ansible restore-web -i "$INV" \
  -e restore_backup_ts="$BACKUP_TS" -e confirm=yes

./tools/icinga-ansible deploy -i "$INV"
./tools/icinga-ansible check  -i "$INV"
```

`restore-web` yêu cầu tên các master mới khớp tên master trong bundle. Nếu đổi tên hoặc thêm master
so với thời điểm backup, không đổi tên archive để ép restore; hãy bỏ qua bước này, dựng Web config
mới rồi chuyển thủ công phần cần giữ sau khi review.

Cuối cùng, triển khai lại `conf.d/operator`, plugin/credential và object monitoring bằng pipeline
riêng của operator, validate `icinga2 daemon -C`, reload Icinga 2 rồi chạy `check` lại. Không chép
monitoring config qua `zones.d` và không trông chờ `deploy` đồng bộ nội dung operator.

### 7.3. Kiểm tra sau restore

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
  -a 'cat /var/lib/icinga-ansible/icinga2/icingadb.env'

# Nếu giữ PKI, hai fingerprint dưới đây phải giống nhau.
tar -xOzf "$BACKUP_ROOT/pki/pki-$BACKUP_TS.tar.gz" \
  --wildcards '*/ca.crt' | openssl x509 -noout -fingerprint -sha256
ssh ubuntu@"$CA_IP" \
  'sudo openssl x509 -in /var/lib/icinga-ansible/icinga2/data/var/lib/icinga2/ca/ca.crt -noout -fingerprint -sha256'
```

Chỉ xóa hạ tầng cũ hoặc backup generation cũ sau khi toàn bộ checklist PASS và đã tạo một
`backup-full` baseline mới từ cluster vừa phục hồi.

### 7.4. Destroy rồi deploy lại cùng cluster

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
