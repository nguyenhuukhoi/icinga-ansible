# icinga-ansible

Deploy & operate stack Icinga (Icinga 2 + Icinga DB + Icinga Web 2 + MariaDB) bằng
Ansible + Docker, phong cách kolla-ansible. Thiết kế đầy đủ: [`design.md`](design.md).

> 🆕 **Mới bắt đầu?** Đọc [`QUICKSTART.md`](QUICKSTART.md) — hướng dẫn từng bước, đầy đủ và dễ tiếp
> cận hơn README này (giải thích khái niệm, sự cố thường gặp, ví dụ chạy thật).

> Checklist go-live và regression mới nhất: [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md).

> **Trạng thái: P1, P2 (HA N-master, KHÔNG VIP), P3 (satellite), Galera cluster thật (≥3 node), kiến
> trúc config kiểu kolla-ansible (`/etc/icinga-ansible/<svc>` trên từng node + override) — ĐÃ VERIFY
> chạy thật**, bao gồm cả `add-master`/`remove-master`/`add-node`/`remove-node` (P5), trên host thật
> (Ubuntu 24.04). P1: all-in-one, destroy→deploy sạch, login+dashboard OK. P2/P3: verify trên 7 host
> thật — **2 master + 2 satellite + 3 node Galera cluster thật** (`wsrep_cluster_size=3`, `Primary`,
> `wsrep_ready=ON`) — cluster zone HA thật sự kết nối (xác nhận qua Icinga2 API, không chỉ log),
> icingadb leader election, CA HA. Đã test full round-trip: xoá + thêm lại 1 master và 1 satellite
> đang chạy, cluster phục hồi hoàn toàn cả 2 lần. Kiến trúc config: mount per-file (không mount cả
> thư mục — tránh phá `zones.d`/`enabledModules` do runtime tự ghi), override thật đã test 2 chiều
> (đặt override → ăn đúng host → xoá override → tự revert template). **Client (command endpoint)** —
> tính năng mới ngoài roadmap gốc — cũng đã verify: Host/Service thật (check `ssh`) chạy qua command
> endpoint, `state: 0` (OK) thật. Chi tiết + bug đã gặp/đã fix: xem [`TODO.md`](TODO.md).
>
> **P4 (DB backup/recovery):** backup có nhãn + `mariadb-recovery restore-backup` ĐÃ VERIFY thật;
> trường hợp chỉ còn DB backup có thêm `recover-db-only` để phục hồi Icinga DB environment ID lên
> mọi master và xoá Redis state tạm. Identity/Redis recovery smoke drill trên cụm 2 master + 3
> Galera đã PASS; full drill mất trắng filesystem hai master vẫn còn cần chạy.
> `recover-cluster` (cứu cụm chết) đã code, smoke-test còn dở. **Version model ĐỔI (2026-07-22):** bỏ
> `version-matrix.yml`, khai thẳng `icinga_image_versions` trong `globals.yml`. **P5 (upgrade/rollback):**
> ĐÃ verify end-to-end trên standalone và Galera 3 node đến ngày 2026-09-06: backup pre-upgrade,
> failure drill 11.8.9→12.0.2 dừng đúng và rollback giữ nguyên data; sau đó rolling LTS chính thức
> **11.8.9→12.3.3 thành công đủ ba node**, replication/deep check PASS. Đổi MariaDB series bị chặn
> mặc định và Galera provider không được downgrade; path đã review cần opt-in tường minh. Load balancer (VIP web) chưa triển khai và role
> sẽ fail cứng; xem ranh giới hỗ trợ trong [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md).
>
> 👉 **Người làm tiếp đọc [`TODO.md`](TODO.md)** — trạng thái, bug đã fix (bài học), roadmap P4–P6.

## Thành phần (mục tiêu Icinga DB — KHÔNG dùng IDO/PDO)
`icinga2` · `icingadb` (daemon) · `icingadb-redis` · `icingaweb2` (Apache2) · `mariadb`

## Cấu trúc
```
ansible/          playbook, inventory, group_vars, roles/, playbooks/ (destroy, upgrade, rollback, mariadb-recovery...)
etc/examples/     TEMPLATE mặc định (globals.yml, passwords.yml.example) — KHÔNG sửa trực tiếp
tools/icinga-ansible  CLI wrapper
```

**Repo và config KHÔNG chung chỗ — giống kolla-ansible (`/etc/kolla`).** Repo (code) có thể clone/
move ở bất cứ đâu, không ảnh hưởng gì. Config **thật** (`globals.yml`, `passwords.yml`) luôn nằm ở
đường dẫn OS cố định **`/etc/icinga-ansible/`**, tách biệt hoàn toàn với repo — sống sót qua mọi lần
di chuyển/deploy lại code. Override đường dẫn này bằng biến môi trường `ICINGA_ANSIBLE_CONFIG_DIR`
nếu cần (vd nhiều bộ config trên cùng máy).

