#!/bin/bash
# telegram-service-notification.sh — gui Telegram khi Service doi trang thai.
# Tham so truyen vao qua NotificationCommand "telegram-service-notification"
# (xem templates/telegram-notifications.conf.j2) — KHONG hardcode bot_token/chat_id trong script,
# ca hai deu do Icinga2 truyen vao luc chay (tu passwords.yml qua Jinja, render trong .conf.j2).
#
# LICH SU (2026-07-24 -> 2026-07-28): tung gap bug notification gui TRUNG (ca 1 node master lan 1
# node satellite cung gui) do cach dat file apply-rule khong dung (xem BUG NGHIEM TRONG trong
# roles/icinga2/tasks/main.yml, block "zones.d/master/telegram-notifications.conf"). Tung workaround
# tam bang cach so sanh check_source ngay trong script nay (-N/-C) — KHONG CON CAN NUA sau khi fix
# dung goc: dat file apply-rule CHINH TRONG zones.d/master/ (satellite khong con "thay" duoc object
# nay nua, khong the tu bau/gui trung). Da go bo logic check_source, script ve lai dang don gian.
set -euo pipefail

BOT_TOKEN=""
CHAT_ID=""
LONGDATETIME=""
HOSTDISPLAYNAME=""
SERVICEDISPLAYNAME=""
SERVICEOUTPUT=""
HOSTADDRESS=""
SERVICESTATE=""
NOTIFICATIONTYPE=""

while getopts "t:c:d:l:n:e:E:o:4:s:y:" opt; do
  case "$opt" in
    t) BOT_TOKEN="$OPTARG" ;;
    c) CHAT_ID="$OPTARG" ;;
    d) LONGDATETIME="$OPTARG" ;;
    l) : ;;                        # HOSTNAME ($host.name$) - khong dung truc tiep
    n) HOSTDISPLAYNAME="$OPTARG" ;;
    e) : ;;                        # SERVICENAME ($service.name$) - khong dung truc tiep
    E) SERVICEDISPLAYNAME="$OPTARG" ;;
    o) SERVICEOUTPUT="$OPTARG" ;;
    4) HOSTADDRESS="$OPTARG" ;;
    s) SERVICESTATE="$OPTARG" ;;
    y) NOTIFICATIONTYPE="$OPTARG" ;;
    *) ;;
  esac
done

if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
  echo "UNKNOWN - thieu -t (bot_token) hoac -c (chat_id)"
  exit 3
fi

case "$SERVICESTATE" in
  OK)       ICON="✅" ;;
  WARNING)  ICON="⚠️" ;;
  CRITICAL) ICON="💔" ;;
  *)        ICON="❓" ;;
esac

TEXT=$(printf '%s %s - %s on %s is %s\n\nHost: %s\nService: %s\nAddress: %s\nDate: %s\n\n```\n%s\n```' \
  "$ICON" "$NOTIFICATIONTYPE" "$SERVICEDISPLAYNAME" "$HOSTDISPLAYNAME" "$SERVICESTATE" \
  "$HOSTDISPLAYNAME" "$SERVICEDISPLAYNAME" "$HOSTADDRESS" "$LONGDATETIME" "$SERVICEOUTPUT")

curl --fail-with-body --silent --show-error --connect-timeout 10 --max-time 30 \
  -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "parse_mode=Markdown" \
  --data-urlencode "text=${TEXT}" \
  -o /dev/null -w 'telegram_http_status=%{http_code}\n'
