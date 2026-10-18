# Quickstart — icinga-ansible

Hướng dẫn này dành cho người **chưa từng dùng** `icinga-ansible`. Đọc từ trên xuống, làm theo thứ tự
là chạy được. Muốn hiểu sâu kiến trúc/thiết kế thì đọc [`design.md`](design.md); muốn xem
trạng thái dự án + bug đã gặp/đã fix thì đọc [`TODO.md`](TODO.md).

## 0. Đây là gì?

`icinga-ansible` là công cụ triển khai + vận hành **Icinga 2 monitoring stack** bằng
**Ansible + Docker**, theo phong cách `kolla-ansible` (OpenStack). Nó dựng 5 thành phần, chạy mỗi
thứ trong 1 container riêng:

| Thành phần | Vai trò |
|---|---|
| `icinga2` | Core — chạy check, quản lý cluster/zone |
| `icingadb` | Daemon đồng bộ dữ liệu check từ Redis vào MariaDB |
| `icingadb-redis` | Redis riêng cho Icinga DB (không phải cache chung) |
| `icingaweb2` | Web UI (Apache2), nơi bạn xem dashboard |
| `mariadb` | Database lưu kết quả check (dùng Icinga DB — **không** dùng IDO/PDO kiểu cũ) |

Bạn không cần cài từng cái tay — chỉ cần khai vài biến trong 1 file YAML (`globals.yml`), rồi chạy
1 lệnh, `icinga-ansible` tự lo phần còn lại (tạo container, ký chứng chỉ, khởi tạo database...).

## 1. Yêu cầu trước khi bắt đầu

- **Hệ điều hành host đích**: Ubuntu 24.04 hoặc 26.04 (đã verify — bản khác chưa test).
- **Máy điều khiển** (nơi bạn chạy lệnh `icinga-ansible`, có thể là 1 trong các host đích hoặc máy
  riêng): cần Python 3, `python3-venv` và SSH tới được các host đích. Ansible được cài bằng pip trong
  venv do operator quản lý.
- **User chạy lệnh**: cần **sudo không cần nhập mật khẩu** (`passwordless sudo`) trên mọi host đích —
  Ansible tự nâng quyền (`become`) khi cần (cài Docker, tạo container...).
- **Nếu host đích sau proxy công ty** (không ra Internet trực tiếp): chuẩn bị sẵn URL proxy, sẽ khai
  ở bước cấu hình.

> ⚠️ **Lưu ý quan trọng, dễ nhầm nhất**: chạy lệnh `icinga-ansible` bằng **user thường có sudo**
> (vd `ubuntu`), **ĐỪNG** `sudo icinga-ansible ...` hay `sudo su` rồi chạy. Ansible tự `sudo` đúng
> lúc cần cho từng bước — nếu bạn tự bọc `sudo` cả câu lệnh, SSH ra các host khác (trong cụm nhiều
> node) sẽ dùng nhầm key của `root` (không có quyền) thay vì key thật của user, gây lỗi
> `unreachable` khó hiểu.

## 2. Cài nhanh — 1 host (all-in-one)

Cách nhanh nhất để "sờ" được sản phẩm: deploy mọi thứ trên **1 máy duy nhất**.

```bash
# 0. Lấy code (đường dẫn tuỳ ý, ví dụ /opt/icinga-ansible)
cd /opt/icinga-ansible

# 1. Tạo venv, activate và cài Ansible + collection cần thiết
sudo apt update
sudo apt install -y python3-venv
sudo install -d -o "$(id -un)" -g "$(id -gn)" /path/to/venv
sudo chown -R "$(id -un):$(id -gn)" /path/to/venv
python3 -m venv /path/to/venv
source /path/to/venv/bin/activate
python -m pip install -U pip
python -m pip install ansible
ansible-galaxy collection install -r ansible/requirements.yml

# 2. Khởi tạo cấu hình thật (tách biệt hoàn toàn khỏi code, xem mục 5 bên dưới)
./tools/icinga-ansible init-config      # tạo /etc/icinga-ansible (cần sudo, chỉ chạy 1 lần)
./tools/icinga-ansible genpwd           # sinh mật khẩu ngẫu nhiên mạnh vào passwords.yml

# 3. (tuỳ chọn) Sửa cấu hình — mặc định đã chạy được ngay, không bắt buộc sửa bước này
$EDITOR /etc/icinga-ansible/globals.yml

# 4. Copy inventory mẫu ra ngay đây (giống kolla-ansible: "cp .../all-in-one ." rồi dùng path
#    ngắn) — không bắt buộc gõ "ansible/inventory/all-in-one" đầy đủ mỗi lần
cp ansible/inventory/all-in-one .

# 5. Chuẩn bị host (cài Docker Engine, chrony, tạo thư mục/mạng cần thiết)
./tools/icinga-ansible bootstrap-servers -i all-in-one

# 6. Kiểm tra cấu hình hợp lệ, rồi triển khai thật
./tools/icinga-ansible prechecks -i all-in-one
./tools/icinga-ansible deploy    -i all-in-one

# 7. In thông tin đăng nhập
./tools/icinga-ansible post-deploy -i all-in-one
```

Trong phiên shell mới, chạy lại `source /path/to/venv/bin/activate` trước khi gọi
`icinga-ansible`. Lệnh `deactivate` thoát khỏi venv khi không còn vận hành hệ thống.

Mỗi lệnh chạy xong sẽ in ra **recap** dạng:

```
PLAY RECAP *********************************************************************
localhost  : ok=42  changed=20  unreachable=0  failed=0  skipped=5
```

`failed=0` là dấu hiệu chạy thành công. Có `failed` khác 0 thì đọc log phía trên để biết task nào lỗi.

### Đăng nhập Web UI

- URL: `http://<ip-host>:8080/authentication/login` (chú ý **cổng 8080**, không phải 80/443).
- User: `admin` (mặc định, đổi được qua `icingaweb2_admin_user` trong `globals.yml`).
- Mật khẩu: xem giá trị `icingaweb2_admin_password` trong `/etc/icinga-ansible/passwords.yml`
  (do `genpwd` sinh ngẫu nhiên ở bước 2 — mở file lên đọc, hoặc tự sửa lại giá trị bạn muốn).

Nếu login được và thấy dashboard (dù chưa có host/service nào ngoài chính nó) — **vậy là thành công**.

## 3. Cài nhanh — HA nhiều host (1 deployment node + 2 master + 2 satellite + 3 Galera)

Mô hình HA đầy đủ, khác mục 2 ở chỗ: **deployment node là 1 máy RIÊNG** (chỉ chạy Ansible, không
chạy `icinga2`/`icingadb`/`mariadb` gì cả — khác setup lab kiểu `master1` kiêm luôn control node),
SSH ra 7 host quản lý (2 master HA + 2 satellite 1 zone con + 3 node Galera cluster thật). Có sẵn
inventory mẫu `ansible/inventory/ha-2master-2satellite-galera3` — chỉ cần đổi IP.

```bash
# 0. Trên DEPLOYMENT NODE (máy riêng, KHÔNG phải master1/master2/...) — lấy code, tạo venv
cd /opt/icinga-ansible
sudo apt update
sudo apt install -y python3-venv
sudo install -d -o "$(id -un)" -g "$(id -gn)" /path/to/venv
sudo chown -R "$(id -un):$(id -gn)" /path/to/venv
python3 -m venv /path/to/venv
source /path/to/venv/bin/activate
python -m pip install -U pip
python -m pip install ansible
ansible-galaxy collection install -r ansible/requirements.yml

# 1. SSH key của deployment node phải có mặt trong authorized_keys của CẢ 7 host quản lý
for h in <ip-master1> <ip-master2> <ip-sat01> <ip-sat02> <ip-galera1> <ip-galera2> <ip-galera3>; do
  ssh-copy-id ubuntu@$h
done

# 2. Khởi tạo cấu hình thật NGAY TRÊN DEPLOYMENT NODE (không phải trên master1 hay host nào khác —
#    $CONFIG_DIR sống ở đây, xem mục 5 + "ansible_connection=local là gì?" ở mục 5.4)
./tools/icinga-ansible init-config
./tools/icinga-ansible genpwd

# 3. Copy inventory mẫu ra ngay đây (giống kolla-ansible, path ngắn — xem mục 5.4 "Inventory"),
#    sửa IP thật
cp ansible/inventory/ha-2master-2satellite-galera3 my-ha-cluster
$EDITOR my-ha-cluster
# -> đổi 7 dòng ansible_host thành IP thật.
# -> không thêm "ansible_connection=local": master1 là SSH target như 6 host còn lại.

# 4. (tuỳ chọn) Sửa cấu hình — vd khai satellite_zones cho zone con "dc-hcm" gồm sat01+sat02
$EDITOR /etc/icinga-ansible/globals.yml

# 5. Chuẩn bị cả 7 host (cài Docker/chrony, tạo thư mục/mạng) — chỉ cần 1 lần
./tools/icinga-ansible bootstrap-servers -i my-ha-cluster

# 6. Kiểm tra cấu hình hợp lệ, rồi triển khai thật
./tools/icinga-ansible prechecks -i my-ha-cluster
./tools/icinga-ansible deploy    -i my-ha-cluster

# 7. In thông tin truy cập
./tools/icinga-ansible post-deploy -i my-ha-cluster
```

`failed=0` trên **cả 7 host** trong recap là thành công (không chỉ 1 dòng `localhost` như mục 2).
Login Web UI ở **bất kỳ master nào** cũng được (`http://<ip-master1 hoặc master2>:8080/...`) — cả 2
đều active/active, chưa cần load balancer/VIP để bắt đầu dùng thử (thêm sau nếu muốn 1 URL duy nhất,
xem `design.md`).

