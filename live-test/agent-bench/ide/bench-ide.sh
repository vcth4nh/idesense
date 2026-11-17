#!/usr/bin/env bash
# Start, stop and examine one dedicated benchmark IDE instance (GoLand or PyCharm) in serverMode.
# The instance has its own config, system, plugins and log folders below BENCH/ide/<ide>/ and its
# own MCP port, so that it never reaches an IDE of the fleet (ports 29170 to 29178).
# The launch follows ~/.local/opt/x11-userland/bin/ide-gui-throwaway.
#
# Usage: bench-ide.sh start|prepare|dry-run <goland|pycharm> <project dir>...
#        bench-ide.sh stop|status <goland|pycharm>
#   start writes options/recentProjects.xml with the project dirs marked as open and launches a bare
#   serverMode: that start opens each project of the file (live-test/fleet.py does the same).
#   prepare does each step of start before the launch (for the tests). dry-run does each check of
#   start and prints what start would do. It makes no folder, copies nothing and starts nothing.
# Environment:
#   BENCH_ROOT        the data root (default /home/ubuntu/dev/idesense-bench). Each project dir must be
#                     below BENCH_ROOT/trees/, each folder of the instance below BENCH_ROOT/ide/.
#   BENCH_APPS        the Toolbox apps folder (default /home/ubuntu/.local/share/JetBrains/Toolbox/apps)
#   BENCH_PLUGIN_ZIP  the IdeSense distribution zip that start unpacks into the plugins folder
#   BENCH_PORT        for the tests only: each port other than the port of the IDE is refused
set -euo pipefail

BENCH_ROOT="${BENCH_ROOT:-/home/ubuntu/dev/idesense-bench}"
BENCH_APPS="${BENCH_APPS:-/home/ubuntu/.local/share/JetBrains/Toolbox/apps}"
KEYS=(config system plugins log)

die() { echo "bench-ide: $*" >&2; exit 1; }
usage() { die "usage: bench-ide.sh start|prepare|dry-run <goland|pycharm> <project dir>... | stop|status <goland|pycharm>"; }

[ "$#" -ge 2 ] || usage
cmd="$1"; ide="$2"; shift 2
case "$cmd" in start|prepare|dry-run|stop|status) ;; *) usage ;; esac
case "$ide" in
  goland) ide_port=29374 ;;
  pycharm) ide_port=29372 ;;
  *) usage ;;
esac

# --- Port: the first check of each command, before any call or change.
port="${BENCH_PORT:-$ide_port}"
[[ "$port" =~ ^[0-9]+$ ]] || die "port '$port' is not a number: refused"
# A second rule, hard-coded: the ports of the fleet are refused, whatever the variables say.
if [ "$port" -ge 29170 ] && [ "$port" -le 29178 ]; then die "port $port is a fleet port (29170 to 29178): refused"; fi
[ "$port" = "$ide_port" ] || die "port $port is not the port of $ide ($ide_port): refused"
URL="http://127.0.0.1:$port/mcp/streamable-http"

# --- The four folders of the instance: below BENCH_ROOT/ide/, no symbolic link, 60 characters or fewer
# (unix socket paths below the system folder must stay below the limit of 108).
root="$(realpath -m -- "$BENCH_ROOT")"
IDE_DIR="$root/ide/$ide"
declare -A P
for k in "${KEYS[@]}"; do
  p="$IDE_DIR/$k"
  r="$(realpath -m -- "$p")"
  case "$r" in "$root/ide/"?*) ;; *) die "path $p resolves to $r, which is not below $root/ide/: refused" ;; esac
  [ "$r" = "$p" ] || die "path $p resolves to $r through a symbolic link: refused"
  [ "${#r}" -le 60 ] || die "path $r has ${#r} characters, more than 60: refused"
  P[$k]="$r"
done
VMO="$IDE_DIR/ide.vmoptions"
PIDF="$IDE_DIR/pid"
LAUNCH_OUT="$IDE_DIR/launch.out"
MCP_XML="${P[config]}/options/mcp-plugin.xml"

