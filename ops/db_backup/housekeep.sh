#!/bin/bash
# db-backup housekeeping: space precheck, checksum manifest, rotation, optional offsite copy.
# RELENG 2026-10-11. NOT DEPLOYED. Nothing here is enabled on Railway until the owner approves
# RELENG_FIX.md section 5 and the integrator changes the db-backup start command.
#
# The proven dump-and-restore script (Railway variable SCRIPT_B64, BK line protocol, verified
# 2026-10-11T13:00Z) is left untouched. This wraps it and acts only on its own verdict line,
# `BK RESULT OK <path>`.
#
#   housekeep.sh run <backup-script> <dir>   precheck, run the script, then record, rotate, ship
#   housekeep.sh precheck <dir>              make room for one more dump, or fail
#   housekeep.sh record <dir> <dump>         add a verified dump to MANIFEST.jsonl + SHA256SUMS
#   housekeep.sh rotate <dir>                keep the newest BACKUP_KEEP verified dumps
#   housekeep.sh check <dir>                 re-hash every kept dump against the manifest
#   housekeep.sh ship <dir> <dump>           offsite copy; does nothing unless OFFSITE_UPLOAD=1
#
# Environment (all optional):
#   BACKUP_KEEP=2            verified dumps kept on the volume (minimum 1)
#   BACKUP_HEADROOM_PCT=120  free space needed for the next dump, as % of the newest dump
#   OFFSITE_UPLOAD=0         1 = encrypt and copy offsite (only after owner approval)
#   OFFSITE_ENDPOINT, OFFSITE_BUCKET, OFFSITE_REGION, OFFSITE_KEY_ID, OFFSITE_SECRET
#                            S3-compatible destination (Backblaze B2 / Cloudflare R2 / AWS)
#   OFFSITE_PREFIX=pgdump/daily/
#   OFFSITE_GPG_PUBKEY_B64   base64 of the owner's ARMORED PUBLIC key. The private key never
#                            leaves the owner. This container can encrypt but never decrypt.
#   BK_FREE_BYTES            test-only override of the volume's free space
#
# Exit codes: 0 ok; 1 local backup failed or no room; 2 usage; 3 local OK but offsite failed;
# 4 manifest check found a missing or changed dump.
set -u
MANIFEST=MANIFEST.jsonl
SUMS=SHA256SUMS
KEEP=${BACKUP_KEEP:-2}
HEADROOM=${BACKUP_HEADROOM_PCT:-120}
[ "$KEEP" -ge 1 ] 2>/dev/null || KEEP=1

say() { echo "BK $*"; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

field() {  # field <json-line> <name>  (manifest lines are written by this script only)
  printf '%s\n' "$1" | sed -n "s/.*\"$2\":\"\{0,1\}\([^\",}]*\)\"\{0,1\}[,}].*/\1/p"
}

# Verified dump file names still present, oldest first (manifest order is time order).
kept() {
  local dir=$1 line f
  [ -f "$dir/$MANIFEST" ] || return 0
  while IFS= read -r line; do
    f=$(field "$line" file)
    case "$(field "$line" event)" in
      verified) printf '%s\n' "$f" ;;
      deleted) printf '%s\n' "-$f" ;;
    esac
  done < "$dir/$MANIFEST" | awk '/^-/{d[substr($0,2)]=1; next} {o[++n]=$0} END{for(i=1;i<=n;i++) if(!d[o[i]]) print o[i]}'
}

sha_of() { sha256sum "$1" | awk '{print $1}'; }
size_of() { stat -c %s "$1"; }
free_bytes() {
  if [ -n "${BK_FREE_BYTES:-}" ]; then echo "$BK_FREE_BYTES"; return; fi
  df -Pk "$1" | awk 'NR==2{print $4*1024}'
}

write_sums() {
  local dir=$1 f line
  : > "$dir/$SUMS.tmp"
  for f in $(kept "$dir"); do
    line=$(grep -F "\"event\":\"verified\",\"file\":\"$f\"" "$dir/$MANIFEST" | tail -1)
    printf '%s  %s\n' "$(field "$line" sha256)" "$f" >> "$dir/$SUMS.tmp"
  done
  mv "$dir/$SUMS.tmp" "$dir/$SUMS"
}

