# Thiết kế icinga-ansible

## 1. Phạm vi

Project quản lý hạ tầng chạy Icinga: node, container, topology, PKI, API, Icinga DB, Redis, Web và
database. Project không sở hữu Host, Service, CheckCommand, apply rule hoặc Notification và không
vận chuyển/validate static DSL. Nội dung monitoring hoàn toàn thuộc operator.

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
nguồn override/operator. Node đích nhận config tại `/etc/icinga-ansible`; state ghi được nằm dưới
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

Role không đọc, copy, mount hoặc xoá `zones.d`. Cấu hình hạ tầng mới do role sở hữu được kiểm tra
bằng `icinga2 daemon -C` với đúng tập mount trước khi container phục vụ bị thay đổi.

## 5. Network

Service dùng Docker host network. Port cluster/API 5665 nối trực tiếp theo endpoint; không đặt VIP ở
đây. Web mặc định dùng 8080. Nếu cần HAProxy/Keepalived/VIP Web thì quản lý bên ngoài vì role
`loadbalancer` hiện fail-fast, chưa được hiện thực.

## 6. Invariant và precheck

- ít nhất một master;
- endpoint không trùng vai trò và tên hợp lệ;
- mỗi satellite thuộc đúng một zone, tối đa hai endpoint mỗi zone;
- managed Galera có một node hoặc số lẻ từ ba node;
- Icinga DB feature/module bắt buộc, IDO bị chặn;
- zone nguồn mồ côi và đổi master-zone trên cluster đang chạy bị chặn.

## 7. Vòng đời node

Node mới được bootstrap một lần rồi `add-master`/`add-node`. Xoá node là hai pha: playbook xoá
workload trên target, operator cập nhật inventory, sau đó `reconfigure` đồng bộ topology. CA host
không được xoá trực tiếp. Membership Galera không thuộc lệnh remove master/satellite.

## 8. Vai trò runtime

### 8.3. Satellite và client

Satellite nhận config từ parent zone và có thể thực thi check do operator định nghĩa. Client là
command endpoint một node. Role chỉ quản lý zone, endpoint, certificate và cờ accept-config/
accept-commands; không tạo Host/Service cho các node này.

## 9. Icinga 2

### 9.2. CA HA

CA private key được sao sang master peer để còn khả năng ký certificate khi CA host chính lỗi. Backup
PKI vẫn bắt buộc trước mọi thay đổi phá huỷ.

### 9.3. Config monitoring

Role không quản lý hay đồng bộ `zones.d`. Operator tự triển khai static DSL trực tiếp lên master đầu
tiên bằng pipeline riêng hoặc quản lý object qua Director. Với static HA, config đặt trong
`zones.d/<ZoneName>` trên master đầu tiên được **Icinga** config-sync sang master peer; đây không phải
deployment node ghi đè monitoring config. Cây config được mount nguyên thư mục chỉ bảo đảm nội dung
đã có trên node tồn tại bền vững.

### 9.4. SSH và secret

SSH key, plugin và credential chỉ là kênh vận chuyển operator-owned. Chúng không kích hoạt object nào
nếu operator chưa tự định nghĩa CheckCommand/Host/Service.

Tầng `config/icinga2/secrets` chỉ được phân phối tới master, dành cho API credential như
`clouds.yaml`; tầng `config/icinga2/secret` vẫn là global cho mọi Icinga node. Runtime secret được
mount tại `/etc/icinga-ansible/icinga2` trong container và không được ghi vào monitoring DSL.

### 9.6. Custom image

Project không build image. Operator build/push image bất biến rồi khai `custom_image_registry` và
`custom_image_overrides`.

## 10. Backup và recovery

`backup-full` gom config controller, MariaDB, PKI và Web config về destination ngoài config tree, tạo
checksum/manifest rồi mới cập nhật `LATEST_COMPLETE`. Destroy không xoá backup destination.
Recovery tách config, PKI, DB và Web để có thể kiểm soát thứ tự khôi phục.

## 13. Upgrade

Version đích nằm trong `icinga_image_versions`. `upgrade-plan` kiểm tra image và migration;
`upgrade` backup trước, rolling Galera/runtime rồi postcheck. Thay đổi major/schema không dùng deploy
thông thường. External DB cần change plan riêng của DBA.

## 14. Nội dung operator

Director chỉ được enable/migrate; Kickstart và object management do operator thực hiện. Static DSL
phải được triển khai bằng một quy trình độc lập ngoài project.
