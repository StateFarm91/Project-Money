#!/bin/bash
# usage: boot.sh <OLD|NEW> <dbname> <port> <label> [extra env...]
W=/home/user/Project-Money/.claude/worktrees/W4-MIG-$1/brambleloop
S=$SCRATCH/mig
sha=$(git -C $W rev-parse HEAD)
shift; db=$1; port=$2; label=$3; shift 3
cd $W
env -i PATH=/usr/bin:/bin HOME=/root PYTHONPATH=$W/src \
  DATABASE_URL=postgresql://postgres@127.0.0.1:55433/$db \
  BRAMBLELOOP_REQUIRE_POSTGRES=1 BRAMBLELOOP_PHASE=shadow BRAMBLELOOP_EMBEDDED_WORKER=0 \
  BRAMBLELOOP_COMMIT=$sha "$@" \
  nice -n 10 /home/user/Project-Money/brambleloop/.venv/bin/python -m uvicorn brambleloop.app.main:app \
  --host 127.0.0.1 --port $port --workers 1 > $S/$label.log 2>&1 &
pid=$!
echo "pid $pid"
for i in $(seq 1 180); do
  code=$(curl -s -o $S/$label.health.json -w '%{http_code}' http://127.0.0.1:$port/health) && [ "$code" != "000" ] && break
  kill -0 $pid 2>/dev/null || { echo "DIED"; tail -30 $S/$label.log; exit 1; }
  sleep 1
done
echo "health $code after ${i}s"; echo $pid > $S/$label.pid