# --- Process helpers. A signal goes only to a pid that one of the two ours_by_* checks accepts.
alive() {  # $1 = pid; a zombie does not count
  local st
  st="$(sed -n 's/^.*) \(.\).*$/\1/p' "/proc/$1/stat" 2>/dev/null)" || return 1
  [ -n "$st" ] && [ "$st" != Z ] && [ "$st" != X ]
}
ours_by_cmdline() {
  # $1 = pid. Its command line names a folder of this instance (the java with its -Didea.*.path options).
  local a
  a="$(tr '\0' '\n' < "/proc/$1/cmdline" 2>/dev/null)" || return 1
  grep -Fq -- "$IDE_DIR/" <<<"$a"
}
ours_by_launch() {
  # $1 = pid of the tree that this start launched (the caller walks only that tree); for the guard after
  # the launch only. A java that ignored the path options has no folder of the instance in its command
  # line. Then the marks are the last argument (serverMode) and, the strong mark, the VM options variable
  # of this launch in the environment, which exec keeps.
  local a e
  a="$(tr '\0' '\n' < "/proc/$1/cmdline" 2>/dev/null)" || return 1
  e="$(tr '\0' '\n' < "/proc/$1/environ" 2>/dev/null)" || return 1
  [ "$(tail -n 1 <<<"$a")" = serverMode ] && grep -Fxq -- "$envvar=$VMO" <<<"$e"
}
tree_pids() {  # $1 and its descendants, by the parent links of the process table (no search by name)
  local c
  echo "$1"
  for c in $(ps -o pid= --ppid "$1" 2>/dev/null || true); do tree_pids "$c"; done
}

# --- The options file and the check of the path options (for the file and for the java command line).
path_lines() { local k; for k in "${KEYS[@]}"; do printf -- '-Didea.%s.path=%s\n' "$k" "${P[$k]}"; done; }
check_path_args() {
  # stdin: one argument on each line. Each -Didea.<key>.path= occurs one time, with the folder of this instance.
  local text k
  text="$(cat)"
  for k in "${KEYS[@]}"; do
    [ "$(grep -c -- "^-Didea\.$k\.path=" <<<"$text" || true)" = 1 ] || return 1
    grep -Fxq -- "-Didea.$k.path=${P[$k]}" <<<"$text" || return 1
  done
}

# --- MCP calls (only after the port checks above).
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
mcp_post() { curl -sS -m 10 -X POST -H 'Content-Type: application/json' --data "$1" "$URL"; }
version_of() { python3 -I -c 'import json,sys; print(json.load(sys.stdin)["result"]["serverInfo"]["version"])'; }
open_projects() {
  # Prints "<path><TAB><name>" for each open project. The server lists them in the error of a call
  # with an unknown project_path; an entry with "workspace" is a module folder, not a project
  # (as open_projects of live-test/fleet.py). Fails when the answer has no list.
  local call='{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ide_index_status","arguments":{"project_path":"/bench-ide-status/no-such-project"}}}'
  mcp_post "$call" 2>/dev/null | python3 -I -c '
import json, sys
r = json.load(sys.stdin).get("result") or {}
p = r.get("structuredContent")
if not isinstance(p, dict):
    p = json.loads((r.get("content") or [{}])[0].get("text", ""))
for e in p["available_projects"]:
    if "workspace" not in e:
        print("%s\t%s" % (e["path"], e.get("name")))
' 2>/dev/null
}

pid_file_pid() {  # prints the pid of the pid file, or nothing when there is no pid file
  [ -f "$PIDF" ] || return 0
  local pid
  pid="$(cat "$PIDF")"
  [[ "$pid" =~ ^[0-9]+$ ]] || die "pid file $PIDF holds no pid"
  echo "$pid"
}

# --- stop and status
if [ "$cmd" = stop ]; then
  pid="$(pid_file_pid)"
  [ -n "$pid" ] || { echo "no pid file $PIDF: nothing to stop"; exit 0; }
  if ! alive "$pid"; then rm -f "$PIDF"; echo "pid $pid does not run: pid file removed"; exit 0; fi
  ours_by_cmdline "$pid" || die "the command line of pid $pid does not name $IDE_DIR/: no signal sent (stale pid file?)"
  echo "SIGTERM to pid $pid"
  ours_by_cmdline "$pid" && kill -TERM "$pid" || true
  for _ in $(seq 1 60); do alive "$pid" || break; sleep 1; done
  if alive "$pid"; then
    echo "pid $pid still runs after 60 s: SIGKILL to pid $pid"
    ours_by_cmdline "$pid" && kill -KILL "$pid" || true
    for _ in $(seq 1 10); do alive "$pid" || break; sleep 1; done
  fi
  alive "$pid" && die "pid $pid still runs"
  rm -f "$PIDF"
  echo "stopped pid $pid"
  exit 0
