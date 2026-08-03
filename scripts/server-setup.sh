#!/bin/sh
# Первичная настройка чистого Ubuntu 24.04 (Timeweb Cloud, 186.246.12.136).
# Запускать ОДИН РАЗ на сервере, из-под root (первый SSH-вход):
#   ssh root@186.246.12.136
#   curl -fsSL https://raw.githubusercontent.com/<ваш-репозиторий>/main/scripts/server-setup.sh -o server-setup.sh
#   sh server-setup.sh
# (или просто скопировать содержимое файла и вставить в консоль/веб-терминал Timeweb)
#
# Делает: обновление системы, Docker + compose plugin (офиц. репозиторий, не snap),
# ufw (22/80/443), fail2ban, sudo-пользователя с входом по SSH-ключу.
#
# ВАЖНО: скрипт НЕ отключает вход по паролю — сделайте это вручную ПОСЛЕ того,
# как проверили, что вход по SSH-ключу под новым пользователем работает.
# Если что-то пойдёт не так — аварийный доступ есть через веб-консоль в панели
# Timeweb (работает даже без SSH).
set -eu

NEW_USER="${1:-deploy}"

echo "==> Обновление системы"
apt update && apt upgrade -y

echo "==> Установка Docker (официальный репозиторий, НЕ snap)"
apt install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

echo "==> ufw: разрешаем только 22, 80, 443"
apt install -y ufw
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> fail2ban для SSH"
apt install -y fail2ban
systemctl enable --now fail2ban

echo "==> Пользователь с sudo: $NEW_USER"
if ! id "$NEW_USER" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "$NEW_USER"
    usermod -aG sudo,docker "$NEW_USER"
fi

mkdir -p "/home/$NEW_USER/.ssh"
echo "Вставь публичный SSH-ключ (одну строку, начинается с ssh-ed25519 или ssh-rsa) и нажми Enter:"
read -r PUBKEY
echo "$PUBKEY" >> "/home/$NEW_USER/.ssh/authorized_keys"
chmod 700 "/home/$NEW_USER/.ssh"
chmod 600 "/home/$NEW_USER/.ssh/authorized_keys"
chown -R "$NEW_USER:$NEW_USER" "/home/$NEW_USER/.ssh"

echo
echo "==> Готово. ПЕРЕД тем как отключать вход по паролю:"
echo "    1. Открой НОВУЮ сессию: ssh $NEW_USER@186.246.12.136"
echo "    2. Убедись, что вход по ключу работает и есть sudo/docker без пароля к группе"
echo "    3. Только после этого правь /etc/ssh/sshd_config (PasswordAuthentication no) и перезапусти sshd"
echo "    Аварийный доступ, если что-то сломается: веб-консоль в панели Timeweb Cloud."
