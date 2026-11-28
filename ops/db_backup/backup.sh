#!/bin/bash
# db-backup: one pg_dump of the production database, proven by a full restore into a scratch
# cluster and a per-table row-count comparison. Speaks the BK line protocol; the last line is
# `BK RESULT OK <dump path>` only when the dump restored. ops/db_backup/housekeep.sh acts on
# that line alone (manifest, rotation, offsite).
#
# ENG-DB-BACKUP 2026-11-28. This is the repository copy of the Railway variable SCRIPT_B64
# (generate it with ops/db_backup/encode.sh). It is the proven 2026-10-11 script
# (research/final_build/w4/evidence_MIGRATE/scripts/backup_local.sh is its local rehearsal)
# with one change:
#
#   The DATA of continuity_archives is excluded (--exclude-table-data). core/continuity.py
#   retain() keeps the last RETAINED_ARCHIVES gzip whole-database exports in that table, about
#   100 MB+ each, so every dump carried copies of earlier exports and the 5 GB volume filled.
#   Those rows are derived (each is an export of the other tables, which this dump holds in
#   full). The table's SCHEMA is still dumped, so a restored database boots and continuity
#   simply writes a fresh archive. The comparison expects 0 restored rows for it, and a
#   non-zero count, a missing table, or a TABLE DATA entry for it in the archive is a FAIL:
#   the dump would be carrying the archives again.
#
# Environment:
#   SRC_URL           the database to dump (Railway: a reference to the Postgres service URL)
#   BACKUP_DIR        where the dump is written (default /backup, the db-backup volume)
#   BK_RESTORE_PORT   port of the scratch restore cluster (default 5499)
#   BK_RESTORE_URL    test-only: restore into this existing server instead of a scratch cluster
set -uo pipefail

# Tables whose DATA is excluded from the dump by design. Keep in step with the pg_dump line.
EXCLUDED_DATA_TABLES="continuity_archives"

BACKUP_DIR=${BACKUP_DIR:-/backup}
PORT=${BK_RESTORE_PORT:-5499}
fail() { echo "BK RESULT FAIL $*"; exit 1; }

[ -n "${SRC_URL:-}" ] || fail "config SRC_URL is not set"
mkdir -p "$BACKUP_DIR" || fail "config cannot create $BACKUP_DIR"

TS=$(date -u +%Y%m%dT%H%M%SZ)
F=$BACKUP_DIR/brambleloop_prod_${TS}.dump
echo "BK start $TS"
echo "BK server_version $(psql "$SRC_URL" -Atc 'show server_version' 2>&1 | head -1)"
echo "BK pg_dump_version $(pg_dump --version)"
echo "BK excluded_table_data $EXCLUDED_DATA_TABLES"

pg_dump --format=custom --compress=6 --no-owner --no-privileges \
  --exclude-table-data=continuity_archives \
  --dbname="$SRC_URL" --file="$F"
rc=$?; if [ $rc -ne 0 ]; then fail "pg_dump rc=$rc"; fi
echo "BK file $F bytes $(stat -c %s "$F") sha256 $(sha256sum "$F" | cut -d' ' -f1)"
TOC=$(pg_restore --list "$F") || fail "pg_restore --list rc=$?"
echo "BK toc_entries $(printf '%s\n' "$TOC" | grep -vc '^;')"
for t in $EXCLUDED_DATA_TABLES; do
  printf '%s\n' "$TOC" | grep -Eq "TABLE DATA [^ ]+ $t( |\$)" \
    && fail "dump contains TABLE DATA for $t, which must be excluded"
  printf '%s\n' "$TOC" | grep -Eq " TABLE [^ ]+ $t( |\$)" \
    || echo "BK note $t has no TABLE entry in the dump (not present in the source schema)"
done

