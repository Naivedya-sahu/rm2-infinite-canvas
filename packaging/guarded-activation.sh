#!/bin/sh
# Run on rM2 after install, with user-approved restart; no notebook writes.
# Usage: guarded-activation.sh <build-dir>
set -eu
base=${1:?build dir required}
qrr=/home/root/xovi/exthome/qt-resource-rebuilder
mkdir -p "$base"
trap '' HUP
since=$(date +%s)
printf '%s\n' "$since" > "$base/restart-start"
printf 'ACTIVATING\n' > "$base/result"
systemctl reset-failed xochitl
systemctl restart xochitl
sleep 1
firstpid=$(systemctl show xochitl -p MainPID --value)
sleep 28
state=$(systemctl show xochitl -p ActiveState --value)
pid=$(systemctl show xochitl -p MainPID --value)
restarts=$(systemctl show xochitl -p NRestarts --value)
journalctl -u xochitl --since "@$since" --no-pager > "$base/startup.log"
fatal_pattern='Type Toolbar unavailable|Non-existent attached object|Cannot assign to non-existent|Cannot load legacydevice|Cannot not open the startup window|(Toolbar|DocumentView|DeviceSceneView)\.qml:.*(ReferenceError|TypeError|SyntaxError)'
printf 'startup pid=%s current pid=%s state=%s restarts=%s\n' "$firstpid" "$pid" "$state" "$restarts"
if [ "$state" = active ] && [ "$pid" != 0 ] && [ "$pid" = "$firstpid" ] && [ "$restarts" = 0 ] && ! grep -Eqi "$fatal_pattern" "$base/startup.log"; then
    systemctl show xochitl -p MainPID -p NRestarts -p ActiveState -p SubState
    printf 'PASS\n' > "$base/result"
    exit 0
fi
printf 'Native startup check failed; disabling infinite-canvas QMDs only.\n'
systemctl stop xochitl || true
for f in infiniteCanvas.qmd infiniteCanvasHome.qmd; do
    if [ -f "$qrr/$f" ]; then mv "$qrr/$f" "$base/$f.failed"; fi
done
systemctl reset-failed xochitl
systemctl start xochitl
sleep 22
systemctl show xochitl -p MainPID -p NRestarts -p ActiveState -p SubState
printf 'ROLLED_BACK\n' > "$base/result"
exit 42
