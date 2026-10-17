# Deploy Icinga2 — 2 master (HA) + 3 Galera + 1 deployment node (step by step)

Hướng dẫn tái lập đúng cụm Icinga đã build và verify chạy thật trong lab này (2026-09-12/13), qua
Terraform (provision VM) + `icinga-ansible` (deploy Icinga2). Toàn bộ lệnh dưới đây đã chạy thật ít
nhất 1 lần trong lab, kể cả 2 bug thật đã gặp (ghi ở mục Troubleshooting).

## 0. Kiến trúc

```
icinga-deploy (chỉ chạy Ansible CLI, KHÔNG chạy icinga2/mariadb)
    │ SSH key riêng (Terraform tự sinh + tự copy)
    ├── icinga-master1 ─┐
    ├── icinga-master2 ─┴─ HA active/active, cùng zone "master"
    ├── icinga-galera1 ─┐
    ├── icinga-galera2 ─┼─ Galera cluster thật (wsrep), DB cho icingadb
    └── icinga-galera3 ─┘
```

6 VM trên network OpenStack `vlan2019` (external+shared, DHCP, **không cần floating IP** — trunk
trực tiếp tới máy quản trị này nên SSH/HTTP thẳng, không cần jump host).

## 1. Yêu cầu trước (đã có sẵn trong lab này)

Kiểm tra các resource sau đã tồn tại trên OpenStack trước khi chạy Terraform (nếu môi trường khác,
tạo tương đương rồi sửa `variables.tf`):

```bash
openstack flavor show monitoring.icinga        # 2 vCPU / 4096MB / 40GB
openstack network show vlan2019                # external+shared, DHCP
openstack security group show monitoring-lab-sg
openstack image show Ubuntu-24.04
```

Nếu chưa có, tạo nhanh (đổi CIDR/rule theo nhu cầu thật):

```bash
openstack flavor create --vcpus 2 --ram 4096 --disk 40 --public monitoring.icinga
openstack security group create monitoring-lab-sg
openstack security group rule create monitoring-lab-sg --protocol tcp --dst-port 22 --remote-ip <admin-cidr> --ingress
openstack security group rule create monitoring-lab-sg --protocol icmp --remote-ip <admin-cidr> --ingress
openstack security group rule create monitoring-lab-sg --protocol any --remote-group monitoring-lab-sg --ingress
```

## 2. Deploy 6 VM bằng Terraform

Chạy được từ máy quản trị NẾU máy đó tới thẳng `registry.terraform.io` — nếu không (như máy Windows
lab này), chạy Terraform **từ 1 VM trong cùng network** đã có proxy hoạt động (vd copy thư mục
`terraform/` sang 1 VM sẵn có rồi chạy ở đó qua SSH).

```bash
cd icinga-ansible/terraform

# nếu cần proxy để tải provider (không có đường ra internet trực tiếp)
export http_proxy=http://<proxy>:80
export https_proxy=http://<proxy>:80

terraform init
export TF_VAR_password="<mật khẩu OpenStack admin>"
terraform plan      # xem trước 9 resource (6 VM + keypair + tls_private_key + local_file)
terraform apply -auto-approve
```

Kết quả mong đợi: `Apply complete! Resources: 9 added`. Lấy IP:

```bash
terraform output master_ips
terraform output galera_ips
terraform output deploy_ip
```

File `../ansible/inventory/multinode` được **tự sinh** với đúng IP — không cần sửa tay.

## 3. Verify SSH từ deployment node ra 5 node kia

```bash
# lấy private key Terraform sinh ra (chỉ nên chạy trên chính máy/VM vừa apply, tránh chép lung tung)
terraform output -raw private_key_pem > /tmp/icinga-key
chmod 600 /tmp/icinga-key

ssh -i /tmp/icinga-key ubuntu@<deploy_ip> "
  for ip in <master1_ip> <master2_ip> <galera1_ip> <galera2_ip> <galera3_ip>; do
    ssh \$ip hostname
  done
"
```

Nếu thấy đủ 5 hostname (không lỗi `Permission denied`/`Host key verification failed`) — key và
inventory đã đúng, sang bước 4.

## 4. Copy repo `icinga-ansible` + cài Ansible trên deployment node

