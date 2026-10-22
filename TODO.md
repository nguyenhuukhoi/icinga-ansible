# Giới hạn và việc còn lại

Các giới hạn hiện tại được giữ fail-fast hoặc ghi rõ, không giả vờ deploy thành công:

- role `[loadbalancer]` chưa hiện thực; dùng reverse proxy/LB Web do hệ thống ngoài quản lý;
- lệnh add/remove node chỉ quản lý endpoint Icinga, không tự thay membership Galera;
- đổi CA host hoặc `icinga_master_zone_name` cần runbook migration PKI riêng;
- external DB do DBA chịu trách nhiệm backup, schema migration và rollback;
- shellcheck là kiểm tra tuỳ chọn và bị skip nếu deployment node chưa cài.

Regression bắt buộc trước release: syntax-check, fresh destroy/deploy, reconfigure `changed=0`,
health-check 2 master + 3 Galera, add/remove master, add/remove satellite và kiểm tra Ansible không
chạm `zones.d`.
