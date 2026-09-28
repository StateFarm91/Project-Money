"""Run one local suite with source binding and durable logs; not release certification.

The Windows bundled interpreter ignores PYTHONPATH, so explicitly load local dependencies.
No production credentials/configuration are propagated to the child.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


def main():
    p = argparse.ArgumentParser()
    p.add_argument('suite')
    p.add_argument('--deps', required=True)
    p.add_argument('--font', required=True)
    p.add_argument('--timeout', type=int, default=1500)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[3]
    suite = (root / args.suite).resolve()
    if suite.parent != root / 'tests' or not suite.is_file():
        p.error('suite must be an existing tests/test_*.py file')
    if not suite.name.startswith('test_'):
        p.error('not a test suite')
    def git(*command):
        return subprocess.check_output(['git', *command], cwd=root, text=True).strip()
    sha = git('rev-parse', 'HEAD')
    started = datetime.now(timezone.utc)
    run_id = started.strftime('%Y%m%dT%H%M%S%fZ') + '-' + suite.stem
    evidence = Path(__file__).parent / 'evidence'
    evidence.mkdir(exist_ok=True)
    log = evidence / (run_id + '.log')
    record_path = evidence / (run_id + '.json')
    record = dict(run_id=run_id, sha=sha, suite=args.suite,
                  started=started.isoformat(), tree_before=git('status', '--porcelain'),
                  status='running', interpreter=sys.executable,
                  font_sha256=hashlib.sha256(Path(args.font).read_bytes()).hexdigest(),
                  release_eligible=False)
    record_path.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    env = {k:v for k,v in os.environ.items() if k.upper() in {
        'SYSTEMROOT','WINDIR','PATH','PATHEXT','COMSPEC','USERPROFILE','APPDATA',
        'LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)','PROCESSOR_ARCHITECTURE',
        'NUMBER_OF_PROCESSORS'}}
    env['BRAMBLELOOP_FONT_PATH'] = str(Path(args.font).resolve())
    env['PYTHONIOENCODING'] = 'utf-8'
    code = 'import sys,runpy; sys.path.insert(0,sys.argv[1]); runpy.run_path(sys.argv[2],run_name="__main__")'
    result = 1
    with tempfile.TemporaryDirectory(prefix='codex_final_suite_') as scratch:
        env.update(TEMP=scratch, TMP=scratch, TMPDIR=scratch)
        try:
            with log.open('wb') as stream:
                run = subprocess.run([sys.executable, '-u', '-c', code, args.deps, str(suite)],
                                     cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                     timeout=args.timeout)
            result = run.returncode
            record.update(status='passed' if result == 0 else 'failed', exit_code=result)
        except subprocess.TimeoutExpired:
            record.update(status='timeout', exit_code=None)
    record.update(finished=datetime.now(timezone.utc).isoformat(),
                  head_after=git('rev-parse', 'HEAD'), log=log.name,
                  log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    if record['head_after'] != sha:
        record['status'] = 'invalid_source_changed'
        result = 1
    record_path.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(record, indent=2))
    print(log.read_text(encoding='utf-8', errors='replace')[-5000:])
    return result


if __name__ == '__main__':
    raise SystemExit(main())
