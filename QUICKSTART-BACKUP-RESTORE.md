# Quickstart: full-cluster backup và restore

Tài liệu này dùng cho `managed_db`. Chạy bằng user thường có `sudo`, từ đúng revision code ghi trong
`cluster-<timestamp>.json`, sau khi đã activate Ansible virtualenv.

## 1. Tạo full backup

```bash
cd /opt/icinga-ansible
source /path/to/venv/bin/activate
INV=ansible/inventory/my-cluster

./tools/icinga-ansible check       -i "$INV"
./tools/icinga-ansible backup-full -i "$INV"

BACKUP_ROOT=/var/backups/icinga-ansible-config
BACKUP_TS="$(cat "$BACKUP_ROOT/LATEST_COMPLETE")"
cd "$BACKUP_ROOT"
sha256sum --strict -c "manifest-$BACKUP_TS.sha256"
```

Một generation hoàn chỉnh có:

- `config-*`: `globals.yml`, `passwords.yml` và override trên máy điều khiển;
- `inventory-*` và `cluster-*`: inventory, logical topology, IP lúc backup và image version;
- `nodes/icinga2-<node>-*`: config/cert/identity của mọi master, satellite và client, gồm
  `zones.d`, `secrets`, custom plugin và `icingadb.env` trên master;
- `pki/pki-*`: CA certificate và private key;
- `icingaweb2-<master>-*`: toàn bộ INI Web của từng master;
- `database/db-full-*`: physical backup của MariaDB/Galera;
- `manifest-*` và `LATEST_COMPLETE`: checksum và generation đã được công bố.

Copy **nguyên cây** `$BACKUP_ROOT` ra storage độc lập. Không chỉ copy file DB và không dùng generation
không có trong `LATEST_COMPLETE`.

```bash
rsync -a "$BACKUP_ROOT/" backup-host:/srv/backup/icinga/prod/
```

## 2. Biến dùng chung khi restore

```bash
cd /opt/icinga-ansible
source /path/to/venv/bin/activate
BACKUP_ROOT=/var/backups/icinga-ansible-config
BACKUP_TS="$(cat "$BACKUP_ROOT/LATEST_COMPLETE")"

cd "$BACKUP_ROOT"
sha256sum --strict -c "manifest-$BACKUP_TS.sha256"
cd /opt/icinga-ansible
```

Không upgrade image trong lúc DR. Restore bằng version trong `cluster-$BACKUP_TS.json`, xác minh xong
mới chạy quy trình upgrade riêng.

## 3. Trường hợp 1: restore lên hệ thống hiện tại

`restore_mode=existing` chỉ chạy nếu CA đang hoạt động giống CA trong bundle. Tool lưu một bản
node-state trước khi ghi đè tại `/var/backups/icinga-ansible-pre-restore/` trên từng endpoint.

```bash
INV=ansible/inventory/my-cluster

CONFIRM=yes-i-really-really-mean-it ./tools/icinga-ansible restore-config \
  --config-backup "$BACKUP_ROOT/config-$BACKUP_TS.tar.gz"

./tools/icinga-ansible restore-node-state -i "$INV" \
  -e restore_mode=existing -e restore_backup_ts="$BACKUP_TS" \
  -e confirm=yes-i-really-really-mean-it

./tools/icinga-ansible mariadb-recovery -i "$INV" \
  -e recovery_mode=restore-backup -e restore_backup_tag=full \
  -e restore_backup_ts="$BACKUP_TS" -e confirm=yes

./tools/icinga-ansible recover-db-only -i "$INV" -e confirm=yes
./tools/icinga-ansible restore-web -i "$INV" \
  -e restore_backup_ts="$BACKUP_TS" -e confirm=yes
./tools/icinga-ansible deploy -i "$INV"
./tools/icinga-ansible check  -i "$INV"
```

## 4. Trường hợp 2: VM sạch, cùng IP và topology