fi

if [ "$cmd" = status ]; then
  pid="$(pid_file_pid)"
  if [ -z "$pid" ]; then state="no pid file"
  elif ! alive "$pid"; then state="does not run"
  elif ours_by_cmdline "$pid"; then state="runs"
  else state="runs, but its command line does not name $IDE_DIR/ (stale pid file)"; fi
  echo "pid:                ${pid:--} ($state)"
  echo "port:               $port ($URL)"
  v="$(mcp_post "$INIT" 2>/dev/null | version_of 2>/dev/null)" || v=""
  if [ -z "$v" ]; then echo "serverInfo.version: no answer"; exit 1; fi
  echo "serverInfo.version: $v"
  if open="$(open_projects)"; then
    echo "open projects:      $(grep -c . <<<"$open" || true)"
    [ -z "$open" ] || sed 's/^\([^\t]*\)\t\(.*\)$/  \2  \1/' <<<"$open"
  else
    echo "open projects:      unknown (the answer has no list)"
  fi
  exit 0
fi

# --- start, prepare and dry-run: the checks before the launch
[ "$#" -ge 1 ] || die "give one project dir or more, below $root/trees/"
PROJECTS=()
for p in "$@"; do
  r="$(realpath -e -- "$p" 2>/dev/null)" || die "project dir $p does not exist: refused"
  [ -d "$r" ] || die "project dir $r is not a folder: refused"
  case "$r" in "$root/trees/"?*) ;; *) die "project dir $r is not below $root/trees/: refused" ;; esac
  PROJECTS+=("$r")
done
# rewrite_recent_projects and trust_project_paths of the fleet harness write the two project files.
FLEET_PY="$(realpath -m -- "$(dirname -- "$(realpath -- "$0")")/../../fleet.py")"
[ -f "$FLEET_PY" ] || die "no $FLEET_PY"

APP="$BENCH_APPS/$ide"
LAUNCHER="$APP/bin/$ide.sh"
BASE_VMO="$APP/bin/${ide}64.vmoptions"
[ -f "$LAUNCHER" ] || die "no launcher $LAUNCHER"
[ -f "$BASE_VMO" ] || die "no options file $BASE_VMO"
data="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["dataDirectoryName"])' "$APP/product-info.json")" \
  || die "no dataDirectoryName in $APP/product-info.json"
[[ "$data" =~ ^[A-Za-z][A-Za-z0-9.]*$ ]] || die "data folder name '$data' is not a plain name"
# The name of the variable comes from the launcher text (WebStorm reads WEBIDE_VM_OPTIONS, not WEBSTORM_VM_OPTIONS).
names="$(grep -o '\$[A-Z][A-Z_]*_VM_OPTIONS' "$LAUNCHER" | grep -v 'USER_VM_OPTIONS' | tr -d '$' | sort -u || true)"
[ -n "$names" ] || die "no *_VM_OPTIONS variable in $LAUNCHER: refused"
[ "$(wc -l <<<"$names")" = 1 ] || die "more than one *_VM_OPTIONS variable in $LAUNCHER: $(echo $names): refused"
envvar="$names"

CONFIG_SRC="$HOME/.config/JetBrains/$data"
PLUGIN_SRC="$HOME/.local/share/JetBrains/$data"
FLEET_PLUGINS=()
for d in "$PLUGIN_SRC"/*/; do
  [ -d "$d" ] || continue
  d="${d%/}"
  [ "${d##*/}" = idesense ] || FLEET_PLUGINS+=("$d")
done

listening="$(ss -Hltn "sport = :$port")" || die "ss failed"
[ -z "$listening" ] || die "a process already listens on port $port: refused"
pid="$(pid_file_pid)"
if [ -n "$pid" ] && alive "$pid"; then
  die "pid file $PIDF names the live process $pid: refused (bench-ide.sh stop $ide)"
fi
if [ -d "${P[config]}" ]; then
  grep -Eq "name=\"serverPort\" value=\"$port\"" "$MCP_XML" 2>/dev/null \
    || die "$MCP_XML does not set serverPort $port: refused"
fi
vmo_text() { cat "$BASE_VMO"; [ -z "$(tail -c 1 "$BASE_VMO")" ] || echo; path_lines; }
vmo_text | check_path_args || die "the options text for $VMO does not have the four path options exactly one time: refused"

zip="${BENCH_PLUGIN_ZIP:-}"
LAUNCH=(env "$envvar=$VMO" nohup "$LAUNCHER" serverMode)

