# Thiết kế icinga-ansible

## 1. Phạm vi

Project quản lý hạ tầng chạy Icinga: node, container, topology, PKI, API, Icinga DB, Redis, Web và
database. Project không sở hữu Host, Service, CheckCommand, apply rule hoặc Notification. Static DSL
hoàn toàn thuộc operator; module FileShipper tuỳ chọn chỉ cho Director vận chuyển nguyên văn file khi
operator chủ động deploy.

## 2. Thành phần

Master chạy Icinga 2, Redis, Icinga DB daemon và Icinga Web 2. Satellite/client chỉ chạy Icinga 2.
`managed_db` chạy MariaDB standalone hoặc Galera số lẻ từ ba node; `external` chỉ kiểm tra kết nối
bằng service account, không dùng quyền DBA.

## 3. Topology và định danh

Inventory là nguồn topology duy nhất. `master[0]` là CA host. Mỗi hostname inventory là tên Endpoint
và phải ổn định. `icinga_master_zone_name` phải được chốt trước deploy đầu. Satellite membership lấy
từ `satellite_zones`; client có zone một endpoint.

## 4. Quyền sở hữu cấu hình

### 4.1. Repo và config runtime

Repo chứa logic. `/etc/icinga-ansible` trên deployment node chứa `globals.yml`, `passwords.yml` và
nguồn override hạ tầng. Node đích nhận config tại `/etc/icinga-ansible`; state ghi được nằm dưới
`/var/lib/icinga-ansible`. Mỗi service mount **nguyên thư mục config** read-write (`rw`), không mount
từng file. Vì vậy UI/daemon tạo file mới hoặc thay file bằng atomic rename vẫn ghi bền vững về host.
Input archive chỉ dùng để restore vẫn giữ read-only theo nguyên tắc tối thiểu quyền.

| Service | Cây config trên host | Đích trong container |
|---|---|---|
| Icinga 2 | `/etc/icinga-ansible/icinga2` | `/data/etc/icinga2` |
| Icinga Web 2 + Director | `/etc/icinga-ansible/icingaweb2` | `/data/etc/icingaweb2` |
| Icinga DB | `/etc/icinga-ansible/icingadb` | `/etc/icingadb` |
| Redis của Icinga DB | `/etc/icinga-ansible/icingadb-redis` | `/usr/local/etc/redis` |
| MariaDB/Galera | `/etc/icinga-ansible/mariadb` | `/etc/mysql/conf.d` |

`/data` hoặc datadir vẫn là mount runtime riêng. Với Icinga 2/Web, mount config lồng bên trong `/data`
cố ý che cây config cũ. Deploy đầu tiên sau nâng cấp chỉ migrate file còn thiếu từ cây cũ, không ghi
đè file đã có dưới `/etc/icinga-ansible`.

Role không render hoặc reconcile `zones.d`. Luồng direct-to-core do operator tự phân phối; FileShipper
chỉ thêm file vào package Director khi operator chủ động deploy. Thư mục có mặt trong container vì
toàn bộ cây config host được bind-mount RW. Trước khi thay đổi runtime, role chạy `icinga2 daemon -C` trên config
hiệu lực, nên lỗi cú pháp operator vẫn dừng deploy an toàn. Migration layout cũ chỉ copy cục bộ một
lần trên chính node để tránh mất dữ liệu. `remove-*`/`destroy` xóa nguyên config của target được chỉ
định; nội dung operator phải có backup/pipeline riêng.

## 5. Network

Service dùng Docker host network. Port cluster/API 5665 nối trực tiếp theo endpoint; không đặt VIP ở
đây. Web mặc định dùng HTTP 8080. Khi bật HTTPS, Apache trong container bind cổng TLS (mặc định 443),
nạp certificate/key theo permission root và có thể redirect 8080 sang HTTPS. Reverse proxy/load
balancer/VIP bên ngoài vẫn nằm ngoài phạm vi của tool.

## 6. Invariant và precheck

- ít nhất một master;
- endpoint không trùng vai trò và tên hợp lệ;
- mỗi satellite thuộc đúng một zone, tối đa hai endpoint mỗi zone;
- managed Galera có một node hoặc số lẻ từ ba node;
- Icinga DB feature/module bắt buộc, IDO bị chặn;
- zone nguồn mồ côi và đổi master-zone trên cluster đang chạy bị chặn.

## 7. Vòng đời node

Node mới được bootstrap một lần rồi `add-master`/`add-node` (satellite/client). Xoá node là hai pha: playbook xoá
workload trên target, operator cập nhật inventory, sau đó `reconfigure` đồng bộ topology. CA host
không được xoá trực tiếp. Membership Galera không thuộc lệnh remove master/satellite.

## 8. Vai trò runtime

### 8.1. Satellite và client

Satellite nhận config từ parent zone và có thể thực thi check do operator định nghĩa. Client là
command endpoint một node. Role chỉ quản lý zone, endpoint, certificate và cờ accept-config/
accept-commands; không tạo Host/Service cho các node này.