```bash
scp -r -i /tmp/icinga-key icinga-ansible ubuntu@<deploy_ip>:/tmp/icinga-ansible
ssh -i /tmp/icinga-key ubuntu@<deploy_ip> '
  sudo mkdir -p /opt/icinga-ansible
  sudo cp -r /tmp/icinga-ansible/* /opt/icinga-ansible/
  sudo chown -R ubuntu:ubuntu /opt/icinga-ansible

  # apt/docker cần proxy nếu VM không có đường ra internet trực tiếp
  sudo mkdir -p /etc/apt/apt.conf.d
  echo "Acquire::http::Proxy \"http://<proxy>:80\";"  | sudo tee    /etc/apt/apt.conf.d/95proxy
  echo "Acquire::https::Proxy \"http://<proxy>:80\";" | sudo tee -a /etc/apt/apt.conf.d/95proxy
  export http_proxy=http://<proxy>:80 https_proxy=http://<proxy>:80
  sudo -E apt update -qq
  sudo -E apt install -y -qq python3-venv

  cd /opt/icinga-ansible
  python3 -m venv "$HOME/venvs/icinga-ansible"
  source "$HOME/venvs/icinga-ansible/bin/activate"
  python -m pip install -U pip
  python -m pip install ansible
  ansible-galaxy collection install -r ansible/requirements.yml
'
```

## 5. Khởi tạo cấu hình + proxy cho Docker (nếu cần)

```bash
ssh -i /tmp/icinga-key ubuntu@<deploy_ip> '
  cd /opt/icinga-ansible
  source "$HOME/venvs/icinga-ansible/bin/activate"
  ./tools/icinga-ansible init-config
  ./tools/icinga-ansible genpwd

  sudo sed -i \
    -e "s|^proxy_http:.*|proxy_http:  \"http://<proxy>:80\"|" \
    -e "s|^proxy_https:.*|proxy_https: \"http://<proxy>:80\"|" \
    -e "s|^proxy_no_proxy:.*|proxy_no_proxy: \"localhost,127.0.0.1,::1,<subnet-lab>/24\"|" \
    /etc/icinga-ansible/globals.yml
'
```

## 6. bootstrap-servers → prechecks → deploy → post-deploy

```bash
ssh -i /tmp/icinga-key ubuntu@<deploy_ip> '
  cd /opt/icinga-ansible
  source "$HOME/venvs/icinga-ansible/bin/activate"
  ./tools/icinga-ansible bootstrap-servers -i multinode
  ./tools/icinga-ansible prechecks -i multinode
  ./tools/icinga-ansible deploy -i multinode
  ./tools/icinga-ansible post-deploy -i multinode
'
```

Kỳ vọng: `failed=0` cả 5 host (`master1/2`, `galera1/2/3`), precheck suy ra đúng `Master: 2 (HA)`
và `Database: managed_db (galera nodes: 3)`. `deploy` chạy lâu vài phút vì bootstrap Galera thật.
`post-deploy` in URL cùng user đăng nhập Icinga Web 2.

## 7. Verify sau deploy

```bash
# container health trên từng master
ssh -i /tmp/icinga-key ubuntu@<master1_ip> 'sudo docker ps --format "{{.Names}}: {{.Status}}"'
# kỳ vọng: icinga2/icingadb/icingadb-redis/icingaweb2 đều "healthy"

# Galera health trên từng node
ssh -i /tmp/icinga-key ubuntu@<galera1_ip> 'sudo docker ps --filter name=mariadb --format "{{.Status}}"'
# kỳ vọng: "healthy" trên cả 3 node

# login web (từ máy quản trị, cần trunk trực tiếp hoặc port-forward qua SSH)
curl -s -o /dev/null -w "%{http_code}\n" http://<master1_ip>:8080/authentication/login
# 302 là bình thường (redirect sang trang login)
```

Mật khẩu admin nằm trong `/etc/icinga-ansible/passwords.yml` trên `icinga-deploy`
(`icingaweb2_admin_password`).

## 8. Troubleshooting — 2 bug thật đã gặp trong lab này

### 8.1. Galera cluster rơi về NON-PRIMARY khi `deploy` (race condition)

