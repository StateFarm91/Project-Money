#!/bin/bash
# db-backup housekeeping: space precheck, checksum manifest, rotation, optional offsite copy.
# RELENG 2026-10-11; ENG-DB-BACKUP 2026-11-28. Deployed only when the owner applies
# brambleloop/research/DB-BACKUP-APPLY.md (Railway variable HOUSEKEEP_B64 + start command).
#
# It wraps the dump-and-restore script, ops/db_backup/backup.sh (Railway variable SCRIPT_B64,
# BK line protocol), and acts only on that script's verdict line, `BK RESULT OK <path>`.
#
#   housekeep.sh run [<backup-script>] <dir> precheck, run the script, then record, rotate, ship
#                                            (script defaults to $BACKUP_SCRIPT, else backup.sh
#                                            beside this file)
#   housekeep.sh precheck <dir>              reclaim and make room for one more dump, or fail:
#                                            1. classify the dumps on disk, writing nothing
#                                            2. delete partial/unverified dumps and verified ones
#                                               beyond the newest BACKUP_KEEP (only while a
#                                               verified dump remains), then the oldest verified
#                                               beyond the newest until 1.2x the newest fits
#                                            3. only then write the manifest; a failed write is
#                                               fatal (no dump is attempted)
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
# Adoption. Until the manifest holds an `adopt-done` event, a dump that is not in the manifest
# is LEGACY: if pg_restore reads it back in full (every data block, so a truncated dump is
# refused) it counts as verified and is recorded with "adopted":true. After `adopt-done`, a
# dump not in the manifest is a failed or partial run and is deleted while a verified one
# remains.
#
# Why the precheck decides from the disk and writes last (2026-11-28). The first production
# run found the 5 GB volume full. Every manifest append failed with ENOSPC, the precheck then
# read an empty manifest as "no previous dump", deleted nothing, and pg_dump hit ENOSPC too.
# Now nothing is written until deletes have made room, and a write that still fails stops the
# run instead of being taken for an empty history.
#
# Exit codes: 0 ok; 1 local backup failed, no room, or the manifest could not be written;
# 2 usage; 3 local OK but offsite failed; 4 manifest check found a missing or changed dump.
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

# Complete manifest lines only: an append cut short by ENOSPC leaves a line with no closing }.
mlines() { [ -f "$1/$MANIFEST" ] && grep -a '^{.*}$' "$1/$MANIFEST"; return 0; }

# mwrite <dir> <json>: append one line; fail loudly if it did not land (ENOSPC, read-only).
mwrite() {
  if ! printf '%s\n' "$2" >> "$1/$MANIFEST" 2>/dev/null; then
    say "manifest write FAILED in $1 (no space left or not writable)"
    return 1
  fi
}

# Verified dump file names still present in the manifest, oldest first.
kept() {
  local dir=$1 line f
  mlines "$dir" | while IFS= read -r line; do
    f=$(field "$line" file)
    [ -n "$f" ] || continue
    case "$(field "$line" event)" in
      verified) printf '%s\n' "$f" ;;
      deleted) printf '%s\n' "-$f" ;;
    esac
  done | awk '/^-/{d[substr($0,2)]=1; next} {o[++n]=$0} END{for(i=1;i<=n;i++) if(!d[o[i]]) print o[i]}'
}

adopt_done() { mlines "$1" | grep -q '"event":"adopt-done"'; }
sha_of() { sha256sum "$1" | awk '{print $1}'; }
size_of() { stat -c %s "$1"; }
free_bytes() {
  if [ -n "${BK_FREE_BYTES:-}" ]; then echo "$BK_FREE_BYTES"; return; fi
  df -Pk "$1" | awk 'NR==2{print $4*1024}'
}
reads_back() { pg_restore --file=/dev/null "$1" 2>/dev/null; }
drop() { rm -f -- "${1:?}/${2:?}"; }  # drop <dir> <file>

write_sums() {
  local dir=$1 f line
  if {
    for f in $(kept "$dir"); do
      [ -f "$dir/$f" ] || continue
      line=$(mlines "$dir" | grep -F "\"event\":\"verified\",\"file\":\"$f\"" | tail -1)
      printf '%s  %s\n' "$(field "$line" sha256)" "$f"
    done
  } > "$dir/$SUMS.tmp" 2>/dev/null && mv "$dir/$SUMS.tmp" "$dir/$SUMS" 2>/dev/null; then
    return 0
  fi
  drop "$dir" "$SUMS.tmp"
  say "manifest write FAILED in $dir ($SUMS)"
  return 1
}

delete_dump() {  # delete_dump <dir> <file> <why>   (rotation: delete, then record)
  drop "$1" "$2"
  say "rotate deleted $2 ($3)"
  mwrite "$1" "$(printf '{"event":"deleted","file":"%s","at":"%s","why":"%s"}' "$2" "$(now)" "$3")"
}