> **Khác biệt cốt lõi so với setup lab 1-máy-kiêm-2-vai-trò**: mọi thao tác vòng đời sau này
> (`deploy`/`reconfigure`/`destroy`/`add-master`...) đều chạy **từ deployment node**, không phải từ
> `master1`. `destroy` cũng xử lý đúng trường hợp này — phần xoá `$CONFIG_DIR`
> (`globals.yml`/`passwords.yml`) nhắm đúng vào deployment node dù nó không nằm trong inventory
> (xem mục 7, lệnh `destroy`).

> **Host hoàn toàn mới (VM vừa cài lại/chưa từng pull image nào)**: `deploy` có thể fail ở bước
> khởi động container do Docker Hub rate-limit (`429 Too Many Requests`), hay gặp khi nhiều host
> dùng chung 1 IP proxy ra ngoài. Xem mục 9 (Sự cố thường gặp) — fix bằng `docker login` trên host
> bị chặn rồi `deploy` lại, không cần làm gì thêm.

### 3.1. Mô hình 5 máy: 2 master + 3 Galera, quản lý check SSH bằng Director

Inventory `ansible/inventory/ha-icinga5-director` là ví dụ đã chạy thực tế cho đúng mô hình này. File
`ha-icinga5-director-extra.yml` bật Director, cài Linuxfabrik Monitoring Plugins trên các target và khai báo
5 Host cùng 3 **Service Apply Rule** (CPU/RAM/Disk) trong database của Director. Ba rule sinh ra tổng cộng
15 service runtime, không tạo 15 Service object riêng và không sinh `Host`/`Service` tĩnh trong `zones.d`.

Khi áp dụng cho môi trường khác, copy hai file mẫu, đổi IP và danh sách object rồi chạy theo thứ tự:

```bash
cp ansible/inventory/ha-icinga5-director my-icinga5
cp ansible/inventory/ha-icinga5-director-extra.yml my-icinga5-extra.yml
$EDITOR my-icinga5
$EDITOR my-icinga5-extra.yml

./tools/icinga-ansible bootstrap-servers -i my-icinga5 -e @my-icinga5-extra.yml
./tools/icinga-ansible prepare-check-by-ssh -i my-icinga5 -e @my-icinga5-extra.yml
./tools/icinga-ansible prechecks -i my-icinga5 -e @my-icinga5-extra.yml
./tools/icinga-ansible deploy -i my-icinga5 -e @my-icinga5-extra.yml
./tools/icinga-ansible check -i my-icinga5 -e @my-icinga5-extra.yml
ICINGA_API_URL=https://<IP-master1>:5665/v1 \
  ./tools/verify-director-ssh-checks /etc/icinga-ansible/passwords.yml icinga5- 15
```

`prepare-check-by-ssh` tạo một Ed25519 key riêng cho runtime monitoring, cấp public key lên target và pin
host key vào một `known_hosts` riêng. Nó không tái sử dụng SSH key quản trị của Ansible và không tắt
`StrictHostKeyChecking`. Private key chỉ được đồng bộ read-only vào hai container Icinga master. Director
được kickstart/migrate/deploy bằng CLI idempotent; chạy lại playbook không tạo object trùng.

Ba CheckCommand dùng plugin chuẩn từ Linuxfabrik ở `/usr/lib64/nagios/plugins`: `cpu-usage`,
`memory-usage`, `disk-usage`. Mỗi host cần monitor mang `vars.monitor_linuxfabrik: true`; ba Apply Rule dùng
`assign_filter: "host.vars.monitor_linuxfabrik=true"` nên host mới tự nhận đủ CPU/RAM/Disk. Sáu ngưỡng được
khai báo trong `director_managed_custom_variables` với kiểu `number`, rồi gắn vào ba Service Template trong
`director_managed_service_templates`. Apply Rule import template tương ứng nên Director hiển thị ô số có
nhãn rõ ràng trong tab **Custom Variables**. Giá trị mặc định nằm ở template; có thể sửa trong YAML hoặc
nhập giá trị override trên từng Apply Rule. Các tên biến là `lfmp_cpu_warn/crit`, `lfmp_memory_warn/crit`,
`lfmp_disk_warn/crit`.

Ví dụ tối thiểu trong extra-vars hoặc `globals.yml`:

```yaml
director_managed_hosts:
  - name: "openstack-controller01"
    address: "172.28.81.101"
    vars: { monitor_linuxfabrik: true }

director_managed_custom_variables:
  - name: "lfmp_cpu_warn"
    uuid: "7ae6c919-40f8-5fc2-8b2d-e1455dfc5501"
    type: "number"
    label: "CPU warning (%)"
  - name: "lfmp_cpu_crit"
    uuid: "7ae6c919-40f8-5fc2-8b2d-e1455dfc5502"
    type: "number"
    label: "CPU critical (%)"

director_managed_service_templates:
  - name: "Linuxfabrik CPU defaults"
    check_command: "by_ssh_lfmp_cpu"
    vars: { lfmp_cpu_warn: 80, lfmp_cpu_crit: 90 }

director_managed_service_apply_rules:
  - name: "CPU"
    check_command: "by_ssh_lfmp_cpu"
    assign_filter: "host.vars.monitor_linuxfabrik=true"
    imports: ["Linuxfabrik CPU defaults"]
    vars: { ssh_user: "icinga-monitor" }
```

Giữ nguyên UUID của mỗi custom variable khi chuyển cấu hình giữa các hệ thống; Director dùng UUID để giữ
liên kết giữa schema, template và giá trị. File `ansible/inventory/openstack-cluster-director-extra.yml`
có ví dụ hoàn chỉnh cho cả CPU, RAM và Disk.

`director_managed_services` vẫn dành cho Service object phải gắn trực tiếp vào từng host. Khi chuyển một
deployment cũ sang Apply Rule, khai `director_managed_direct_services_absent: [CPU, RAM, Disk]`; role lưu
Apply Rule, xoá các Service object cũ rồi deploy tất cả trong cùng một Director configuration. Danh sách này
có thể giữ nguyên vì thao tác dọn là idempotent.

### 3.2. Monitor các node OpenStack bên ngoài cụm Icinga

Các controller/compute OpenStack chỉ là **target được monitor**, vì vậy đặt chúng trong group
`[linuxfabrik_targets]`, không đặt trong `[all_hosts]`. Nhờ đó `deploy`, `upgrade` và `destroy` chỉ tác động
đến stack Icinga; lệnh `prepare-check-by-ssh` mới kết nối tới target để cài plugin và cấu hình SSH.

Thêm vào inventory của deployment node (đổi đường dẫn key quản trị cho đúng môi trường):

```ini
[linuxfabrik_targets]
openstack-controller01 ansible_host=172.28.81.101 ansible_user=root ansible_ssh_private_key_file=/home/ubuntu/.ssh/openstack-root
openstack-controller02 ansible_host=172.28.81.102 ansible_user=root ansible_ssh_private_key_file=/home/ubuntu/.ssh/openstack-root
openstack-controller03 ansible_host=172.28.81.103 ansible_user=root ansible_ssh_private_key_file=/home/ubuntu/.ssh/openstack-root
openstack-compute01    ansible_host=172.28.81.104 ansible_user=root ansible_ssh_private_key_file=/home/ubuntu/.ssh/openstack-root
openstack-compute02    ansible_host=172.28.81.105 ansible_user=root ansible_ssh_private_key_file=/home/ubuntu/.ssh/openstack-root
openstack-compute03    ansible_host=172.28.81.106 ansible_user=root ansible_ssh_private_key_file=/home/ubuntu/.ssh/openstack-root

[linuxfabrik_targets:vars]
ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new'
```

Copy nội dung `ansible/inventory/openstack-cluster-director-extra.yml` vào `globals.yml`, hoặc truyền file
đó bằng `-e @...`. Ngưỡng mặc định nằm trên Service Template; `ssh_user` nằm trên từng Apply Rule. Host
check dùng TCP/22; service check dùng Linuxfabrik qua SSH.

```bash
source /path/to/venv/bin/activate
cd /home/ubuntu/icinga-ansible

# Chạy một lần và chạy lại khi rotate key/thêm node. Lệnh này:
# - tạo key riêng tại /etc/icinga-ansible/config/icinga2/ssh/id_monitor;
# - cài package linuxfabrik-monitoring-plugins trên target;
# - tạo user hệ thống icinga-monitor không có quyền sudo;
# - chỉ nhận ba plugin CPU/RAM/Disk qua forced-command;
# - chỉ nhận key từ IP của các node trong group [master];
# - pin host key vào known_hosts riêng.
./tools/icinga-ansible prepare-check-by-ssh \
  -i ansible/inventory/ha-lab-2master-galera3

./tools/icinga-ansible deploy \
  -i ansible/inventory/ha-lab-2master-galera3
./tools/icinga-ansible check \
  -i ansible/inventory/ha-lab-2master-galera3
```

Không dùng private key quản trị OpenStack làm runtime key của Icinga. Có hai đường dẫn SSH cố ý khác nhau:

- `/etc/icinga-ansible/config/icinga2/ssh/` trên deployment node là **nguồn cấu hình** do người vận hành
  quản lý. `prepare-check-by-ssh` tạo `id_monitor`, `id_monitor.pub` và `known_hosts` tại đây; `backup-full`
  sao lưu thư mục này.
- `/etc/icinga-ansible/icinga2/ssh/` trên mỗi node chạy Icinga 2 là **bản runtime** do Ansible đồng bộ từ
  nguồn trên. Bản này có thể tái tạo bằng `reconfigure` và được mount read-only vào container tại