Trước tiên tắt/xóa hoàn toàn VM cũ và giải phóng port giữ fixed IP. Không để hai VM dùng cùng IP.
Xóa SSH host key cũ rồi giải inventory từ bundle:

```bash
mkdir -p restore-inventory
tar -xzf "$BACKUP_ROOT/inventory-$BACKUP_TS.tar.gz" -C restore-inventory
INV=restore-inventory/my-cluster       # thay bằng tên file vừa giải nén

for ip in 10.0.0.11 10.0.0.12 10.0.0.21 10.0.0.22 10.0.0.23; do
  ssh-keygen -f ~/.ssh/known_hosts -R "$ip"
done

CONFIRM=yes-i-really-really-mean-it ./tools/icinga-ansible restore-config \
  --config-backup "$BACKUP_ROOT/config-$BACKUP_TS.tar.gz"

./tools/icinga-ansible bootstrap-servers -i "$INV"
./tools/icinga-ansible restore-node-state -i "$INV" \
  -e restore_mode=clean -e restore_backup_ts="$BACKUP_TS" \
  -e confirm=yes-i-really-really-mean-it
./tools/icinga-ansible pull   -i "$INV"
./tools/icinga-ansible deploy -i "$INV"
```

Sau deploy tạm, restore dữ liệu và hội tụ lần cuối:

```bash
./tools/icinga-ansible mariadb-recovery -i "$INV" \
  -e recovery_mode=restore-backup -e restore_backup_tag=full \
  -e restore_backup_ts="$BACKUP_TS" -e confirm=yes
./tools/icinga-ansible recover-db-only -i "$INV" -e confirm=yes
./tools/icinga-ansible restore-web -i "$INV" \
  -e restore_backup_ts="$BACKUP_TS" -e confirm=yes
./tools/icinga-ansible deploy -i "$INV"
./tools/icinga-ansible check  -i "$INV"
```

## 5. Trường hợp 3: VM sạch, IP mới nhưng cùng topology

Làm giống trường hợp 2, nhưng trước `bootstrap-servers` sửa **chỉ** `ansible_host` trong bản inventory
đã giải nén. Giữ nguyên inventory hostname (`master1`, `master2`...), thứ tự và membership các nhóm
`master`, `satellite`, `client`, `galera`, `icinga_master_zone_name` và `icinga_database_type`.

```bash
cp restore-inventory/my-cluster restore-inventory/my-cluster-new-ip
INV=restore-inventory/my-cluster-new-ip
$EDITOR "$INV"                         # chỉ đổi ansible_host
ansible-inventory -i "$INV" --graph
ansible -i "$INV" all_hosts -m ping
```

Sau đó chạy nguyên chuỗi của trường hợp 2 từ `restore-config`. `restore-node-state` kiểm tra logical
topology nhưng cho phép IP đổi; lần `deploy` đầu sẽ render lại `zones.conf` bằng IP trong inventory mới.

## 6. Xác minh bắt buộc

`check` phải có `failed=0` trên mọi node. Đối chiếu thêm:

```bash
cd "$BACKUP_ROOT"
sha256sum --strict -c "manifest-$BACKUP_TS.sha256"

ansible -i "$INV" master -b \
  -a 'cat /var/lib/icinga-ansible/icinga2/data/var/lib/icinga2/icingadb.env'
ansible -i "$INV" icinga -b -a 'docker exec icinga2 icinga2 daemon -C'
```

Hai master phải có cùng environment ID; Galera phải `Primary`, `Synced`, `wsrep_ready=ON` và đủ số
node. Director chỉ tồn tại trên `master[0]`. Web login, Icinga API và Icinga DB heartbeat/config sync
đều được `check` kiểm tra thật.

Với `external_db`, bundle không chứa database: DBA phải backup/restore DB ngoài và xác minh schema/user/
grant riêng. Không chạy `mariadb-recovery` cho external DB.