cmd_record() {
  local dir=$1 path=$2 f toc
  f=$(basename "$path")
  [ -f "$dir/$f" ] || { say "record FAIL no such dump $f"; return 1; }
  toc=$(pg_restore --list "$dir/$f" 2>/dev/null | grep -vc '^;' || true)
  mwrite "$dir" "$(printf '{"event":"verified","file":"%s","bytes":%s,"sha256":"%s","at":"%s","toc_entries":%s}' \
    "$f" "$(size_of "$dir/$f")" "$(sha_of "$dir/$f")" "$(now)" "${toc:-0}")" \
    || { say "record FAIL $f could not be written to the manifest"; return 1; }
  write_sums "$dir" || return 1
  say "manifest recorded $f sha256 $(sha_of "$dir/$f")"
}

cmd_rotate() {
  local dir=$1 all n f newest bad=0
  all=$(kept "$dir")
  n=$(printf '%s\n' "$all" | grep -c . || true)
  newest=$(printf '%s\n' "$all" | tail -1)
  for f in $(printf '%s\n' "$all" | head -n "$(( n > KEEP ? n - KEEP : 0 ))"); do
    delete_dump "$dir" "$f" "older than the newest $KEEP verified" || bad=1
  done
  # A dump the manifest never verified is a failed or partial run. Delete it only when a
  # verified dump exists, so a failure never removes the last thing that might help.
  if [ -n "$newest" ]; then
    for f in $(cd "$dir" && ls -1 brambleloop_prod_*.dump 2>/dev/null); do
      if ! printf '%s\n' "$all" | grep -qx "$f"; then
        drop "$dir" "$f"; say "rotate removed unverified $f"
      fi
    done
  fi
  write_sums "$dir" || bad=1
  say "rotate kept $(kept "$dir" | grep -c . || true) verified (keep $KEEP)"
  [ "$bad" = 0 ] || return 1
}

cmd_check() {
  local dir=$1 bad=0 f line want
  for f in $(kept "$dir"); do
    line=$(mlines "$dir" | grep -F "\"event\":\"verified\",\"file\":\"$f\"" | tail -1)
    want=$(field "$line" sha256)
    if [ ! -f "$dir/$f" ]; then say "check MISSING $f"; bad=1
    elif [ "$(sha_of "$dir/$f")" != "$want" ]; then say "check CHANGED $f"; bad=1
    else say "check ok $f"; fi
  done
  [ "$bad" = 0 ] || return 4
}