`/etc/icinga2/ssh/`.

Với credential dành cho plugin tùy biến (ví dụ `clouds.yaml` hoặc một SSH private key không thuộc
luồng `prepare-check-by-ssh`), có thể đặt file trên deployment node theo ba tầng:

```text
/etc/icinga-ansible/config/icinga2/
├── secret/                         # global: mọi master, satellite và client
│   ├── clouds.yaml
│   └── nested/common-token
├── group_master/secret/            # chỉ các node trong group [master]
│   └── clouds.yaml                 # ghi đè file global cùng đường dẫn
├── group_satellite/secret/         # chỉ các node trong group [satellite]
│   └── id_openstack_check
└── master1/secret/                 # chỉ inventory host master1
    └── clouds.yaml                 # ghi đè cả global và group_master trên master1
```

Thứ tự trộn cố định là **global → loại node → host**. Việc ghi đè diễn ra theo đường dẫn tương đối của
từng file, không thay thế cả thư mục: trong ví dụ trên, `nested/common-token` vẫn có trên `master1`, còn
`clouds.yaml` của `master1/secret` thắng hai tầng trước. Các tên thư mục loại node được hỗ trợ là
`group_master`, `group_satellite` và `group_client`; tên tầng host phải khớp chính xác
`inventory_hostname` trong inventory.

`deploy`/`reconfigure` trộn các file áp dụng cho từng node rồi bind-mount read-only vào container tại
`/etc/icinga-ansible/icinga2/`. Một file runtime bị xóa khi đường dẫn đó không còn ở bất kỳ tầng nguồn áp
dụng cho node; các thư mục con rỗng còn lại cũng được dọn. Nếu không có cả ba thư mục nguồn, node không tạo
và không mount thư mục runtime. Chỉ cần
một thư mục nguồn tồn tại, kể cả đang rỗng, mount vẫn được bật. Giữ private key ở mode `0600`; không commit
bất kỳ thư mục `secret/` nào vào Git. File mode `0600` phải thuộc user chạy Ansible, và mọi thư mục cha phải
cho user đó quyền đi xuyên qua; playbook fail nếu `find` báo có nhánh không đọc được. Check script trong
container đọc đường dẫn như
`/etc/icinga-ansible/icinga2/clouds.yaml`.

Đây là input của deployment node nên `backup-full` tự đưa cả thư mục vào `config-<ts>.tar.gz`, và
`restore-config` phục hồi nó cùng `globals.yml`, `passwords.yml` và các override khác.

Nếu deployment node là máy riêng, không thuộc group `[master]` hoặc `[satellite]`, nó chỉ cần thư mục nguồn
dưới `config/`. Thư mục runtime không được tạo mới trên deployment node; nếu còn ở đó thì thường là dữ liệu
sót lại từ lúc máy từng đồng thời làm master hoặc từng được đưa vào inventory dịch vụ. `authorized_keys` của
`icinga-monitor` dùng cả `from=`, `restrict` và `command=`; dù runtime key bị lộ, nó không mở shell và không
chạy được lệnh ngoài ba plugin.

Kiểm tra 18 service sau khi Director deploy (script chấp nhận prefix và số service để dùng lại cho cụm khác):

```bash
ICINGA_API_URL=https://172.28.83.95:5665/v1 \
  ./tools/verify-director-ssh-checks \
  /etc/icinga-ansible/passwords.yml openstack- 18
```

Kết quả đúng phải có 18 dòng `host | service | check_command | state | output` và exit code 0. State `0` là
OK; CPU/RAM/Disk vượt ngưỡng có thể trả về WARNING/CRITICAL hợp lệ, cần xử lý tải hoặc dung lượng thay vì sửa
SSH.

### 3.3. Monitor Nova/Neutron/Cinder service status không qua Director

CPU/RAM/Disk của từng controller/compute có thể tiếp tục dùng Host và Apply Rule trong Director như mục trên.
Trạng thái control plane của Nova, Neutron và Cinder được khai trực tiếp trong `globals.yml`; Ansible render
thành Host/Service static trong `zones.d/master`. Director không tạo, sửa hoặc deploy các object này.

Luồng mặc định dùng `openstack_service_checks` như bên dưới. Nếu cần tự quản lý toàn bộ object Icinga DSL,
đặt full-file override trên deployment node tại:

```text
/etc/icinga-ansible/config/icinga2/zones.d/master/openstack-services.conf
```

Override này thay thế hoàn toàn nội dung sinh từ `openstack_service_checks`, không merge. Ansible chỉ copy
nó tới `ca_host`, sau đó Icinga2 cluster config-sync sang master còn lại. Xóa override và chạy lại
`reconfigure` sẽ tự quay về template sinh từ `openstack_service_checks`.

Image Icinga 2 phải là image custom có `/opt/icinga-venv/bin/python3`, `openstacksdk` và `PyYAML`. Khai image
đó bằng `custom_image_overrides.icinga2` như mục 5.5. Trên deployment node, tạo file credential:

```bash
install -d -m 0700 /etc/icinga-ansible/config/icinga2/openstack
$EDITOR /etc/icinga-ansible/config/icinga2/openstack/clouds.yaml
chmod 0600 /etc/icinga-ansible/config/icinga2/openstack/clouds.yaml
```

```yaml
clouds:
  production:
    region_name: RegionOne
    auth:
      auth_url: "https://keystone.example.internal:5000/v3"
      username: "icinga-monitoring"
      password: "CHANGE_ME"
      project_name: "service"
      user_domain_name: "Default"
      project_domain_name: "Default"
```

Nên dùng user monitoring riêng. Credential phải có quyền đọc Nova service list, Neutron agent list và Cinder
service list; không cần quyền sửa trạng thái service. Mẫu policy cho tài khoản giới hạn quyền nằm trong
`examples/openstack-rbac/`.

Khai trong `/etc/icinga-ansible/globals.yml`:

```yaml
openstack_service_checks:
  - name: "openstack-production"
    display_name: "OpenStack Production"
    cloud: "production"              # khớp clouds.production ở trên
    services: [nova, neutron, cinder]
    check_interval: 60               # giây
    retry_interval: 30               # giây
    max_check_attempts: 3
```

Cấu hình mẫu tương đương nằm tại `ansible/inventory/openstack-service-checks-extra.yml`. Có thể dùng
cùng `openstack-cluster-director-extra.yml`: file thứ nhất tạo service status static; file thứ hai chỉ tạo
host và CPU/RAM/Disk trong Director.

Kết quả là một Host logic `openstack-production` và ba Service static:

- `nova-service-status`: kiểm tra mọi Nova service có `status=enabled` và `state=up`.
- `neutron-service-status`: kiểm tra mọi Neutron agent có `is_alive=true` và
  `is_admin_state_up=true`.
- `cinder-service-status`: kiểm tra mọi Cinder service có `status=enabled` và `state=up`.

Host logic dùng `dummy` và không đại diện cho một controller cụ thể. Check gọi API OpenStack trực tiếp từ
Icinga master; trong mô hình hai master, Icinga HA tự chọn master thực thi. File `clouds.yaml` được Ansible
đồng bộ mode `0600` và mount read-only vào cả hai container, nên master còn lại có thể nhận duty khi failover.

Áp dụng và kiểm tra:

```bash
source /path/to/venv/bin/activate
cd /home/ubuntu/icinga-ansible

./tools/icinga-ansible prechecks   -i <inventory>
./tools/icinga-ansible reconfigure -i <inventory>
./tools/icinga-ansible check       -i <inventory>

# Ép chạy ngay và đọc kết quả ba service qua Icinga API:
./tools/verify-openstack-ha.sh openstack-production
```

`prechecks` chặn sớm nếu tên host/cloud sai định dạng, service ngoài danh sách hỗ trợ, giá trị interval không
hợp lệ, thiếu `clouds.yaml`, hoặc tên profile không tồn tại. Thêm một cloud khác chỉ cần thêm profile vào
`clouds.yaml` và thêm một phần tử vào `openstack_service_checks`. Các kiểm tra biến này chỉ áp dụng cho luồng
render mặc định; khi có full-file override `openstack-services.conf`, người vận hành chịu trách nhiệm về nội
dung object và credential mà file custom sử dụng. Cú pháp Icinga vẫn được kiểm tra trước khi cập nhật container.

## 4. Nếu host đích ở sau proxy công ty

Nếu host đích không ra Internet trực tiếp, cách đơn giản nhất là khai trên **từng managed node**
trong `/etc/environment`:

```ini
http_proxy="http://proxy.example.internal:3128"
https_proxy="http://proxy.example.internal:3128"
HTTP_PROXY="http://proxy.example.internal:3128"
HTTPS_PROXY="http://proxy.example.internal:3128"
no_proxy="localhost,127.0.0.1,::1,10.0.0.0/24"
NO_PROXY="localhost,127.0.0.1,::1,10.0.0.0/24"
```

Không cần khai lại proxy trong `globals.yml`. `bootstrap-servers` dùng môi trường của managed node
cho `apt`/`get_url`, đồng thời cấu hình Docker và Ubuntu Pro ESM cache đọc chính file này.

Nếu muốn Ansible tự ghi `/etc/environment`, hoặc mỗi nhóm node dùng proxy khác nhau, có thể khai
tuỳ chọn trong `/etc/icinga-ansible/globals.yml` **trước khi** chạy `bootstrap-servers`:

```yaml
proxy_http:  "http://proxy.example.internal:3128"
proxy_https: "http://proxy.example.internal:3128"    # thường trùng proxy_http
proxy_no_proxy: "localhost,127.0.0.1,::1,10.0.0.0/24"   # thêm subnet nội bộ của bạn
```