if [ "$cmd" = dry-run ]; then
  echo "dry-run $ide: the checks passed. Nothing was made, copied or started."
  echo "launcher:       $LAUNCHER"
  echo "variable:       $envvar"
  echo "data folder:    $data"
  echo "vmoptions:      $VMO (a copy of $BASE_VMO and these lines)"
  path_lines | sed 's/^/  /'
  echo "port:           $port (nothing listens; $URL)"
  echo "pid file:       $PIDF"
  if [ -d "${P[config]}" ]; then
    echo "config:         ${P[config]} exists (serverPort $port); start keeps it"
  else
    echo "config:         ${P[config]} is absent; start copies $CONFIG_SRC,"
    echo "                removes .lock and options/recentProjects.xml, and writes options/trusted-paths.xml"
    echo "                ($root/trees) and options/mcp-plugin.xml (serverPort $port only)"
  fi
  if [ -n "$zip" ] && [ -f "$zip" ]; then
    echo "plugin zip:     $zip (present; start unpacks it into ${P[plugins]})"
  else
    echo "plugin zip:     ${zip:-BENCH_PLUGIN_ZIP is not set} is absent: start refuses"
  fi
  echo "plugin copies:  ${#FLEET_PLUGINS[@]} folder(s) into ${P[plugins]}"
  for d in "${FLEET_PLUGINS[@]}"; do echo "  $d"; done
  echo "project dirs:   start writes ${P[config]}/options/recentProjects.xml new with these dirs"
  echo "                (each entry opened=\"true\" with a frame element) and adds a trust entry for each"
  echo "                to options/trusted-paths.xml:"
  for d in "${PROJECTS[@]}"; do echo "  $d"; done
  printf 'command:        '; printf '%q ' "${LAUNCH[@]}"; printf '> %q 2>&1 < /dev/null &\n' "$LAUNCH_OUT"
  exit 0
fi

# --- start and prepare: prepare the folders (the IDE is down: the checks above found no listener and no live pid)
[ -n "$zip" ] && [ -f "$zip" ] || die "no plugin zip '${zip}': set BENCH_PLUGIN_ZIP to the IdeSense distribution zip"
command -v curl >/dev/null || die "no curl"
mkdir -p "${P[system]}" "${P[log]}"
if [ ! -d "${P[config]}" ]; then
  [ -d "$CONFIG_SRC" ] || die "no fleet config folder $CONFIG_SRC to copy"
  seed="$IDE_DIR/config.seed"
  rm -rf -- "$seed"
  mkdir -p "$seed"
  cp -a "$CONFIG_SRC/." "$seed/"                    # a read of the fleet config, never a write there
  rm -f "$seed/.lock" "$seed/options/recentProjects.xml"   # else the instance opens the projects of the fleet
  mkdir -p "$seed/options"
  printf '<application>\n  <component name="Trusted.Paths.Settings">\n    <option name="TRUSTED_PATHS">\n      <list>\n        <option value="%s" />\n      </list>\n    </option>\n  </component>\n</application>\n' \
    "$root/trees" > "$seed/options/trusted-paths.xml"
  # Only the port: the plugin then takes its default disabled tools (install, restart, read_file, rename, move).
  printf '<application>\n  <component name="McpPluginSettings">\n    <option name="serverPort" value="%s" />\n  </component>\n</application>\n' \
    "$port" > "$seed/options/mcp-plugin.xml"
  mv -- "$seed" "${P[config]}"
  echo "config seeded from $CONFIG_SRC"
fi
grep -Eq "name=\"serverPort\" value=\"$port\"" "$MCP_XML" || die "$MCP_XML does not set serverPort $port: refused"
# A bare serverMode start opens each project with opened="true" in recentProjects.xml (new at each start),
# and a serverMode IDE checks the trust of each project.
python3 -I -B - "$FLEET_PY" "$HOME" "${P[config]}/options" "${PROJECTS[@]}" <<'PY'
import sys
from pathlib import Path
fleet_py, home, options, projects = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4:]
sys.path.insert(0, str(Path(fleet_py).parent))
import fleet
import xml.etree.ElementTree as ET
empty = ('<application><component name="RecentProjectsManager"><option name="additionalInfo"><map />'
         '</option></component></application>')
