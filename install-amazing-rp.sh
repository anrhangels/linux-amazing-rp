#!/usr/bin/env bash
# Amazing Online: one installation entry point. Run without sudo.
set -euo pipefail
amazing_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
arguments=("$@")
read_only=0; assume_yes=0; skip_packages=0
for ((i=0; i<${#arguments[@]}; i++)); do
 case "${arguments[i]}" in
  --check|--plan) read_only=1 ;;
  --yes) assume_yes=1 ;;
  --no-system-packages) skip_packages=1 ;;
  --no-shortcuts) ;;
  --prefix|--installer)
   if ((i+1 >= ${#arguments[@]})) || [[ "${arguments[i+1]}" == --* ]]; then printf 'У %s должно быть значение.\n' "${arguments[i]}" >&2; exit 2; fi
   i=$((i+1)) ;;
  -h|--help)
   cat <<'HELP'
AMAZING ONLINE / LINUX — установка игры и подготовка запуска
  bash install-amazing-rp.sh                 Подготовить компоненты, официальный лаунчер и ярлык
  bash install-amazing-rp.sh --check         Только проверить установку, ничего не менять
  bash install-amazing-rp.sh --plan          Только показать план
  bash install-amazing-rp.sh --yes           Подтвердить установку
  bash install-amazing-rp.sh --no-system-packages   Системные пакеты уже установлены
  bash install-amazing-rp.sh --prefix DIR    Отдельный каталог в ~/Games/amazing-rp/
  bash install-amazing-rp.sh --installer EXE Свой официальный установщик
  bash install-amazing-rp.sh --no-shortcuts  Подготовить отдельный тестовый профиль
После установки откройте Amazing RP или команду amazing. Клиент загрузит официальный лаунчер.
HELP
   exit 0 ;;
  *) printf 'Неизвестный параметр: %s. См. --help.\n' "${arguments[i]}" >&2; exit 2 ;;
 esac
done
if ((read_only)); then
 command -v python3 >/dev/null || { printf 'Для диагностики нужен Python 3.10+. Ничего не установлено.\n' >&2; exit 1; }
 exec python3 "$amazing_root/scripts/install_amazing.py" "$@"
fi
if ((EUID == 0)); then printf 'Запускайте без sudo. Права нужны только для системных пакетов.\n' >&2; exit 1; fi
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || { printf 'Требуется Linux x86_64.\n' >&2; exit 1; }
ID=unknown; ID_LIKE=''
if [[ -r /etc/os-release ]]; then source /etc/os-release; fi
family=''
for distro in "$ID" $ID_LIKE; do
 case "$distro" in
  arch|manjaro|cachyos|endeavouros) family=arch; break ;;
  debian|ubuntu|linuxmint|pop) family=debian; break ;;
  fedora|rhel) family=fedora; break ;;
  opensuse*|suse) family=opensuse; break ;;
 esac
done
if [[ -e /run/ostree-booted || "$ID" == steamos || "$ID" == nixos ]] && (( !skip_packages )); then
 printf 'Подготовьте зависимости средствами вашей ОС и добавьте --no-system-packages.\n' >&2; exit 1
fi
packages=()
case "$family" in
 arch) packages=(pacman -S --needed python flatpak libarchive fontconfig ttf-dejavu xorg-xrandr ca-certificates) ;;
 debian) packages=(apt-get install python3 flatpak libarchive-tools fontconfig fonts-dejavu-core x11-xserver-utils ca-certificates) ;;
 fedora) packages=(dnf install python3 flatpak bsdtar fontconfig dejavu-sans-fonts xrandr ca-certificates) ;;
 opensuse) packages=(zypper install python3 flatpak bsdtar fontconfig dejavu-fonts xrandr ca-certificates) ;;
 *) if (( !skip_packages )); then printf 'Установите Python 3, Flatpak, libarchive, Fontconfig и xrandr; повторите с --no-system-packages.\n' >&2; exit 1; fi ;;
esac
printf '\nAMAZING ONLINE / LINUX — установка игры\n'
printf 'Будут подготовлены Faugus, GE-Proton, .NET, VC++, DirectX, PowerShell, официальный лаунчер и совместимость.\n'
printf 'Данные существующей игры не очищаются. Клиент скачивается в официальном лаунчере.\n'
if (( !skip_packages )); then printf 'Системные пакеты: '; printf '%q ' "${packages[@]}"; printf '\n'; fi
if (( !assume_yes )); then
 [[ -t 0 ]] || { printf 'Для запуска без терминала добавьте --yes.\n' >&2; exit 1; }
 read -r -p 'Начать установку? [y/N] ' reply
 [[ "$reply" == y || "$reply" == Y || "$reply" == yes || "$reply" == 'да' ]] || exit 0
fi
if (( !skip_packages )); then
 command -v sudo >/dev/null || { printf 'Нужен sudo или --no-system-packages.\n' >&2; exit 1; }
 if [[ "$family" == debian ]]; then sudo apt-get update; fi
 if ((assume_yes)); then
  case "$family" in
   arch) packages+=(--noconfirm) ;;
   opensuse) packages=(zypper --non-interactive "${packages[@]:1}") ;;
   *) packages+=(-y) ;;
  esac
 fi
 sudo "${packages[@]}"
fi
command -v python3 >/dev/null || { printf 'Нужен Python 3.10+.\n' >&2; exit 1; }
exec python3 "$amazing_root/scripts/install_amazing.py" --yes "$@"