## Quickstart (all-in-one, đã verify trên Ubuntu 24.04/26.04)

Clone/copy repo lên node cần deploy (đường dẫn tuỳ ý, ví dụ `/opt/icinga-ansible`), rồi:

```bash
cd /opt/icinga-ansible

# 1. Tạo môi trường Ansible riêng cho project
sudo apt update
sudo apt install -y git python3 python3-venv
./tools/setup-venv                 # cài ansible-core + collection vào repo
source .venv/bin/activate          # khuyến nghị; wrapper vẫn tự tìm .venv nếu không activate

# 2. Khởi tạo /etc/icinga-ansible từ template + sinh secrets ngẫu nhiên
./tools/icinga-ansible init-config      # tạo /etc/icinga-ansible (cần sudo, chỉ 1 lần)
./tools/icinga-ansible genpwd           # sinh /etc/icinga-ansible/passwords.yml
#   Muốn đặt tay 1 giá trị cụ thể (vd mật khẩu admin web), sửa trực tiếp
#   /etc/icinga-ansible/passwords.yml sau khi genpwd — không cần chạy lại genpwd.
#   (tuỳ chọn) ansible-vault encrypt /etc/icinga-ansible/passwords.yml

# 3. Chỉnh cấu hình (mặc định đã chạy được ngay, không bắt buộc sửa)
$EDITOR /etc/icinga-ansible/globals.yml       # icinga_image_versions (tag image), module, DB...

# 4. Bootstrap host (Docker Engine, chrony) — bỏ qua nếu host đã có sẵn
./tools/icinga-ansible bootstrap-servers -i ansible/inventory/all-in-one

# 5. Kiểm tra tiền deploy + triển khai
./tools/icinga-ansible prechecks -i ansible/inventory/all-in-one
./tools/icinga-ansible deploy    -i ansible/inventory/all-in-one

# 6. Thông tin truy cập
./tools/icinga-ansible post-deploy -i ansible/inventory/all-in-one
```

Không cài `ansible` bằng `apt` cho control node. Project khóa phiên bản trong `requirements.txt`,
collection nằm ở `ansible/.collections`, và wrapper từ chối fallback sang Ansible hệ thống để tránh
hai deployment node chạy hai phiên bản khác nhau. Xoá `.venv` rồi chạy lại `./tools/setup-venv` nếu
cần dựng sạch môi trường công cụ; việc này không đụng tới `/etc/icinga-ansible` hay cluster.

Web: `http://<host>:8080/authentication/login` (Apache lắng nghe port **8080** trên host,
không phải 80 — xem `icingaweb2_http_port` trong `globals.yml`).
User: `admin` (biến `icingaweb2_admin_user`), mật khẩu: `icingaweb2_admin_password` trong `passwords.yml`.

### Làm lại từ đầu (destroy)
```bash
./tools/icinga-ansible destroy -i ansible/inventory/all-in-one -e confirm=yes-i-really-really-mean-it
```
Xoá **toàn bộ**: container, dữ liệu (DB, PKI ở `icinga_base_dir`) và cấu hình render trên từng host
(`icinga_etc_dir` = `/etc/icinga-ansible`: mọi override, config từng service) — KHÔNG đụng
Docker/chrony đã cài lẫn docker network (giữ nguyên, giống `kolla-ansible destroy`).
**`globals.yml` + `passwords.yml` trên deployment node (control node) được GIỮ LẠI** — theo thiết kế
(2026-07-23), vì đây là secrets/định danh cụm (mật khẩu DB, API user, admin web...); mất đi thì
`deploy` lại sẽ tạo mật khẩu MỚI hoàn toàn, không "y hệt cụm cũ" được nữa dù đã mất data theo destroy
rồi. Nhờ vậy sau `destroy`, chạy `deploy` **thẳng luôn** là được — không cần `init-config`/`genpwd`
lại. Muốn xoá cả 2 file này thì tự tay `rm /etc/icinga-ansible/{globals.yml,passwords.yml}` sau khi
destroy.
Playbook có **2 play**: play 1 xoá dữ liệu+cấu hình trên từng host trong inventory; play 2 xoá riêng
phần còn lại của `/etc/icinga-ansible` **trên chính máy chạy CLI** (`hosts: localhost`) — cần thiết
vì control node **không nhất thiết** là 1 host trong inventory (vd chạy CLI từ máy vận hành/CI, SSH
ra các node, không phải setup kiểu lab `ansible_connection=local` trùng với master). Nếu control
node trùng với 1 host trong inventory thì play 2 chỉ xoá lại đúng chỗ play 1 đã xoá — vô hại.
Cụm xác nhận `-e confirm=yes-i-really-really-mean-it` phải gõ **đúng nguyên văn** (giống
`kolla-ansible destroy --yes-i-really-really-mean-it`) — thiếu hoặc gõ khác đi thì playbook tự chặn,
không xoá gì (cố ý khó gõ nhầm/copy-paste nhầm cho 1 lệnh không hồi phục được).
Vẫn **không cần** `bootstrap-servers` lại (Docker/chrony/thư mục base/network giữ nguyên).