# precheck: reclaim, make room, then write. The order is the point; see the header.
cmd_precheck() {
  local dir=$1 f g all adopting=0 need=0 free n i ok=1
  local -a GOOD=() ADOPT=() BAD=() GONE=()
  all=$(kept "$dir")
  adopt_done "$dir" || adopting=1

  # 1. Classify, newest first, writing nothing. In adoption, once BACKUP_KEEP dumps are known
  #    good, anything older is deleted in step 2 anyway, so it is not read back.
  for f in $(cd "$dir" && ls -1r brambleloop_prod_*.dump 2>/dev/null); do
    if printf '%s\n' "$all" | grep -qx "$f"; then
      GOOD=("$f" "${GOOD[@]}")
    elif [ "$adopting" = 1 ] && [ "${#GOOD[@]}" -ge "$KEEP" ]; then
      BAD=("$f" "${BAD[@]}"); say "adopt skipped $f (older than the newest $KEEP verified)"
    elif [ "$adopting" = 1 ] && reads_back "$dir/$f"; then
      GOOD=("$f" "${GOOD[@]}"); ADOPT=("$f" "${ADOPT[@]}")  # oldest first, as manifest order is time order
      say "adopt verified legacy $f ($(size_of "$dir/$f") bytes, reads back in full)"
    else
      BAD=("$f" "${BAD[@]}")
      if [ "$adopting" = 1 ]; then say "adopt refused $f (does not read back in full)"; fi
    fi
  done
  free=$(free_bytes "$dir")

  # 2. Free space by deleting only, and only while at least one verified dump remains.
  if [ "${#GOOD[@]}" -eq 0 ]; then
    if [ "${#BAD[@]}" -eq 0 ]; then say "precheck no previous dump; proceeding"
    else say "precheck no verified dump on the volume; ${#BAD[@]} unverified left untouched"; fi
  else
    for f in "${BAD[@]}"; do
      free=$(( free + $(size_of "$dir/$f") )); drop "$dir" "$f"
      GONE+=("$f|partial, unverified or older than the newest $KEEP")
      say "rotate removed unverified $f"
    done
    n=${#GOOD[@]}
    for (( i=0; i < n-KEEP; i++ )); do
      f=${GOOD[$i]}; free=$(( free + $(size_of "$dir/$f") )); drop "$dir" "$f"
      GONE+=("$f|older than the newest $KEEP verified"); say "rotate deleted $f (older than the newest $KEEP verified)"
    done
    if (( n > KEEP )); then GOOD=("${GOOD[@]:n-KEEP}"); fi
    need=$(( $(size_of "$dir/${GOOD[-1]}") * HEADROOM / 100 ))
    while [ "$free" -lt "$need" ] && [ "${#GOOD[@]}" -gt 1 ]; do
      f=${GOOD[0]}; free=$(( free + $(size_of "$dir/$f") )); drop "$dir" "$f"
      GONE+=("$f|making room for the next dump"); say "rotate deleted $f (making room for the next dump)"
      GOOD=("${GOOD[@]:1}")
    done
    if [ -n "${BK_FREE_BYTES:-}" ]; then BK_FREE_BYTES=$free; fi
  fi

  # 3. Record. A write that fails is fatal: no dump is attempted on a volume this full.
  for f in "${ADOPT[@]}"; do
    [ -f "$dir/$f" ] || continue
    mwrite "$dir" "$(printf '{"event":"verified","file":"%s","bytes":%s,"sha256":"%s","at":"%s","toc_entries":%s,"adopted":true}' \
      "$f" "$(size_of "$dir/$f")" "$(sha_of "$dir/$f")" "$(now)" \
      "$(pg_restore --list "$dir/$f" 2>/dev/null | grep -vc '^;' || true)")" || ok=0
  done
  for g in "${GONE[@]}"; do
    f=${g%%|*}
    printf '%s\n' "$all" | grep -qx "$f" || continue  # only manifest entries need a tombstone
    mwrite "$dir" "$(printf '{"event":"deleted","file":"%s","at":"%s","why":"%s"}' "$f" "$(now)" "${g#*|}")" || ok=0
  done
  if [ "$adopting" = 1 ] && [ "$ok" = 1 ]; then
    if mwrite "$dir" "$(printf '{"event":"adopt-done","at":"%s","adopted":%s}' "$(now)" "${#ADOPT[@]}")"; then
      say "adopt recorded ${#ADOPT[@]} legacy dump(s)"
    else ok=0; fi
  fi
  write_sums "$dir" || ok=0
  if [ "$ok" = 0 ]; then
    say "precheck FAIL the manifest could not be written; no dump attempted (free $free)"
    return 1
  fi
  if [ "$free" -lt "$need" ]; then
    say "precheck FAIL free $free < need $need with only the newest verified dump left"
    return 1
  fi
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
  mwrite "$dir" "$(printf '{"event":"offsite","file":"%s","key":"%s","ciphertext_sha256":"%s","at":"%s"}' \
    "$f" "$key" "$want" "$(now)")" || { say "OFFSITE FAIL manifest write"; return 3; }
  say "OFFSITE OK $OFFSITE_BUCKET/$key ciphertext_sha256 $want"
}

cmd_run() {
  local script=$1 dir=$2 log rc dump
  [ -f "$script" ] || { say "RESULT FAIL no backup script at $script"; return 1; }
  cmd_precheck "$dir" || { say "RESULT FAIL precheck"; return 1; }
  log=$(mktemp /tmp/bk-log-XXXXXX)
  # The script writes into the same directory this wrapper rotates.
  BACKUP_DIR=$dir bash "$script" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  dump=$(sed -n 's/^BK RESULT OK \(.*\)$/\1/p' "$log" | tail -1)
  rm -f -- "${log:?}"
  if [ -z "$dump" ]; then
    # Worded so it can never match a log scanner looking for the OK verdict
    # (ops/autopromote.py OK_LINE): the old text quoted that verdict and would have read as OK.
    say "RESULT FAIL housekeep: the backup script reported no verified dump (exit $rc); nothing recorded or rotated"
    return 1
  fi
  cmd_record "$dir" "$dump" || { say "RESULT FAIL housekeep: record"; return 1; }
  cmd_rotate "$dir" || { say "RESULT FAIL housekeep: rotate could not write the manifest"; return 1; }
  cmd_check "$dir" || return 4
  cmd_ship "$dir" "$dump" || return 3
  return 0
}

case "${1:-}" in
  run)
    if [ $# -eq 3 ]; then cmd_run "$2" "$3"
    elif [ $# -eq 2 ]; then cmd_run "${BACKUP_SCRIPT:-$(dirname "$0")/backup.sh}" "$2"
    else exit 2; fi ;;
  precheck|rotate|check) [ $# -eq 2 ] || exit 2; "cmd_$1" "$2" ;;
  record|ship) [ $# -eq 3 ] || exit 2; "cmd_$1" "$2" "$3" ;;
  *) sed -n '2,48p' "$0"; exit 2 ;;
esac