delete_dump() {  # delete_dump <dir> <file> <why>
  rm -f "$1/$2"
  printf '{"event":"deleted","file":"%s","at":"%s","why":"%s"}\n' "$2" "$(now)" "$3" >> "$1/$MANIFEST"
  say "rotate deleted $2 ($3)"
}

cmd_record() {
  local dir=$1 path=$2 f toc
  f=$(basename "$path")
  [ -f "$dir/$f" ] || { say "record FAIL no such dump $f"; return 1; }
  toc=$(pg_restore --list "$dir/$f" 2>/dev/null | grep -vc '^;' || true)
  printf '{"event":"verified","file":"%s","bytes":%s,"sha256":"%s","at":"%s","toc_entries":%s}\n' \
    "$f" "$(size_of "$dir/$f")" "$(sha_of "$dir/$f")" "$(now)" "${toc:-0}" >> "$dir/$MANIFEST"
  write_sums "$dir"
  say "manifest recorded $f sha256 $(sha_of "$dir/$f")"
}

cmd_rotate() {
  local dir=$1 all n f newest
  all=$(kept "$dir")
  n=$(printf '%s\n' "$all" | grep -c . || true)
  newest=$(printf '%s\n' "$all" | tail -1)
  for f in $(printf '%s\n' "$all" | head -n "$(( n > KEEP ? n - KEEP : 0 ))"); do
    delete_dump "$dir" "$f" "older than the newest $KEEP verified"
  done
  # A dump the manifest never verified is a failed or partial run. Delete it only when a
  # newer verified dump exists, so a failure never removes the last thing that might help.
  if [ -n "$newest" ]; then
    for f in $(cd "$dir" && ls -1 brambleloop_prod_*.dump 2>/dev/null); do
      if ! printf '%s\n' "$all" | grep -qx "$f" && [[ "$f" < "$newest" ]]; then
        rm -f "$dir/$f"; say "rotate removed unverified $f"
      fi
    done
  fi
  write_sums "$dir"
  say "rotate kept $(kept "$dir" | grep -c . || true) verified (keep $KEEP)"
}

cmd_check() {
  local dir=$1 bad=0 f line want
  for f in $(kept "$dir"); do
    line=$(grep -F "\"event\":\"verified\",\"file\":\"$f\"" "$dir/$MANIFEST" | tail -1)
    want=$(field "$line" sha256)
    if [ ! -f "$dir/$f" ]; then say "check MISSING $f"; bad=1
    elif [ "$(sha_of "$dir/$f")" != "$want" ]; then say "check CHANGED $f"; bad=1
    else say "check ok $f"; fi
  done
  [ "$bad" = 0 ] || return 4
}

cmd_precheck() {
  local dir=$1 newest need free all n oldest
  all=$(kept "$dir")
  newest=$(printf '%s\n' "$all" | tail -1)
  [ -n "$newest" ] && [ -f "$dir/$newest" ] || { say "precheck no previous dump; proceeding"; return 0; }
  need=$(( $(size_of "$dir/$newest") * HEADROOM / 100 ))
  free=$(free_bytes "$dir")
  while [ "$free" -lt "$need" ]; do
    n=$(kept "$dir" | grep -c . || true)
    if [ "$n" -le 1 ]; then
      say "precheck FAIL free $free < need $need with only the newest verified dump left"
      return 1
    fi
    oldest=$(kept "$dir" | head -1)
    free=$(( free + $(size_of "$dir/$oldest") ))
    delete_dump "$dir" "$oldest" "making room for the next dump"
    [ -n "${BK_FREE_BYTES:-}" ] && BK_FREE_BYTES=$free
  done
  write_sums "$dir"
  say "precheck ok free $free need $need"
}

cmd_ship() { ( ship_inner "$@" ); }