## 9. Icinga 2

### 9.1. CA HA

CA private key được sao sang master peer để còn khả năng ký certificate khi CA host chính lỗi. Backup
PKI vẫn bắt buộc trước mọi thay đổi phá huỷ.

### 9.2. Config monitoring

Role không quản lý hay đồng bộ trực tiếp `zones.d`. Operator tự triển khai static DSL lên master đầu
tiên bằng pipeline riêng, quản lý object qua Director, hoặc dùng FileShipper để Director đóng gói
file operator-owned. Với static HA, config đặt trong
`zones.d/<ZoneName>` trên master đầu tiên được **Icinga** config-sync sang master peer; đây không phải
deployment node ghi đè monitoring config. Cây config được mount nguyên thư mục chỉ bảo đảm nội dung
đã có trên node tồn tại bền vững.

### 9.3. SSH và secret

SSH key, plugin và credential API hoàn toàn local trên từng executor; deployment node không phân
phối chúng. Role tạo `/etc/icinga-ansible/icinga2/secrets` trên từng master. Thư mục này thuộc cây
config đã bind-mount RW nguyên khối vào `/data/etc/icinga2`, nên không cần mount riêng. Role không
render/reconcile credential bên trong; sửa file trên host được container thấy ngay. Xóa target bằng
`remove-*`/`destroy` cũng xóa thư mục local này. `backup-full` chụp nguyên cây endpoint để DR; Git/vault
vẫn phải là nguồn quản lý dài hạn cho credential và monitoring content.

### 9.4. Custom image

Project không build image. Operator build/push image bất biến rồi khai `custom_image_registry` và
`custom_image_overrides`.

## 10. Backup và recovery

`backup-full` gom inventory/topology, config controller, physical MariaDB, PKI, Web config và nguyên
state Icinga 2 của từng master/satellite/client về destination ngoài config tree. State endpoint gồm
`zones.d`, secrets/plugin, certificate và `icingadb.env` trên master. Bundle tạo checksum/manifest rồi
mới cập nhật `LATEST_COMPLETE`; destroy không xoá backup destination.

`restore-node-state` có hai mode: `existing` chỉ rollback khi CA hiện tại khớp bundle và lưu rollback
local; `clean` yêu cầu VM chưa có CA/cert/config. Logical hostname, thứ tự group, zone master và loại DB
phải giống metadata, còn `ansible_host` có thể đổi. `mariadb-recovery` reconcile `server.cnf` theo
inventory hiện tại trước khi bootstrap DB; sau node-state phải restore DB, deploy runtime tạm, phục hồi
environment ID và Web đúng thứ tự trước deploy/check cuối. Quy trình thao tác từng bước nằm ở mục 7
trong `QUICKSTART.md`.

### 10.1. Failure model

Trong project này, “mất node” chỉ trạng thái VM và toàn bộ boot/data disk hoặc state local đã mất vĩnh
viễn, không thể đưa node cũ trở lại và bắt buộc phải provision VM sạch. Container/service dừng, VM
power-off, reboot, mất mạng, network partition hoặc lỗi host nhưng disk còn phục hồi được chỉ là
“temporarily unavailable”, không phải mất node. VM thay thế dùng lại cùng IP/name vẫn là recovery từ một
node đã mất.

Mất một Icinga master không được làm dừng check engine trên master peer; Director vẫn là singleton trên
`ca_host`. Kết quả failover phải được xác minh bằng execution timestamp sau thời điểm lỗi, không chỉ state
đang lưu trong API. Thay CA host bị mất vĩnh viễn phải restore đúng PKI/identity từ full backup hoặc theo
một kế hoạch CA migration riêng; việc reorder inventory đơn thuần không phải recovery.

Galera ba node chịu được một crash. Hai crash làm component còn lại mất Primary/quorum; shutdown có trật
tự có thể thu nhỏ membership mà vẫn Primary nên không dùng để kết luận behavior crash. Khi datadir còn
nguyên, `recover-cluster` chỉ bootstrap sau khi `wsrep-recover` tìm được history UUID chiếm đa số và chọn
node có seqno cao nhất. Khi không chứng minh được history an toàn hoặc disk đã mất, recovery bắt buộc đi
từ backup thay vì force bootstrap.

## 13. Upgrade

Version đích nằm trong `icinga_image_versions`. `upgrade-plan` kiểm tra image và migration;
`upgrade` backup trước, rolling Galera/runtime rồi postcheck. Thay đổi major/schema không dùng deploy
thông thường. External DB cần change plan riêng của DBA.

## 14. Nội dung operator

Director chỉ được enable/migrate; Kickstart và object management do operator thực hiện. FileShipper
tuỳ chọn được pin checksum và mount read-only vào `/usr/share/icingaweb2/modules/fileshipper`; nguồn
DSL/import nằm trong cây Web persistent. Role tạo mapping nhưng không tạo/reconcile nội dung nguồn,
và chỉ Director deployment do operator kích hoạt mới publish thay đổi.