Proxy này chỉ áp dụng cho traffic RA NGOÀI (cài gói, pull image) — traffic nội bộ giữa các node
trong cụm (`no_proxy`) không đi qua proxy.

`bootstrap-servers` tạo systemd drop-in `EnvironmentFile=-/etc/environment` cho Docker và
`esm-cache.service`. Đây là phần nối systemd vào cùng một nguồn cấu hình; operator vẫn chỉ cần duy
trì `/etc/environment`. Sau khi sửa file, chạy lại `bootstrap-servers` để Docker nạp giá trị mới.

### 4.1. Proxy khác nhau cho từng nhóm node (master/satellite/galera/client)

Nếu master/satellite/galera nằm ở mạng khác nhau và mỗi mạng ra Internet qua 1 proxy riêng (hoặc 1
nhóm không cần proxy dù nhóm khác cần), khai thêm `proxy_group_overrides` bên cạnh
`proxy_http`/`proxy_https`/`proxy_no_proxy` (coi là giá trị **mặc định chung**):

```yaml
proxy_group_overrides:
  satellite:                                          # satellite ở DC/VLAN khác, proxy riêng
    http:  "http://proxy-dc2.example.internal:3128"
    https: "http://proxy-dc2.example.internal:3128"
    no_proxy: "localhost,127.0.0.1,::1,10.1.0.0/24"   # subnet nội bộ RIÊNG của DC2 (khác global)
  galera:                                              # DB nội bộ, không qua proxy dù global có khai
    http:  ""
    https: ""
```

Field nào không khai trong 1 nhóm (`http`/`https`/`no_proxy`) rơi về đúng giá trị global ở trên —
không cần khai đủ cả 3 field mỗi nhóm. Chỉ nhận đúng 4 tên nhóm: `master`, `satellite`, `galera`,
`client` (khớp tên nhóm trong inventory) — `prechecks` sẽ chặn nếu gõ nhầm tên. Áp dụng cho MỌI chỗ
dùng proxy trong dự án: `apt`/Docker daemon lúc `bootstrap-servers`, và traffic ra ngoài của
container `icinga2` (Telegram, webhook...).

## 5. Khái niệm cần biết trước khi đi xa hơn

### 5.1. Repo (code) và Config (dữ liệu thật) tách biệt

Giống `kolla-ansible`:

- **Repo** (thư mục bạn đang đọc file này) = **code**, có thể clone/move/xoá đi build lại tuỳ ý,
  không ảnh hưởng gì tới cụm đang chạy.
- **Config thật** luôn nằm ở đường dẫn hệ điều hành cố định **`/etc/icinga-ansible/`**
  (`globals.yml`, `passwords.yml`), độc lập hoàn toàn với vị trí repo. Đây là nơi bạn **thực sự
  chỉnh sửa** — không sửa file trong `etc/examples/` của repo (đó chỉ là *template* để copy ra).

### 5.2. `globals.yml` — file cấu hình chính

Sau `init-config`, mở `/etc/icinga-ansible/globals.yml` — mọi quyết định triển khai đều khai ở đây:
version image, port, module Web nào bật, loại database (`managed_db` tự dựng Galera hay `external`
trỏ vào DB có sẵn), backup...

### 5.3. `passwords.yml` — mọi mật khẩu/secret

Sinh bằng `genpwd` (giá trị ngẫu nhiên mạnh). Muốn đặt tay 1 giá trị cụ thể (vd mật khẩu admin) thì
sửa trực tiếp file này — không cần chạy lại `genpwd`. Khuyến khích mã hoá sau khi điền xong:
```bash
ansible-vault encrypt /etc/icinga-ansible/passwords.yml
```
(khi mã hoá rồi, CLI tự hỏi vault password mỗi lần chạy lệnh — không cần làm gì thêm).

### 5.4. Inventory — khai host nào làm vai trò gì

Inventory (file kiểu Ansible, ví dụ `ansible/inventory/all-in-one`) khai **host nào đóng vai trò
gì** bằng cách bỏ vào nhóm (group):

| Nhóm | Ý nghĩa |
|---|---|
| `[master]` | Host chạy đầy đủ: `icinga2` + `icingadb` + `icingaweb2`. 1 host = single, 2+ host = HA (tự động, chỉ cần liệt kê thêm) |
| `[satellite]` | Zone con của `master` — chỉ chạy `icinga2` (không web/DB), dùng để phân vùng theo địa lý/mạng |
| `[galera]` | Host chạy MariaDB. 1 host = standalone, số lẻ ≥3 = cluster Galera thật |
| `[loadbalancer]` | (tuỳ chọn) HAProxy + VIP cho web, chỉ cần khi HA nhiều master |

Có 5 inventory mẫu sẵn trong `ansible/inventory/`:

- **`all-in-one`** — mọi vai trò dồn vào 1 host (dùng ở mục 2 phía trên). Phù hợp thử nghiệm/lab nhỏ.
- **`multinode`** — mẫu nhiều host (master+galera dồn chung node), đổi IP theo hạ tầng thật của bạn.
- **`ha-2master-galera3`** — 2 master (HA) + 3 node Galera cluster riêng, KHÔNG satellite.
- **`ha-2master-2satellite-galera3`** — 2 master (HA) + 2 satellite (1 zone con) + 3 node Galera
  cluster riêng (dùng ở mục 3 phía trên). (Trước đây đặt tên `ha-2master-standalone-db` — tên cũ
  sai vì DB ở đây là Galera cluster thật, không phải standalone; đã đổi tên 2026-07-23.)
- **`ha-2master-external-db`** — 2 master (HA) + 2 satellite, trỏ vào Galera cluster ngoài
  (`icinga_database_type=external`, DBA tự quản lý, không qua icinga-ansible).

#### `ansible_connection=local` là gì?

Inventory all-in-one có dòng kiểu:
```ini
localhost ansible_host=127.0.0.1 ansible_connection=local
```
`ansible_connection` báo Ansible **cách kết nối tới host đó** để chạy task — mặc định (không khai
gì) là `ssh`, tức luôn mở SSH ra host, kể cả khi host đó chính là máy đang gõ lệnh. Khai
`ansible_connection=local` nghĩa là **bỏ qua SSH, chạy task thẳng trên chính máy đang chạy
`ansible-playbook`**.

**Khi nào cần, khi nào không:**
- **All-in-one một host**: deployment node cũng là host duy nhất chạy Icinga, nên `localhost` dùng
  local connection.
- **Mọi mô hình multi-master**: deployment node tách riêng hoàn toàn, không phải
  master/satellite/Galera và không nằm trong inventory. Không khai `ansible_connection=local` ở
  đâu; mọi host trong `[all_hosts]` đều được quản lý qua SSH.
  `$CONFIG_DIR` (`/etc/icinga-ansible`: `globals.yml`, `passwords.yml`, override) đặt trên chính
  deployment node này (chạy `init-config`/`genpwd` ở đó), và SSH key của nó phải được
  `authorized_keys` trên toàn bộ host trong inventory.

Muốn triển khai thật với nhiều host: **copy 1 trong các file mẫu ra bất kỳ đâu**, đổi tên/IP theo
hạ tầng của bạn, rồi chạy — **không cần đường dẫn dài**, giống hệt kolla-ansible (hướng dẫn chính
thức của kolla: `cp .../all-in-one .` rồi `kolla-ansible deploy -i ./all-in-one`). `-i` với path
tương đối luôn resolve theo **thư mục bạn đang đứng lúc gõ lệnh**, không phải theo gốc repo — copy
ra đâu, đứng đó gõ tên file là chạy được:

```bash
cp ansible/inventory/multinode my-cluster
$EDITOR my-cluster                 # điền IP/hostname thật

./tools/icinga-ansible bootstrap-servers -i my-cluster
./tools/icinga-ansible prechecks         -i my-cluster
./tools/icinga-ansible deploy            -i my-cluster
```

Copy ra thư mục khác (vd `~/my-cluster`, không cùng chỗ với repo) cũng chạy được y hệt — chỉ cần
đứng đúng chỗ đặt file khi gõ `-i`:

```bash
cp ~/icinga-ansible/ansible/inventory/multinode ~/my-cluster
$EDITOR ~/my-cluster

cd ~
~/icinga-ansible/tools/icinga-ansible deploy -i my-cluster
```

### 5.5. Dùng image custom từ Harbor

`icinga-ansible` không build image. Sau khi build và push bằng `icinga-image-builder`, khai registry và
tag trong `/etc/icinga-ansible/globals.yml`. Ví dụ dùng đủ năm image đã pin:

```yaml
custom_image_registry: "172.28.81.109/openstack.kolla/icinga"
custom_image_overrides:
  icinga2: "icinga2:2.16.5"
  icingadb: "icingadb:1.5.1"
  icingadb_redis: "icingadb-redis:7.4.11"
  icingaweb2: "icingaweb2:2.14.0"
  mariadb: "mariadb:12.3.3"
```

Nếu Harbor dùng CA nội bộ hoặc certificate tự ký, chép CA về deployment node rồi khai thêm trước
khi chạy `bootstrap-servers`:

```bash
sudo install -o "$USER" -g "$USER" -m 0644 harbor-ca.crt /etc/icinga-ansible/harbor-ca.crt
```

```yaml
docker_registry_ca_file: "/etc/icinga-ansible/harbor-ca.crt"
```

Role sẽ xác minh file nguồn rồi cài CA vào
`/etc/docker/certs.d/<registry-host[:port]>/ca.crt` trên mọi managed node. Sau khi đổi CA, chạy lại
`bootstrap-servers` để cập nhật Docker daemon. Không cần hạ bảo mật bằng `insecure-registries`.