ship_inner() {
  local dir=$1 f src work key url got want cfg
  if [ "${OFFSITE_UPLOAD:-0}" != "1" ]; then
    say "offsite disabled (OFFSITE_UPLOAD is not 1; no destination approved)"
    return 0
  fi
  f=$(basename "$2"); src="$dir/$f"
  for v in OFFSITE_ENDPOINT OFFSITE_BUCKET OFFSITE_REGION OFFSITE_KEY_ID OFFSITE_SECRET OFFSITE_GPG_PUBKEY_B64; do
    if [ -z "${!v:-}" ]; then say "OFFSITE FAIL $v is not set"; return 3; fi
  done
  for t in gpg curl; do
    command -v "$t" >/dev/null 2>&1 || { say "OFFSITE FAIL $t is not installed in this image"; return 3; }
  done
  work=$(mktemp -d /tmp/offsite-XXXXXX)
  trap 'rm -rf "$work"' EXIT
  export GNUPGHOME="$work/gnupg"; mkdir -m 700 "$GNUPGHOME"
  printf '%s' "$OFFSITE_GPG_PUBKEY_B64" | base64 -d > "$work/owner.pub" 2>/dev/null \
    || { say "OFFSITE FAIL public key is not valid base64"; return 3; }
  if grep -q "PRIVATE KEY" "$work/owner.pub"; then
    say "OFFSITE FAIL that is a PRIVATE key; only the owner's public key belongs here"; return 3
  fi
  gpg --batch --quiet --yes --trust-model always --recipient-file "$work/owner.pub" \
      --output "$work/$f.gpg" --encrypt "$src" 2>"$work/gpg.err" \
    || { say "OFFSITE FAIL encrypt: $(head -c 200 "$work/gpg.err")"; return 3; }
  want=$(sha_of "$work/$f.gpg")
  key="${OFFSITE_PREFIX:-pgdump/daily/}$f.gpg"
  url="${OFFSITE_ENDPOINT%/}/$OFFSITE_BUCKET/$key"
  # Credentials go to curl on stdin, never on its command line (visible in ps).
  cfg="user = \"$OFFSITE_KEY_ID:$OFFSITE_SECRET\""
  printf '%s\n' "$cfg" | curl -sS -f -K - --aws-sigv4 "aws:amz:$OFFSITE_REGION:s3" \
      -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" -T "$work/$f.gpg" "$url" -o /dev/null \
    || { say "OFFSITE FAIL upload to $OFFSITE_BUCKET/$key"; return 3; }
  # Round trip: read it back and compare. A copy nobody has read back is a hope.
  printf '%s\n' "$cfg" | curl -sS -f -K - --aws-sigv4 "aws:amz:$OFFSITE_REGION:s3" \
      -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" "$url" -o "$work/back.gpg" \
    || { say "OFFSITE FAIL read-back of $OFFSITE_BUCKET/$key"; return 3; }
  got=$(sha_of "$work/back.gpg")
  [ "$got" = "$want" ] || { say "OFFSITE FAIL read-back sha256 $got != uploaded $want"; return 3; }
  printf '{"event":"offsite","file":"%s","key":"%s","ciphertext_sha256":"%s","at":"%s"}\n' \
    "$f" "$key" "$want" "$(now)" >> "$dir/$MANIFEST"
  say "OFFSITE OK $OFFSITE_BUCKET/$key ciphertext_sha256 $want"
}

cmd_run() {
  local script=$1 dir=$2 log rc dump
  cmd_precheck "$dir" || { say "RESULT FAIL precheck"; return 1; }
  log=$(mktemp /tmp/bk-log-XXXXXX)
  bash "$script" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  dump=$(sed -n 's/^BK RESULT OK \(.*\)$/\1/p' "$log" | tail -1)
  rm -f "$log"
  if [ -z "$dump" ]; then
    say "housekeep: no BK RESULT OK from the backup script (exit $rc); nothing recorded or rotated"
    return 1
  fi
  cmd_record "$dir" "$dump" || return 1
  cmd_rotate "$dir"
  cmd_check "$dir" || return 4
  cmd_ship "$dir" "$dump" || return 3
  return 0
}

case "${1:-}" in
  run) [ $# -eq 3 ] || exit 2; cmd_run "$2" "$3" ;;
  precheck|rotate|check) [ $# -eq 2 ] || exit 2; "cmd_$1" "$2" ;;
  record|ship) [ $# -eq 3 ] || exit 2; "cmd_$1" "$2" "$3" ;;
  *) sed -n '2,30p' "$0"; exit 2 ;;
esac
