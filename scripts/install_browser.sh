# scripts/install_browser.sh
#!/usr/bin/env bash
set -euo pipefail

echo "[install_browser] Installing Chrome and dependencies..."

# root 아니면 설치 스킵 (실패하지 않고 통과)
if [[ "${EUID}" -ne 0 ]]; then
  echo "[install_browser] Not running as root -> skip system install."
  echo "  If Chrome is missing, run: sudo ./scripts/install_browser.sh"
  exit 0
fi

# keyring(apt-key deprecate 대체)
install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/google-linux-signing-keyring.gpg ]]; then
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
    | gpg --dearmor -o /etc/apt/keyrings/google-linux-signing-keyring.gpg
  chmod 0644 /etc/apt/keyrings/google-linux-signing-keyring.gpg
fi

# repo 등록
if [[ ! -f /etc/apt/sources.list.d/google-chrome.list ]]; then
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-linux-signing-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    | tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
fi

apt-get update -qq
apt-get install -y -qq \
  google-chrome-stable \
  fonts-noto-cjk \
  libnss3 \
  libxss1 \
  libasound2 \
  unzip \
  xdg-utils

echo "[install_browser] Chrome installation complete."