Giá trị thực tế được ghép theo dạng
`<custom_image_registry>/<custom_image_overrides.<tên>>`; ví dụ Icinga Web trở thành
`172.28.81.109/openstack.kolla/icinga/icingaweb2:2.14.0`. Không thêm `http://` hoặc `https://` vào
`custom_image_registry`.

Không bắt buộc ghi đè đủ năm image. Ví dụ chỉ dùng image Icinga 2 có thêm Python/OpenStack SDK, còn
bốn image khác tiếp tục lấy từ nguồn upstream:

```yaml
custom_image_registry: "172.28.81.109/openstack.kolla/icinga"
custom_image_overrides:
  icinga2: "icinga2:2.16.5-custom"
```

Sau khi sửa cấu hình, pull và kiểm tra trước khi triển khai:

```bash
source /path/to/venv/bin/activate
./tools/icinga-ansible prechecks -i my-cluster
./tools/icinga-ansible pull      -i my-cluster
./tools/icinga-ansible deploy    -i my-cluster
./tools/icinga-ansible check     -i my-cluster
```

Nếu bật Director, không thêm key `director` vào `custom_image_overrides`: Director là module nằm trong
image `icingaweb2`, vì vậy chỉ cần override `icingaweb2` và bật `director` trong
`enable_icingaweb2_modules`.

## 6. Ghi đè cấu hình (override) — tuỳ biến sâu mà không sửa code

Đây là cơ chế mạnh nhất của `icinga-ansible`: bạn có thể chỉnh **bất kỳ file config nào** (thêm
Host/Service thật, đổi CheckCommand, sửa `resources.ini`, thêm script check/notification tuỳ
biến...) **mà không cần sửa 1 dòng code Ansible nào**, giống hệt cách `/etc/kolla/config/<service>/`
hoạt động trong `kolla-ansible`.

### 6.1. Nơi đặt override

Trên **máy chạy lệnh `icinga-ansible`** (deploy node), thư mục override nằm ở:

```
/etc/icinga-ansible/config/<service>/<file>                        # override CHUNG cho mọi host chạy service đó
/etc/icinga-ansible/config/<service>/group_<tên_nhóm>/<file>        # override cho MỌI host trong 1 nhóm inventory
/etc/icinga-ansible/config/<service>/<tên_host>/<file>              # override RIÊNG chỉ 1 host (ưu tiên cao nhất)
```

Ví dụ: muốn đổi `constants.conf` chỉ riêng host `master1` (không đụng `master2`):
```bash
mkdir -p /etc/icinga-ansible/config/icinga2/master1
$EDITOR /etc/icinga-ansible/config/icinga2/master1/constants.conf
```

Ví dụ: muốn 1 file áp dụng cho **cả `master1` lẫn `master2`** (nhóm `[master]` trong inventory)
nhưng **không** đụng satellite:
```bash
mkdir -p /etc/icinga-ansible/config/icinga2/group_master
$EDITOR /etc/icinga-ansible/config/icinga2/group_master/conf.d/custom-commands.conf
```
`<tên_nhóm>` là đúng tên nhóm bạn đặt trong file inventory (`[master]`, `[satellite]`, `[galera]`,
hoặc nhóm tự đặt thêm tuỳ ý) — không giới hạn ở 4 nhóm mẫu.

**Thứ tự ưu tiên** (cụ thể nhất thắng, giống `merge_configs` của kolla):
1. Override riêng cho đúng host (`config/<service>/<tên_host>/<file>`)
2. Override cho cả nhóm inventory host đó thuộc về (`config/<service>/group_<tên_nhóm>/<file>`)
3. Override chung cho mọi host (`config/<service>/<file>`)
4. Không có override nào → dùng template mặc định của Ansible (hành vi gốc)

Xoá file override đi rồi chạy lại `reconfigure` là **tự động quay về** tầng ưu tiên kế tiếp (hoặc
template mặc định nếu không còn override nào) — không có gì bị "kẹt" lại.

### 6.2. Override THEO ZONE — thêm Host/Service để monitor qua SSH

Tình huống hay gặp nhất: thêm 1 host ngoài (không phải node trong cụm, không cài agent Icinga2) để
monitor qua SSH. Loại override này đặc biệt hơn override thường (mục 6.1) — không tổ chức theo
**tên host chạy Ansible**, mà theo **tên ZONE Icinga2** sẽ thực thi check:

```
config/icinga2/zones.d/master/hosts.conf       # check chạy TỪ 1 endpoint trong zone "master"
config/icinga2/zones.d/master/openstack-services.conf # full-file override service status OpenStack
config/icinga2/zones.d/<tên_satellite_zone>/hosts.conf   # check chạy TỪ 1 satellite trong zone đó
```

Dù đặt ở đâu, file này **luôn chỉ cần ghi 1 bản** — dù cụm có 2 master hay 2 satellite trong cùng
zone, Ansible chỉ ghi ra đúng 1 nơi (`ca_host` = master đầu tiên), rồi chính **Icinga2 cluster tự
đồng bộ xuống mọi node còn lại trong zone đó** (không phải cơ chế override thường ở mục 6.1).

**Cách 1 — check chạy từ zone `master`** (không cần satellite):
```bash
mkdir -p /etc/icinga-ansible/config/icinga2/zones.d/master
$EDITOR /etc/icinga-ansible/config/icinga2/zones.d/master/hosts.conf
```
```
object Host "my-server" {
  address       = "10.0.0.50"
  check_command = "by_ssh_disk"
  vars.ssh_user = "ubuntu"
  zone          = "master"   // BẮT BUỘC khai tường minh trên CẢ Host lẫn Service — khác zone
}                             // satellite (mục dưới), ở đây thư mục KHÔNG tự ngụ ý zone

object Service "disk" {
  host_name     = "my-server"
  check_command = "by_ssh_disk"
  zone          = "master"   // thiếu dòng này Service sẽ bị "paused: true", không chạy
}
```

**Cách 2 — check chạy từ 1 satellite zone** (cần satellite zone đã khai trong `satellite_zones`
của `globals.yml`, ví dụ zone tên `dc-hanoi`):
```bash
mkdir -p /etc/icinga-ansible/config/icinga2/zones.d/dc-hanoi
$EDITOR /etc/icinga-ansible/config/icinga2/zones.d/dc-hanoi/hosts.conf
```
```
object Host "my-server" {
  address       = "10.0.0.50"
  check_command = "by_ssh_disk"
  vars.ssh_user = "ubuntu"
  // KHÔNG cần khai zone = "..." ở đây — tên thư mục "dc-hanoi" đã tự ngụ ý zone
}

object Service "disk" {
  host_name     = "my-server"
  check_command = "by_ssh_disk"
}
```

Áp dụng (cả 2 cách):
```bash
./tools/icinga-ansible reconfigure -i ansible/inventory/my-cluster
```

Vào lại Web UI — Host `my-server` xuất hiện, có check `disk` chạy thật. Kiểm tra đúng check chạy từ
zone nào qua API: `GET /v1/objects/services/my-server!disk` → xem `check_source` (tên host thật sự
thực thi check, không phải nơi bạn đặt override).

> ⚠️ SSH check cần key riêng đặt tại `config/icinga2/ssh/id_monitor` trước (không dùng chung key
> quản trị hạ tầng), và host đích phải cài sẵn `monitoring-plugins` — xem `design.md` mục 9.4/9.5 để
> biết đầy đủ cách thiết lập + 3 bug thật đã gặp lúc làm tính năng này.

### 6.3. Các chỗ hay override khác

| Muốn tuỳ biến | Đặt override ở |
|---|---|
| Host/Service thật (monitor máy ngoài cụm) | `config/icinga2/zones.d/<zone>/hosts.conf` — `<zone>` = `master` hoặc tên satellite zone (mục 6.2, override THEO ZONE, khác cơ chế theo-host ở mục 6.1) |
| CheckCommand tự viết (script check riêng) | Script vào `config/icinga2/custom-plugins/`, khai command vào `config/icinga2/conf.d/custom-commands.conf` |
| Cấu hình MariaDB (`server.cnf`) | `config/mariadb/server.cnf` |
| Resource DB Icinga Web 2 (`resources.ini`) | *(xem lưu ý bên dưới — file này KHÔNG dùng cơ chế override)* |

> ⚠️ **Ngoại lệ đáng nhớ**: config của `icingaweb2` (`resources.ini`, `config.ini`,
> `authentication.ini`, `roles.ini`, module config...) chỉ được Ansible ghi **1 lần duy nhất** lúc
> deploy đầu tiên — sau đó bạn sửa trực tiếp qua **Web UI** (Configuration), Ansible sẽ không tự ghi
> đè lại nữa dù bạn `reconfigure`. Đây là chủ đích, để không mất thao tác bạn làm qua UI. Nếu cụm có
> **nhiều master (HA)**, luôn sửa qua UI trên đúng **`master[0]`** — mỗi master lưu file này riêng,
> không tự đồng bộ giữa các master.

### 6.4. Lưu ý quan trọng

- **Luôn phải chạy `reconfigure` sau khi thêm/sửa/xoá file override** — không có gì tự áp dụng
  ngay lập tức (trừ `resources.ini`/`config.ini` sửa qua UI, xem lưu ý ở trên).
- Thêm host mới vào `hosts.conf` không cần chạy `add-master`/`add-node` — đó là 2 lệnh dành riêng
  cho việc thêm **node hạ tầng** (host chạy container icinga2) vào cụm, khác hẳn việc thêm
  **Host/Service để monitor** (chỉ cần override + `reconfigure`).

## 7. Các lệnh dùng trong vòng đời thường ngày

