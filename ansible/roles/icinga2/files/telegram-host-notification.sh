#!/bin/bash
# telegram-host-notification.sh — gui Telegram khi Host doi trang thai.
# Tham so truyen vao qua NotificationCommand "telegram-host-notification"
# (xem templates/telegram-notifications.conf.j2) — KHONG hardcode bot_token/chat_id trong script,
# ca hai deu do Icinga2 truyen vao luc chay (tu passwords.yml qua Jinja, render trong .conf.j2).
#
# LICH SU (2026-07-24 -> 2026-07-28): xem giai thich day du trong telegram-service-notification.sh —
# bug notification gui TRUNG da duoc fix dung goc (dat apply-rule trong zones.d/master/), workaround
# check_source (-N/-C) khong con can, da go bo.
set -euo pipefail

BOT_TOKEN=""
CHAT_ID=""
LONGDATETIME=""
HOSTDISPLAYNAME=""
HOSTOUTPUT=""
HOSTADDRESS=""
HOSTSTATE=""
NOTIFICATIONTYPE=""

while getopts "t:c:d:l:n:o:4:s:y:" opt; do
  case "$opt" in
    t) BOT_TOKEN="$OPTARG" ;;
    c) CHAT_ID="$OPTARG" ;;
    d) LONGDATETIME="$OPTARG" ;;
    l) : ;;                        # HOSTNAME ($host.name$) - khong dung truc tiep, giu de tuong thich cau truc flag
    n) HOSTDISPLAYNAME="$OPTARG" ;;
    o) HOSTOUTPUT="$OPTARG" ;;
    4) HOSTADDRESS="$OPTARG" ;;
    s) HOSTSTATE="$OPTARG" ;;
    y) NOTIFICATIONTYPE="$OPTARG" ;;
    *) ;;
  esac
done

if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
  echo "UNKNOWN - thieu -t (bot_token) hoac -c (chat_id)"
  exit 3
fi

case "$HOSTSTATE" in
  UP)   ICON="✅" ;;
  DOWN) ICON="💔" ;;
  *)    ICON="❓" ;;
esac

TEXT=$(printf '%s %s - Host %s is %s\n\nHost: %s (%s)\nAddress: %s\nDate: %s\n\n```\n%s\n```' \
  "$ICON" "$NOTIFICATIONTYPE" "$HOSTDISPLAYNAME" "$HOSTSTATE" \
  "$HOSTDISPLAYNAME" "$HOSTSTATE" "$HOSTADDRESS" "$LONGDATETIME" "$HOSTOUTPUT")

curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "parse_mode=Markdown" \
  --data-urlencode "text=${TEXT}" \
  -o /dev/null -w 'telegram_http_status=%{http_code}\n'