### Đổi mật khẩu admin web sau khi đã deploy
Sửa `icingaweb2_admin_password` trong `/etc/icinga-ansible/passwords.yml` rồi chạy `reconfigure` —
task tạo/update admin sẽ tự hash lại và ghi đè (không cần destroy):
```bash
./tools/icinga-ansible reconfigure -i ansible/inventory/all-in-one
```

## Chọn version
Khai THẲNG tag từng thành phần trong `/etc/icinga-ansible/globals.yml` → `icinga_image_versions`
(icinga2/icingadb/icingadb_redis/icingaweb2/mariadb). **KHÔNG còn "bộ phiên bản"/version-matrix.yml** —
Icinga phát hành từng thành phần độc lập, không có bundle chính thức. Dò latest-stable trên Docker Hub
(`hub.docker.com/r/icinga/…/tags`); mariadb/redis là image official. Nâng cấp: sửa tag rồi
`icinga-ansible upgrade` (tự backup pre-upgrade, `rollback` được — xem design.md mục 13).

## Lệnh chính
| Lệnh | Việc |
|---|---|
| `init-config` | Tạo `/etc/icinga-ansible` từ template (chỉ 1 lần, không ghi đè nếu đã có) |
| `genpwd` | Sinh `passwords.yml` với giá trị ngẫu nhiên mạnh |
| `bootstrap-servers` | Cài Docker/chrony, tạo thư mục/mạng — **chỉ cần chạy trên host hoàn toàn mới** (chưa từng cài Docker); `deploy` không tự chạy kèm, nhưng `destroy` cũng không còn xoá thư mục/network nên KHÔNG cần chạy lại sau `destroy` |
| `prechecks` | Kiểm tra topology, version, loại DB và credential external DB |
| `pull` | Chỉ pull/refresh digest image cần thiết, không deploy/recreate container |
| `deploy` | Triển khai toàn bộ (giả định host đã `bootstrap-servers` ít nhất 1 lần) |
| `reconfigure` | Render lại config + reload (cũng dùng để đổi mật khẩu admin) |
| `mariadb-backup` | Backup DB + snapshot CA/PKI |
| `post-deploy` | In thông tin truy cập |
| `check` | Health-check runtime: container, Icinga API/config, Redis, Web, DB heartbeat và Galera |
| `destroy` | Xoá toàn bộ container + dữ liệu + cấu hình render (`/etc/icinga-ansible`, GIỮ LẠI `globals.yml`+`passwords.yml` trên deployment node) (cần `-e confirm=yes-i-really-really-mean-it`, đúng nguyên văn — giống kolla-ansible) — giữ nguyên Docker/chrony/docker network, `deploy` lại thẳng được, không cần `bootstrap-servers`/`init-config`/`genpwd` |
| `add-master` / `add-node` | Thêm master/satellite mới (host đã có trong inventory) — chạy `deploy`; chỉ cần `bootstrap-servers` trước nếu host đó HOÀN TOÀN MỚI (chưa từng cài Docker) |
| `remove-master` / `remove-node` | Xoá master/satellite khỏi cluster (`-e target_host=<host> -e confirm=yes`, cần tự sửa inventory + `reconfigure` sau đó — xem TODO.md) |
| `upgrade-plan` / `upgrade` / `rollback` | Đã có cho `managed_db`; external DB phải theo change/backup plan của DBA |

## Ghi chú kiến trúc quan trọng
- **Repo (code) và config (`/etc/icinga-ansible`) tách biệt** — giống kolla-ansible. Move/xoá/deploy
  lại repo không ảnh hưởng config. `destroy` xoá container, data và config render/override; chỉ giữ
  `globals.yml` + `passwords.yml` trên deployment node để có thể deploy lại cùng định danh/secrets.
- `icinga2` / `mariadb` / `icingadb-redis` / web dùng **Docker host network** (endpoint = IP host).
- **KHÔNG** đặt VIP/LB trước cổng cluster 5665. VIP chỉ cho web 443 (sticky session).
- Session Icinga Web 2 là **PHP file-session** → HA cần sticky ở HAProxy.
- P1 chạy MariaDB **đơn node**; Galera cluster bật ở P2/P4 (config đã cắm sẵn, đang tắt).
- Web Icinga DB (module `icingadb`) đọc config **DB resource** từ `modules/icingadb/config.ini`
  và config **Redis** từ file **riêng** `modules/icingadb/redis.ini` — hai file khác nhau, đừng gộp
  (xem TODO.md, bug đã gặp).