| Lệnh | Khi nào dùng |
|---|---|
| `bootstrap-servers` | **Chỉ 1 lần** trên host hoàn toàn mới (cài Docker/chrony, tạo thư mục/mạng) |
| `prechecks` | Trước mỗi lần `deploy` — kiểm tra cấu hình hợp lệ (version, topology, cổng...) |
| `deploy` | Triển khai/deploy lần đầu, hoặc apply thay đổi lớn (thêm module, đổi version...) |
| `reconfigure` | Áp dụng thay đổi nhỏ trong `globals.yml`/`passwords.yml` (vd đổi mật khẩu admin) mà không phải deploy lại từ đầu |
| `post-deploy` | In lại thông tin truy cập (URL, user) bất cứ lúc nào |
| `check` | Health-check nhanh cụm đang chạy |
| `mariadb-backup` | Backup database + snapshot CA/PKI (trên node DB) |
| `backup-full` | Backup TOÀN HỆ THỐNG: config control-node + DB + PKI + icingaweb2 config (xem mục 7.1) |
| `CONFIRM=yes-i-really-mean-it restore-config --config-backup <path>` | Khôi phục `/etc/icinga-ansible` từ 1 bản `backup-full` (dùng khi mất trắng deployment node, xem mục 7.1 — **biến môi trường `CONFIRM=`, không phải cờ `-e confirm=`**) |
| `restore-pki -e pki_backup=<path>` | Khôi phục CA/PKI cũ (giữ nguyên cert/CA cũ) trước khi `deploy` lại, xem mục 7.1 |
| `restore-web -e restore_backup_ts=<ts> -e confirm=yes` | Khôi phục cấu hình Icinga Web riêng của từng master từ `backup-full`; chạy `deploy` ngay sau đó |
| `destroy` | Xoá sạch container + dữ liệu + cấu hình render (`/etc/icinga-ansible`: mọi override — GIỮ LẠI `globals.yml`+`passwords.yml` trên deployment node) (**bắt buộc** thêm `-e confirm=yes-i-really-really-mean-it` đúng nguyên văn, giống `kolla-ansible destroy`, không thì bị chặn an toàn) |

Ví dụ đổi mật khẩu admin web sau khi đã deploy:
```bash
$EDITOR /etc/icinga-ansible/passwords.yml     # sửa icingaweb2_admin_password
./tools/icinga-ansible reconfigure -i ansible/inventory/my-cluster
```

Làm lại từ đầu (xoá sạch rồi deploy lại):
```bash
./tools/icinga-ansible destroy -i ansible/inventory/my-cluster -e confirm=yes-i-really-really-mean-it
./tools/icinga-ansible deploy  -i ansible/inventory/my-cluster
# Không cần bootstrap-servers/init-config/genpwd lại — destroy GIỮ LẠI globals.yml + passwords.yml
# trên deployment node (chỉ xoá data + config render trên từng host), Docker/chrony/thư mục base/
# mạng cũng giữ nguyên -> deploy thẳng lại y hệt cụm cũ (cùng mật khẩu).
```
> **Muốn xoá cả `globals.yml`/`passwords.yml`**: `destroy` KHÔNG xoá 2 file này (cố ý, để deploy lại
> không đổi mật khẩu). Nếu thật sự muốn dọn sạch hoàn toàn, tự `rm /etc/icinga-ansible/{globals.yml,passwords.yml}`
> sau khi destroy, rồi `init-config` + `genpwd` lại trước khi `deploy`.

### 7.1. Backup/Restore toàn hệ thống (dựng lại cụm mới từ backup)

Khác `mariadb-backup` (chỉ DB), `backup-full` sao lưu CẢ 4 phần cần để dựng lại cụm từ đầu:

1. **Config control-node** — `globals.yml`, `passwords.yml`, mọi override (`deploy_config_dir/`) —
   nằm trên **deployment node** (máy chạy CLI), KHÔNG phải trên `master1`/`master2`/...
2. **DB (Galera)** — dữ liệu `director`/`icingadb`/`icingaweb2` — nằm trên **node DB chính**
   (`galera[0]`, ví dụ `db1`).
3. **PKI (CA)** — `ca.crt`/`ca.key` dùng để ký cert cho mọi node — nằm trên **`ca_host`**
   (`master[0]`, ví dụ `m1`) — **KHÁC** node DB chính, dễ nhầm vì 2 vai trò này thường không cùng 1
   host trong topology HA.
4. **Icinga Web config theo từng master** — gồm thay đổi file qua Web UI không có trong override; khôi
   phục bằng `restore-web` rồi chạy lại `deploy` để reconcile credential/endpoint được quản lý.

Đã **verify thật nhiều lần trên hạ tầng lab** (design.md mục 10.6/10.7), gồm cả trường hợp dựng lại
trên **hạ tầng IP hoàn toàn khác** bản backup — xem các case cụ thể bên dưới.

Drill gần nhất ngày **2026-10-18** dùng topology 2 master + 3 Galera trên cùng các VM sau khi chạy
`destroy` và xóa toàn bộ `/etc/icinga-ansible`. Bundle được kiểm tra SHA-256 trước restore. Kết quả xác
nhận DB marker, file cấu hình Web riêng trên cả hai master, CA fingerprint và Icinga DB environment ID
đều khớp bản trước khi xóa; thư mục secret được phục hồi; `check` kết thúc với `failed=0`. Drill này
kiểm chứng teardown/rebuild trên cùng hạ tầng, không được hiểu là một lần tạo VM hoặc đổi IP mới.

```bash
# Chạy định kỳ (cron) hoặc trước khi làm việc rủi ro — TỪ deployment node
./tools/icinga-ansible backup-full -i ansible/inventory/my-cluster
# sinh ra trên deployment node, cùng một thư mục:
# /var/backups/icinga-ansible-config/config-<ts>.tar.gz
# /var/backups/icinga-ansible-config/icingaweb2-<host>-<ts>.tar.gz
# /var/backups/icinga-ansible-config/database/db-full-<ts>.xb.gz + LATEST_FULL
# /var/backups/icinga-ansible-config/pki/pki-<ts>.tar.gz
# /var/backups/icinga-ansible-config/manifest-<ts>.sha256 + LATEST_COMPLETE
# (CỐ Ý ngoài /etc/icinga-ansible — "destroy" không bao giờ đụng tới thư mục này)
# Bản gốc vẫn được tạo trên galera[0]/ca_host, sau đó playbook kiểm tra và fetch về deployment node.
# Mọi archive trên deployment node được siết mode 0600 vì chứa secrets, database hoặc CA private key.
# Chỉ coi bundle hoàn chỉnh khi LATEST_COMPLETE trỏ tới timestamp và manifest SHA-256 tương ứng tồn tại.
# Kiểm tra lại sau khi copy off-site: cd /var/backups/icinga-ansible-config && sha256sum -c manifest-<ts>.sha256
# QUAN TRỌNG: đồng bộ cả thư mục trên sang storage nằm ngoài deployment node để chịu được mất node này.
```

> **`restore-config` dùng biến môi trường `CONFIRM=...`, KHÔNG phải cờ `-e confirm=...`** (đây là lệnh
> bash thuần, không qua Ansible — khác mọi lệnh khác trong bảng ở trên). Gõ nhầm thành `-e confirm=...`
> sẽ không có tác dụng, lệnh vẫn dừng lại hỏi xác nhận.

#### Case 1 — Mất TOÀN BỘ hạ tầng, dựng lại trên ĐÚNG IP/hostname cũ

Đã verify thật 2026-07-24 (design.md mục 10.6) trên hạ tầng 7 host (2 master + 2 satellite + 3
galera). Ví dụ cụ thể với timestamp backup `20260802-044728`:

```bash
# 1. Cài lại icinga-ansible trên deployment node mới (hoặc máy cũ cài lại từ đầu)
CONFIRM=yes-i-really-mean-it ./tools/icinga-ansible restore-config \
  --config-backup /path/to/config-20260802-044728.tar.gz
./tools/icinga-ansible bootstrap-servers -i ansible/inventory/my-cluster

# 2a. HƯỚNG "giữ PKI cũ" (client/satellite cũ vẫn nhận diện đúng CA, không phải cấp lại ticket) —
#     copy pki-20260802-044728.tar.gz lên ĐÚNG host sẽ làm ca_host (master[0], vd m1) TRƯỚC, path
#     phải khớp -e pki_backup= dưới đây (chạy trên chính ca_host, không phải deployment node):
scp pki-20260802-044728.tar.gz m1:/home/ubuntu/
./tools/icinga-ansible restore-pki -i ansible/inventory/my-cluster \
  -e pki_backup=/home/ubuntu/pki-20260802-044728.tar.gz -e confirm=yes
# 2b. HƯỚNG "PKI mới" (đơn giản hơn; xem bảng chọn PKI bên dưới) — bỏ qua hẳn bước 2a,
#     "deploy" ở bước 3 sẽ tự sinh CA mới hoàn toàn.

# 3. Chép lại toàn bộ thư mục backup vào đúng icinga_config_backup_dir trên deployment node mới,
#    deploy rồi khôi phục DB. Role tự tìm controller artifact và stage sang galera[0].
#    Không cần scp DB thủ công lên node Galera.
./tools/icinga-ansible deploy -i ansible/inventory/my-cluster
./tools/icinga-ansible mariadb-recovery -i ansible/inventory/my-cluster \
  -e recovery_mode=restore-backup -e restore_backup_ts=20260802-044728 -e confirm=yes
./tools/icinga-ansible recover-db-only -i ansible/inventory/my-cluster -e confirm=yes
./tools/icinga-ansible restore-web -i ansible/inventory/my-cluster \
  -e restore_backup_ts=20260802-044728 -e confirm=yes
./tools/icinga-ansible deploy -i ansible/inventory/my-cluster   # reconcile config/credential và bật lại service
```

