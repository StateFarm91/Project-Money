set -uo pipefail
TS=$(date -u +%Y%m%dT%H%M%SZ)
F=$SCRATCH/mig/backup/brambleloop_prod_${TS}.dump
echo "BK start $TS"
echo "BK server_version $(psql "$SRC_URL" -Atc 'show server_version' 2>&1 | head -1)"
echo "BK pg_dump_version $(pg_dump --version)"
pg_dump --format=custom --compress=6 --no-owner --no-privileges --dbname="$SRC_URL" --file="$F"
rc=$?; if [ $rc -ne 0 ]; then echo "BK RESULT FAIL pg_dump rc=$rc"; exit 1; fi
echo "BK file $F bytes $(stat -c %s "$F") sha256 $(sha256sum "$F" | cut -d' ' -f1)"
echo "BK toc_entries $(pg_restore --list "$F" | grep -vc '^;')"
: local cluster already running
: using restored db on 55433
:
pg_restore -h 127.0.0.1 -p 55433 -U postgres -d restored --no-owner --exit-on-error "$F" 2>$SCRATCH/mig/restore.err
rc=$?; if [ $rc -ne 0 ]; then echo "BK RESULT FAIL restore rc=$rc $(head -c 400 $SCRATCH/mig/restore.err)"; exit 1; fi
echo "BK restore_ok"
n=0; tot=0; drift=0
for t in $(psql -h 127.0.0.1 -p 55433 -U postgres -d restored -Atc "select tablename from pg_tables where schemaname='public' order by 1"); do
  r=$(psql -h 127.0.0.1 -p 55433 -U postgres -d restored -Atc "select count(*) from \"$t\"")
  s=$(psql "$SRC_URL" -Atc "select count(*) from \"$t\"")
  n=$((n+1)); tot=$((tot+r))
  if [ "$r" != "$s" ]; then drift=$((drift+1)); echo "BK drift $t restored=$r source_now=$s"; fi
done
echo "BK tables $n restored_rows $tot tables_changed_since_snapshot $drift"
echo "BK volume $(df -h $SCRATCH/mig/backup | tail -1 | awk '{print $2" total "$4" free"}')"
ls -l $SCRATCH/mig/backup | sed 's/^/BK ls /'
echo "BK RESULT OK $F"
