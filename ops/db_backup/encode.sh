#!/bin/bash
# Build the two Railway variable payloads for the db-backup service from this checkout:
#
#   SCRIPT_B64     base64 of ops/db_backup/backup.sh     (the dump + restore check)
#   HOUSEKEEP_B64  base64 of ops/db_backup/housekeep.sh  (precheck, manifest, rotation, offsite)
#
# Usage:
#   ops/db_backup/encode.sh [<out-dir>]        write <out-dir>/SCRIPT_B64 and HOUSEKEEP_B64
#                                              (default: a new mktemp directory) and print a
#                                              summary: commit, bytes and sha256 of each script
#   ops/db_backup/encode.sh --print NAME       print only that payload (one line, no newline),
#                                              for piping into a variable setter
#
# Each payload is single-line base64 (no wrapping) and is decoded back and compared with its
# source before it is written, so what is pasted is byte-identical to the reviewed file. The
# start command logs `BK payload <sha256> /tmp/b.sh` and `... /tmp/h.sh`; those must equal the
# script sha256 values printed here. The payloads hold code only, never a secret.
#
# Exit codes: 0 ok; 1 a script is missing or a round trip failed; 2 usage.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
declare -A SRC=([SCRIPT_B64]="$HERE/backup.sh" [HOUSEKEEP_B64]="$HERE/housekeep.sh")
ORDER="SCRIPT_B64 HOUSEKEEP_B64"

payload() {  # payload NAME -> base64 on stdout, after a round-trip check
  local f=${SRC[$1]} b
  [ -f "$f" ] || { echo "encode: missing $f" >&2; return 1; }
  b=$(base64 -w0 < "$f")
  if [ "$(printf '%s' "$b" | base64 -d | sha256sum | cut -d' ' -f1)" != \
       "$(sha256sum < "$f" | cut -d' ' -f1)" ]; then
    echo "encode: round trip failed for $1" >&2; return 1
  fi
  printf '%s' "$b"
}

if [ "${1:-}" = "--print" ]; then
  [ $# -eq 2 ] && [ -n "${SRC[$2]+x}" ] || { echo "usage: $0 --print SCRIPT_B64|HOUSEKEEP_B64" >&2; exit 2; }
  payload "$2"
  exit 0
fi
[ $# -le 1 ] || { echo "usage: $0 [<out-dir>] | --print NAME" >&2; exit 2; }

OUT=${1:-$(mktemp -d "${TMPDIR:-/tmp}/db-backup-payload-XXXXXX")}
mkdir -p "$OUT"
REV=$(git -C "$HERE" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)
DIRTY=$(git -C "$HERE" status --porcelain -- backup.sh housekeep.sh 2>/dev/null || true)
echo "commit $REV${DIRTY:+ (WARNING: uncommitted changes to the scripts; payload is not a reviewed commit)}"
for name in $ORDER; do
  payload "$name" > "$OUT/$name"
  f=${SRC[$name]}
  echo "$name  source $(basename "$f")  bytes $(stat -c %s "$f")  sha256 $(sha256sum < "$f" | cut -d' ' -f1)  payload_chars $(stat -c %s "$OUT/$name")  file $OUT/$name"
done