# ---- restore target -------------------------------------------------------------------
WORK=""
as_pg() {  # run a cluster command as the postgres user when this script runs as root
  if [ "$(id -u)" != 0 ]; then "$@"
  elif command -v gosu >/dev/null 2>&1; then gosu postgres "$@"
  elif command -v runuser >/dev/null 2>&1; then runuser -u postgres -- "$@"
  else su postgres -s /bin/bash -c "$(printf '%q ' "$@")"; fi
}
cleanup() {
  if [ -n "$WORK" ]; then
    as_pg pg_ctl -D "$WORK/data" -m immediate -w stop >/dev/null 2>&1 || true
    rm -rf "$WORK"
  fi
}
trap cleanup EXIT

if [ -n "${BK_RESTORE_URL:-}" ]; then
  R=$BK_RESTORE_URL
else
  if ! command -v initdb >/dev/null 2>&1; then
    for d in /usr/lib/postgresql/*/bin; do [ -x "$d/initdb" ] && PATH="$d:$PATH"; done
  fi
  WORK=$(mktemp -d /tmp/bkr-XXXXXX)
  [ "$(id -u)" = 0 ] && chown postgres "$WORK"
  as_pg initdb -D "$WORK/data" -U postgres -A trust --no-sync >"$WORK/initdb.log" 2>&1 \
    || fail "restore initdb $(tail -c 300 "$WORK/initdb.log")"
  as_pg pg_ctl -D "$WORK/data" -l "$WORK/server.log" -w \
      -o "-p $PORT -k $WORK -c listen_addresses= -c fsync=off" start >/dev/null 2>&1 \
    || fail "restore cluster start $(tail -c 300 "$WORK/server.log" 2>/dev/null)"
  psql "host=$WORK port=$PORT user=postgres dbname=postgres" -qAtc "create database restored" \
    || fail "restore createdb"
  R="host=$WORK port=$PORT user=postgres dbname=restored"
fi

ERR=$(mktemp /tmp/bk-restore-err-XXXXXX)
pg_restore --dbname="$R" --no-owner --exit-on-error "$F" 2>"$ERR"
rc=$?; if [ $rc -ne 0 ]; then msg=$(head -c 400 "$ERR"); rm -f "$ERR"; fail "restore rc=$rc $msg"; fi
rm -f "$ERR"
echo "BK restore_ok"

# ---- row counts: restored vs source ---------------------------------------------------
is_excluded() { case " $EXCLUDED_DATA_TABLES " in *" $1 "*) return 0 ;; esac; return 1; }
n=0; tot=0; drift=0; bad=""; seen=""
for t in $(psql "$R" -Atc "select tablename from pg_tables where schemaname='public' order by 1"); do
  r=$(psql "$R" -Atc "select count(*) from \"$t\"")
  s=$(psql "$SRC_URL" -Atc "select count(*) from \"$t\"")
  n=$((n+1)); tot=$((tot+r))
  if is_excluded "$t"; then
    seen="$seen $t"
    echo "BK excluded $t restored=$r source_now=$s (data excluded by design; expect restored=0)"
    [ "$r" = 0 ] || bad="$bad $t:restored=$r"
  elif [ "$r" != "$s" ]; then
    drift=$((drift+1)); echo "BK drift $t restored=$r source_now=$s"
  fi
done
for t in $EXCLUDED_DATA_TABLES; do
  case " $seen " in *" $t "*) continue ;; esac
  if [ "$(psql "$SRC_URL" -Atc "select to_regclass('public.$t') is not null")" = t ]; then
    bad="$bad $t:missing-from-restore"
  fi
done
[ -z "$bad" ] || fail "excluded-table check$bad"
echo "BK tables $n restored_rows $tot tables_changed_since_snapshot $drift"
echo "BK volume $(df -h "$BACKUP_DIR" | tail -1 | awk '{print $2" total "$4" free"}')"
ls -l "$BACKUP_DIR" | sed 's/^/BK ls /'
echo "BK RESULT OK $F"