Xác nhận đã khôi phục đúng:
```bash
./tools/icinga-ansible check -i ansible/inventory/my-cluster
# Với hướng "giữ PKI cũ": so fingerprint CA cũ/mới phải khớp byte-for-byte
docker exec icinga2 openssl x509 -in /data/var/lib/icinga2/ca/ca.crt -noout -fingerprint -sha256
```

#### Case 2 — Mất TOÀN BỘ hạ tầng, dựng lại trên phần cứng MỚI (IP khác, có thể cả topology khác)

Đã verify thật 2026-08-02 (design.md mục 10.7): destroy hẳn cụm 2 master + 2 satellite + 3 galera,
dựng lại thành **2 master (bớt satellite), IP master đổi hẳn sang vị trí khác** — CA fingerprint khớp
byte-for-byte, DB khôi phục đủ, cụm hoạt động bình thường ở IP mới. **Quy trình y hệt Case 1**, chỉ
khác 2 điểm:

1. **KHÔNG cần IP giống bản backup** — chỉ cần **tên host (`inventory_hostname`)** khớp với những gì
   `globals.yml` đã khai (đặc biệt `satellite_zones[].members`, liệt kê theo TÊN chứ không theo IP).
   Đổi topology (bớt/thêm satellite, đổi tên host...) thì phải **tự sửa tay** `globals.yml` cho khớp
   inventory mới — restore KHÔNG tự đối chiếu/cảnh báo gì nếu bạn quên.
   ```bash
   # Ví dụ: cụm cũ có satellite_zones: [{name: "dc-main", members: ["sat1","sat2"]}], nhưng
   # inventory MỚI không có host nào tên sat1/sat2 (bỏ hẳn satellite) -> PHẢI sửa lại:
   $EDITOR /etc/icinga-ansible/globals.yml   # sau bước restore-config, TRƯỚC bootstrap-servers
   #   satellite_zones: []
   ```
2. **⚠️ Bug đã biết + đã fix (nếu dùng hướng "giữ PKI cũ" VÀ topology mới có thêm master2/satellite
   mới)**: `deploy` có thể fail ở bước cấp cert cho master2/satellite
   (`critical/cli: Ticket salt (--salt) must be specified`) — do CA cũ được restore lại không có sẵn
   `TicketSalt`, trong khi CA hoàn toàn mới thì tự sinh đúng. Đã fix trong
   `roles/icinga2/tasks/main.yml` (tự vá `TicketSalt` mỗi lần khởi tạo `/data`, không chỉ dựa vào
   `node setup`) — nếu gặp lỗi này trên bản code cũ hơn, xem design.md mục 10.7 để biết cách vá tay.

Ví dụ inventory MỚI (IP đổi từ `.152`/`.153` sang `.154`/`.155`, bớt hẳn satellite so với bản backup):
```ini
[all_hosts]
master1 ansible_host=10.10.10.154
master2 ansible_host=10.10.10.155
galera1 ansible_host=10.10.10.156
galera2 ansible_host=10.10.10.157
galera3 ansible_host=10.10.10.158

[master]
master1
master2

[satellite]

[galera]
galera1
galera2
galera3

[icinga:children]
master
satellite
```

#### Chọn hướng PKI nào?

| | Giữ PKI cũ (`restore-pki`) | PKI mới (bỏ qua `restore-pki`) |
|---|---|---|
| Cert/SSH key cũ của client/satellite | Vẫn hợp lệ, không cần cấp lại | Mất hết, phải enroll lại từ đầu (ticket mới) |
| Độ phức tạp | Cao hơn (thêm 1 bước, phải copy đúng file lên đúng `ca_host` MỚI) | Đơn giản nhất — `deploy` tự lo |
| Rủi ro | Bug TicketSalt nếu thêm node mới cùng lúc (đã fix, xem trên) | Không có rủi ro tương tự |
| Khi nào chọn | Cụm có nhiều client/satellite bên ngoài không tiện enroll lại (vd hàng chục host SSH-monitor) | Disaster recovery đơn giản, số node ít, hoặc không chắc PKI cũ còn nguyên vẹn |

#### Case 3 — Chỉ còn bản backup DB, mất cả hai master và không có backup CA/config

Runbook thao tác đầy đủ, gồm topology, safety gate và lệnh verify sau restore nằm trong
[`OPERATIONS-RUNBOOK-VI.md`](OPERATIONS-RUNBOOK-VI.md), mục recovery khi chỉ còn DB.

Đây không phải full restore: DB giữ history/state và database của Director/Web, nhưng **không chứa**
CA private key, `globals.yml`, `passwords.yml`, file `zones.d`, SSH key hay credential OpenStack.
Phải dựng lại các input đó trước; nếu cấu hình cũ nằm trong Director DB thì Director có thể deploy
lại sau khi API của master mới hoạt động. Cấu hình Icinga DSL chỉ từng nằm trên filesystem thì phải
tạo lại từ SCM/tài liệu vận hành — không thể suy ngược đầy đủ từ DB.

Yêu cầu bắt buộc:

- Biết `mariadb_root_password` của thời điểm tạo physical backup. Datadir backup chỉ chứa hash,
  không thể lấy lại plaintext. `icingadb`/`icingaweb2`/`director` password có thể đặt mới và để lần
  `deploy` cuối rotate lại, nhưng root password phải mở được DB vừa restore.
- Dùng cùng version MariaDB đã tạo backup cho lần restore đầu tiên. Dùng đúng Icinga DB/Web series
  tương thích schema cũ; nâng version chỉ làm sau khi recovery và health-check đã PASS.
- CA cũ đã mất nên mọi satellite/agent cũ phải trust CA mới và enroll lại. Giữ nguyên hostname/IP
  không thay thế được bước cấp certificate mới.
- Phục hồi đúng Icinga DB environment ID cũ trên **cả hai master**. Nếu không, dữ liệu mới sẽ được
  ghi như một environment khác và dữ liệu cũ có thể bị tách/trùng trên Web.

Quy trình với bản backup `db-full-<timestamp>.xb.gz`:

```bash
# 1. Dựng config/inventory mới. Điền đúng root password cũ; các secret service có thể đặt mới.
./tools/icinga-ansible init-config
./tools/icinga-ansible genpwd
$EDITOR /etc/icinga-ansible/globals.yml
$EDITOR /etc/icinga-ansible/passwords.yml

# 2. Dựng tạm stack mới để có Galera datadir, CA mới và container/runtime cần thiết.
./tools/icinga-ansible bootstrap-servers -i ansible/inventory/my-cluster
./tools/icinga-ansible deploy -i ansible/inventory/my-cluster

# 3. Đặt physical backup vào controller backup directory; restore sẽ validate rồi tự stage lên galera[0].
sudo install -d -m 0700 /var/backups/icinga-ansible-config/database
sudo install -m 0600 db-full-20260908-120000.xb.gz \
  /var/backups/icinga-ansible-config/database/db-full-20260908-120000.xb.gz
./tools/icinga-ansible mariadb-recovery -i ansible/inventory/my-cluster \
  -e recovery_mode=restore-backup -e restore_backup_ts=20260908-120000 -e confirm=yes

# 4. Lấy environment ID từ DB vừa restore, dừng publisher/consumer, seed cùng ID lên hai master,
#    FLUSHALL Redis tạm và khởi động lại theo đúng thứ tự.
./tools/icinga-ansible recover-db-only -i ansible/inventory/my-cluster -e confirm=yes

# Nếu DB chứa nhiều environment, lệnh trên fail trước khi ghi file. Chọn rõ ID production:
# ./tools/icinga-ansible recover-db-only -i ... -e confirm=yes \
#   -e recover_environment_id=<40-ký-tự-hex>

# 5. Hội tụ lại credential/config, rồi kiểm tra sâu.
./tools/icinga-ansible deploy -i ansible/inventory/my-cluster
./tools/icinga-ansible check -i ansible/inventory/my-cluster
```

Sau recovery phải xác nhận hai master trả cùng nội dung JSON ở
`/var/lib/icinga2/icingadb.env`, DB không phát sinh thêm environment ngoài dự kiến, history cũ đọc
được và mọi agent/satellite đã enroll lại. File environment ID tạm trước recovery được giữ cạnh file
thật với suffix `.before-db-only-recovery` để audit; không được dùng lại file tạm này.

#### Case 4 — Còn nguyên deployment node (config/password/inventory) và DB backup; mất toàn bộ service node

Đây là trường hợp thuận lợi hơn Case 3 và là drill đã chạy thật ngày 2026-10-04 với 2 master, 2 satellite,
3 Galera. Không chạy `init-config`/`genpwd`, vì `/etc/icinga-ansible/globals.yml`, `passwords.yml`, inventory
và override trên deployment node chính là desired state cần giữ. Nếu không còn PKI backup, để lần deploy đầu
tạo CA mới; các satellite/agent được dựng lại phải enroll bằng CA mới.

```bash
# 1. Dựng runtime tạm từ đúng config/inventory còn lại trên deployment node.
./tools/icinga-ansible bootstrap-servers -i ansible/inventory/my-cluster
./tools/icinga-ansible deploy -i ansible/inventory/my-cluster

# 2. Restore trực tiếp artifact do backup-full đã fetch về deployment node.
# Không cần scp lên galera[0]; restore tự đọc LATEST_FULL, validate rồi stage sang Galera mới.
./tools/icinga-ansible mariadb-recovery -i ansible/inventory/my-cluster \
  -e recovery_mode=restore-backup -e restore_backup_tag=full -e confirm=yes

# 3. Khôi phục config Web từng master và environment ID cũ từ DB, sau đó hội tụ toàn stack.
./tools/icinga-ansible restore-web -i ansible/inventory/my-cluster \
  -e restore_backup_ts=<timestamp-trong-LATEST_COMPLETE> -e confirm=yes
./tools/icinga-ansible recover-db-only -i ansible/inventory/my-cluster -e confirm=yes
./tools/icinga-ansible deploy -i ansible/inventory/my-cluster
./tools/icinga-ansible check -i ansible/inventory/my-cluster
```