**Triệu chứng**: `deploy` fail ở bước "Chờ MariaDB sẵn sàng" cho cả 3 node Galera, log
`no bootstrapped primary component found`, `quorum: members = 0/3`.

**Nguyên nhân**: khi Ansible gỡ cờ `--wsrep-new-cluster` khỏi node đầu (sau khi cluster hình thành
lần đầu) để tái tạo container, nếu đúng lúc đó 2 node còn lại CŨNG đang ở giữa chu trình
start/join container của chính chúng, cả 3 container gần như cùng lúc không node nào giữ được
"primary component" đã từng tồn tại → toàn bộ cluster khoá an toàn (chống split-brain), không phải
mất dữ liệu.

**Cách xử lý** (thử theo thứ tự, dừng ngay khi qua được bước nào):
1. **Retry `deploy` lại từ đầu** (idempotent, không phá dữ liệu) — trong lab này, lần 2 chạy y hệt
   code đã **thành công `failed=0`** ngay, không cần sửa gì — nhiều khả năng do timing ngẫu nhiên
   giữa các lần chạy (tốc độ SSH/docker start), không phải lỗi cấu hình cố định.
2. Nếu retry vẫn NON-PRIMARY: dùng playbook chính thức của repo
   `./tools/icinga-ansible mariadb-recovery -i multinode -e recovery_mode=recover-cluster -e confirm=yes`
   — playbook này tự tìm node có `safe_to_bootstrap:1` trong `grastate.dat` để bootstrap lại.
   **Lưu ý**: playbook này có thể tự nó lỗi (Jinja "None has no element 0") nếu CẢ 3 node đều
   `safe_to_bootstrap:0` (crash gần đồng thời, chưa node nào ghi seqno hợp lệ) — nếu gặp đúng
   trường hợp này, chỉ còn cách 3 dưới đây.
3. Dừng + xoá container + xoá sạch datadir trên cả 3 node Galera (**chỉ làm khi CHẮC CHẮN dữ liệu
   hiện tại chưa có gì thật**, vd cụm mới build lần đầu), rồi `deploy` lại từ đầu:
   ```bash
   ssh -i /tmp/icinga-key ubuntu@<galera-ip> '
     sudo docker stop mariadb && sudo docker rm mariadb
     sudo rm -rf /var/lib/icinga-ansible/mariadb/data/*
   '
   # lặp lại cho cả 3 node, rồi:
   ./tools/icinga-ansible deploy -i multinode
   ```

### 8.2. (Chỉ áp dụng nếu dùng Terraform ở bước 2) cloud-init `write_files` fail "Unknown user ubuntu"

**Triệu chứng**: sau `terraform apply`, SSH vào `icinga-deploy` không thấy
`~/.ssh/id_ed25519`/`~/.ssh/config` dù `user_data` có khai `write_files`. `cloud-init status --long`
báo lỗi `write_files ... Unknown user or group: getpwnam(): name not found: 'ubuntu'`.

**Nguyên nhân**: `write_files` chạy ở stage "init", **trước khi** module tạo user `ubuntu` chạy
xong trên image Ubuntu 24.04 dùng ở lab này — khai thẳng `owner: ubuntu:ubuntu` trong
`write_files` bị lỗi âm thầm (không phải lỗi permission dễ đoán).

**Fix** (đã sửa trong `terraform/templates/deploy-init.yaml.tpl`, không cần làm lại nếu dùng đúng
code hiện tại trong repo): ghi file bằng owner mặc định (root), chuyển `chown`/`chmod` sang
`runcmd` (chạy ở stage "config"/cuối, lúc đó user `ubuntu` chắc chắn đã tồn tại). Nếu tự sửa
template khác, nhớ đợi `cloud-init status --wait` xong hẳn trước khi test SSH — `runcmd` chạy sau
cả `write_files`, cần thêm 10-40s sau khi VM báo `ACTIVE`.

## 9. Bước tiếp theo (không nằm trong hướng dẫn deploy cơ bản)

- Thêm Host/Service monitor cho hạ tầng OpenStack/Ceph thật — xem `monitoring/README.md`.
- Business Process / Dependency demo — xem `ICINGA-LAB-2026-09-12.md` mục 4 (đợt build trước, dùng
  inventory `my-cluster` thay vì `multinode`, cùng quy trình).
