#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

sudo apt update
sudo apt install -y python3 python3-tk libnotify-bin xdg-utils

chmod +x "$DIR/study_timer.py"

# Ярлык в меню приложений
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/zoom-auto.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Zoom Auto
Comment=Автоматический заход на пары в Zoom
Exec=python3 $DIR/study_timer.py
Icon=camera-video-symbolic
Terminal=false
Categories=Utility;
EOF

# Автозапуск при входе в систему (свёрнутым)
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/zoom-auto.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Zoom Auto
Exec=python3 $DIR/study_timer.py --hidden
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=10
Terminal=false
EOF

echo "Готово! Перезайди в систему или запусти: python3 $DIR/study_timer.py"