Director DB được restore nguyên vẹn. Lần deploy cuối chạy migration Director. Với mặc định
`director_auto_kickstart: false`, người vận hành tự chạy Kickstart trong Web UI sau khi restore; Ansible chưa
import hoặc reconcile endpoint/zone trước bước đó. Sau khi Kickstart hoàn tất, chạy lại `reconfigure` và
`check` để kiểm tra topology/object đã phục hồi.

## 8. Thêm/bớt node vào cụm đang chạy (HA)

Thêm 1 master hoặc satellite mới vào cụm đang sống:

```bash
$EDITOR ansible/inventory/my-cluster    # thêm host mới vào nhóm [master] hoặc [satellite]

# Nếu host đó HOÀN TOÀN MỚI (chưa từng cài Docker) — bootstrap trước:
./tools/icinga-ansible bootstrap-servers -i ansible/inventory/my-cluster --limit ten-host-moi

./tools/icinga-ansible add-master -i ansible/inventory/my-cluster   # hoặc add-node cho satellite
```

Gỡ 1 node khỏi cụm:
```bash
./tools/icinga-ansible remove-master -i ansible/inventory/my-cluster \
  -e target_host=ten-host-can-xoa -e confirm=yes    # remove-node cho satellite

$EDITOR ansible/inventory/my-cluster    # xoá host đó khỏi inventory
./tools/icinga-ansible reconfigure -i ansible/inventory/my-cluster   # đồng bộ lại các host còn lại
```

## 9. Sự cố thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `The module interpreter '/path/to/venv/bin/python...' was not found` trên `master1`/managed node | Đã gán nhầm venv của deployment node vào `ansible_python_interpreter` của managed node | Xoá biến đó khỏi inventory/group_vars hoặc đặt `/usr/bin/python3`. Chỉ deployment node dùng `source /path/to/venv/bin/activate` |
| `unreachable` khi chạy trên nhiều host | Bạn chạy `icinga-ansible` qua `sudo`/`sudo su` — SSH ra host khác dùng nhầm key của root | Chạy lại bằng user thường (có sudo passwordless), không bọc `sudo` trước cả câu lệnh |
| `deploy` báo thiếu thư mục (`directory ... does not exist`) trên host mới/vừa `destroy` | Host đó chưa từng chạy `bootstrap-servers` | Chạy `bootstrap-servers` trước, rồi `deploy` lại |
| `apt update`/`docker pull` treo mãi không xong | Thiếu proxy trong `/etc/environment` trên managed node | Khai đủ HTTP/HTTPS/NO_PROXY theo mục 4, chạy lại `bootstrap-servers` |
| `docker pull` Harbor lỗi `x509: certificate signed by unknown authority` | Docker daemon chưa trust CA nội bộ của Harbor | Lưu CA trên deployment node, khai `docker_registry_ca_file`, chạy lại `bootstrap-servers`, rồi `pull` |
| Journal có `ubuntupro.lib.esm_cache` / `contracts.canonical.com` / `Network is unreachable` | `esm-cache.service` chưa được nối với `/etc/environment`, hoặc proxy không truy cập được | Cập nhật code, chạy lại `bootstrap-servers`; dùng `systemctl cat esm-cache.service` kiểm tra dòng `EnvironmentFile=-/etc/environment`, rồi start service và đọc journal |
| `permission denied` khi gọi `docker ...` tay trên host | User chưa vào group `docker`/chưa `sudo` | Ansible tự `become` đúng lúc cần — nếu bạn tự gõ lệnh `docker` tay thì phải tự thêm `sudo` |
| Web login báo lỗi, hoặc không load được trang | Nhầm cổng — web chạy ở **8080**, không phải 80/443 mặc định | Kiểm tra lại URL `http://<ip>:8080/authentication/login` |
| Container `icingadb` cứ `Restarting`, log `FATAL ... unexpected database schema version: vX (expected vY)` (hoặc `unexpected Redis schema version`) | Đổi `icinga_image_versions.icingadb` sang bản mới hơn (khác thế hệ schema) qua `deploy`/`reconfigure` thẳng, chưa migrate DB | Xem mục 9.1 ngay dưới — migrate tay hoặc chạy `icinga-ansible upgrade` |
| Cụm Galera kẹt `NON_PRIM` mãi không lên, `icingadb`/`icingaweb2` mất kết nối DB | Cụm Galera chết (không node nào sống) mà 1 node lại khởi động ở mode "join" thay vì bootstrap — hoặc `server.cnf` đổi trên nhiều node cùng lúc khiến Ansible restart cả cụm đồng thời | Chạy `mariadb-recovery -e recovery_mode=recover-cluster -e confirm=yes` (đọc `grastate.dat` mọi node, tự chọn node an toàn nhất để bootstrap lại, các node khác join qua IST — không mất data) |
| `deploy` fail ở bước khởi động container (`no_log`, output ẩn), thường trên host MỚI/vừa reset chưa từng pull image | Docker Hub rate-limit ẩn danh (`429 Too Many Requests`) — hay gặp khi nhiều host dùng chung 1 IP proxy ra ngoài | `docker login` (bằng tài khoản Docker Hub thật) trên host đang bị chặn, chạy `deploy` lại. Kiểm tra lỗi thật (vì bị `no_log` ẩn) bằng cách tự chạy tay `docker run --rm <image>` tương ứng để xem thông báo gốc |
| Đứng ở deployment node, chạy `deploy`/`reconfigure` KHÔNG `sudo` (đúng cách) mà vẫn lỗi không đọc được `globals.yml`/`passwords.yml` | `/etc/icinga-ansible` bị `root` sở hữu thay vì user thường — thường do LỠ chạy `init-config` (hoặc lệnh khác) qua `sudo` trước đó dù CLI đã cảnh báo | `sudo chown -R $(id -un):$(id -gn) /etc/icinga-ansible` — khớp đúng quyền `init-config` vốn định tạo (`0750`, owner = user thường), rồi chạy lại bình thường (không `sudo`) |

### 9.1. `icingadb` crash-loop vì lệch schema sau khi đổi version

Đây **không phải lỗi/mất dữ liệu** — `icingadb` cố ý từ chối khởi động khi thấy schema DB không
khớp version binary, để tránh chạy sai. Log luôn nêu rõ số hiện tại/kỳ vọng. 2 cách xử lý, **cả hai
đều đã test thật, đều an toàn**:

**Cách 1 — dùng lệnh `upgrade` có sẵn (khuyến nghị, tự làm hết các bước):**
```bash
./tools/icinga-ansible pull         -i ansible/inventory/my-cluster   # phải thành công trên mọi host
./tools/icinga-ansible upgrade-plan -i ansible/inventory/my-cluster   # xem trước, không đổi gì
./tools/icinga-ansible upgrade      -i ansible/inventory/my-cluster   # tự backup + migrate + redeploy
```

`upgrade-plan` đọc schema thật từ image đích nên yêu cầu image đã được `pull`. `upgrade` cũng kiểm
tra tất cả image cần thiết đã có trên đúng host trước khi tạo backup hoặc gây downtime.

**Cách 2 — tự migrate tay rồi restart** (đúng những gì lệnh `upgrade` làm ở bước migrate, chỉ khác
là bạn tự tay): tìm file SQL migrate ĐÚNG version trong
`ansible/roles/upgrade/files/icingadb-upgrades/<version>.sql` (nguồn chính thức từ
`github.com/Icinga/icingadb`, KHÔNG tự viết `ALTER TABLE` theo suy đoán — sai kiểu cột/ràng buộc có
thể qua được bước khởi động nhưng làm daemon chạy sai âm thầm về sau), áp thẳng vào DB rồi restart:
```bash
docker run --rm -i --network host mariadb:<tag> \
  mariadb -h <db_host> -P <db_port> -u<user> -p<mật_khẩu> icingadb \
  < ansible/roles/upgrade/files/icingadb-upgrades/<version>.sql

docker restart icingadb
```
Đã verify thật (2026-07-23): tái tạo đúng trạng thái lỗi, áp migrate tay, restart → `healthy` ngay,
không cần chạy nguyên lệnh `upgrade`. Chi tiết đầy đủ + log thật xem `design.md` mục 13.1.1.

> Version chỉ khác PATCH/MINOR mà KHÔNG đổi schema (vd `1.4.0`→`1.5.1`) thì `deploy`/`reconfigure`
> thẳng vẫn an toàn, không gặp lỗi này — chỉ khi đổi qua đúng ranh giới đổi schema mới cần 1 trong 2
> cách trên.

## 10. Đọc tiếp

- [`design.md`](design.md) — thiết kế đầy đủ: PKI/zone, HA, database, backup/upgrade, bảo mật,
  network/firewall (20 mục, dành cho khi cần hiểu SÂU cơ chế bên trong).
- [`TODO.md`](TODO.md) — trạng thái hiện tại của dự án, những gì đã verify chạy thật, bug đã gặp +
  cách đã fix (đọc trước khi sửa code, tránh lặp lại lỗi cũ đã biết).
- [`README.md`](README.md) — tóm tắt ngắn gọn cho người đã quen thuộc dự án.