root = ET.fromstring(fleet.rewrite_recent_projects(empty, projects, home))
# Measured on GoLand 2026.2: when the entries have no frame element, a bare serverMode start opens only
# one project (the last entry); with a frame element in each entry, it opens all of them.
for i, meta in enumerate(root.iter("RecentProjectMetaInfo")):
    xy = str(60 + 30 * i)
    ET.SubElement(meta, "frame", {"x": xy, "y": xy, "width": "1400", "height": "1000"})
ET.indent(root, space="  ")
(options / "recentProjects.xml").write_text(ET.tostring(root, encoding="unicode") + "\n")
trusted = options / "trusted-paths.xml"
old = trusted.read_text() if trusted.exists() else None
trusted.write_text(fleet.trust_project_paths(old, projects, home) + "\n")
PY
echo "recentProjects.xml and trusted-paths.xml: ${#PROJECTS[@]} project dir(s)"
rm -rf -- "${P[plugins]}"
mkdir -p "${P[plugins]}"
for d in "${FLEET_PLUGINS[@]}"; do cp -a -- "$d" "${P[plugins]}/"; done
unzip -q "$zip" -d "${P[plugins]}"
[ -d "${P[plugins]}/idesense" ] || die "the zip $zip has no idesense folder"
vmo_text > "$VMO"
[ -r "$VMO" ] && check_path_args < "$VMO" || die "$VMO does not have the four path options exactly one time: refused"
rm -f "$PIDF"
if [ "$cmd" = prepare ]; then
  echo "prepared $IDE_DIR; nothing was started"
  exit 0
fi

# --- start: the launch and the guard after the launch
"${LAUNCH[@]}" > "$LAUNCH_OUT" 2>&1 < /dev/null &
lpid=$!
echo "launched pid $lpid: ${LAUNCH[*]}"

end_launched() {  # $1 = the reason. SIGKILL at once to each process of the launched tree with the marks of this launch.
  local p
  echo "bench-ide: $1" >&2
  for p in $(tree_pids "$lpid"); do
    ours_by_launch "$p" && kill -KILL "$p" 2>/dev/null || true
  done
  echo "bench-ide: SIGKILL sent; see $LAUNCH_OUT" >&2
  exit 1
}

# The launcher ends with exec of the java, so the java normally keeps the launched pid; a child java is also found.
jpid=""
for _ in $(seq 1 100); do  # 20 s
  for p in $(tree_pids "$lpid"); do
    a0=""
    IFS= read -r -d '' a0 2>/dev/null < "/proc/$p/cmdline" || true
    if [ "${a0##*/}" = java ]; then jpid="$p"; break 2; fi
  done
  alive "$lpid" || break
  sleep 0.2
done
[ -n "$jpid" ] || end_launched "no java process in the launched tree of pid $lpid within 20 s"
tr '\0' '\n' < "/proc/$jpid/cmdline" | check_path_args \
  || end_launched "the java pid $jpid does not have the four -Didea.*.path options of $IDE_DIR: it could reach the fleet"
echo "$jpid" > "$PIDF"
echo "java pid $jpid has the four path options; pid file $PIDF"

deadline=$((SECONDS + 300))
while :; do
  if v="$(mcp_post "$INIT" 2>/dev/null | version_of 2>/dev/null)" && [ -n "$v" ]; then break; fi
  alive "$jpid" || die "the IDE (pid $jpid) ended before it answered; see $LAUNCH_OUT and ${P[log]}/idea.log"
  [ "$SECONDS" -lt "$deadline" ] || die "no answer to initialize on $URL after 300 s; pid $jpid still runs (bench-ide.sh stop $ide)"
  sleep 2
done
echo "ready: pid $jpid, port $port, serverInfo.version $v"

# Wait until the server lists each project dir as open (300 s more). On a timeout the IDE continues to run.
deadline=$((SECONDS + 300))
while :; do
  open="$(open_projects)" || open=""
  missing=()
  for d in "${PROJECTS[@]}"; do
    cut -f1 <<<"$open" | grep -Fxq -- "$d" || missing+=("$d")
  done
  [ "${#missing[@]}" -eq 0 ] && break
  alive "$jpid" || die "the IDE (pid $jpid) ended before it opened the projects; see ${P[log]}/idea.log"
  [ "$SECONDS" -lt "$deadline" ] \
    || die "after 300 s these project dirs are not open: ${missing[*]}; pid $jpid still runs (bench-ide.sh stop $ide)"
  sleep 5
done
echo "open projects:"
cut -f1 <<<"$open" | sed 's/^/  /'
