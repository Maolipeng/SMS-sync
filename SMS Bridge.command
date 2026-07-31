#!/bin/zsh

# Double-click launcher for non-technical macOS users.
# It never reads a .env file and never places credentials in process arguments.

set -u
umask 077

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1
RUNTIME_DIR="$HOME/Library/Application Support/SMS Bridge/runtime"
RUNTIME_PYTHON="$RUNTIME_DIR/bin/python3"
RUNTIME_MARKER="$RUNTIME_DIR/.sms-bridge-runtime-v1"

find_python() {
  local candidate version_ok
  for candidate in \
    "$HOME/.pyenv/shims/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "/usr/bin/python3"
  do
    if [[ -x "$candidate" ]]; then
      version_ok="$("$candidate" -c 'import sys; print(int(sys.version_info >= (3, 10)))' 2>/dev/null)"
      if [[ "$version_ok" == "1" ]]; then
        print -r -- "$candidate"
        return 0
      fi
    fi
  done
  if command -v python3 >/dev/null 2>&1; then
    candidate="$(command -v python3)"
    version_ok="$("$candidate" -c 'import sys; print(int(sys.version_info >= (3, 10)))' 2>/dev/null)"
    if [[ "$version_ok" == "1" ]]; then
      print -r -- "$candidate"
      return 0
    fi
  fi
  return 1
}

BASE_PYTHON="$(find_python)" || {
  print ""
  print "SMS Bridge 需要 Python 3.10 或更高版本。"
  print "SMS Bridge requires Python 3.10 or newer."
  print ""
  print "请先从 https://www.python.org/downloads/macos/ 安装 Python，然后重新双击此文件。"
  print "Install Python from the URL above, then double-click this file again."
  print ""
  read -r "?按回车键关闭 / Press Return to close: "
  exit 1
}
BASE_PYTHON="$("$BASE_PYTHON" -c 'import os,sys; print(os.path.realpath(sys.executable))')"

create_dedicated_runtime() (
  local build_dir real_python version_name temporary_binary link_name
  build_dir="$RUNTIME_DIR.build.$$"
  trap '[[ -n "${build_dir:-}" ]] && "$BASE_PYTHON" -c '\''import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)'\'' "$build_dir"' EXIT
  "$BASE_PYTHON" -c 'import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)' "$build_dir"
  mkdir -p "${RUNTIME_DIR:h}"
  "$BASE_PYTHON" -m venv --without-pip "$build_dir" || return 1
  real_python="$("$BASE_PYTHON" -c 'import os,sys; print(os.path.realpath(sys.executable))')" || return 1
  version_name="$("$BASE_PYTHON" -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}")')" || return 1
  temporary_binary="$build_dir/bin/$version_name.sms-bridge-new"
  /bin/cp "$real_python" "$temporary_binary" || return 1
  /bin/chmod 700 "$temporary_binary" || return 1
  if [[ -e "$build_dir/bin/$version_name" || -L "$build_dir/bin/$version_name" ]]; then
    /bin/unlink "$build_dir/bin/$version_name" || return 1
  fi
  /bin/mv "$temporary_binary" "$build_dir/bin/$version_name" || return 1
  for link_name in python python3; do
    if [[ -e "$build_dir/bin/$link_name" || -L "$build_dir/bin/$link_name" ]]; then
      /bin/unlink "$build_dir/bin/$link_name" || return 1
    fi
    /bin/ln -s "$version_name" "$build_dir/bin/$link_name" || return 1
  done
  print -r -- "SMS Bridge dedicated runtime v1" > "$build_dir/.sms-bridge-runtime-v1"
  "$build_dir/bin/python3" -c \
    'import ctypes, os, sqlite3, sys; assert os.path.realpath(sys.executable).startswith(sys.prefix + os.sep)' \
    || return 1
  "$BASE_PYTHON" -c 'import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)' "$RUNTIME_DIR"
  /bin/mv "$build_dir" "$RUNTIME_DIR" || return 1
  build_dir=""
)

runtime_is_dedicated() {
  local executable
  [[ -x "$RUNTIME_PYTHON" && -f "$RUNTIME_MARKER" ]] || return 1
  executable="$("$RUNTIME_PYTHON" -c 'import os,sys; print(os.path.realpath(sys.executable))' 2>/dev/null)" || return 1
  [[ "$executable" == "$RUNTIME_DIR/bin/"* && ! -L "$executable" ]]
}

if ! runtime_is_dedicated; then
  print "正在创建 SMS Bridge 专用运行环境…"
  print "Creating a dedicated SMS Bridge runtime…"
  create_dedicated_runtime || {
    print ""
    print "无法创建专用运行环境，请查看 docs/USER_GUIDE.zh-CN.md。"
    print "Could not create the dedicated runtime. See docs/USER_GUIDE.en.md."
    read -r "?按回车键关闭 / Press Return to close: "
    exit 1
  }
fi

exec "$RUNTIME_PYTHON" "$SCRIPT_DIR/sms_bridge.py" ui
