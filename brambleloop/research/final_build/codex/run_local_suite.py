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


def source_fingerprint(root):
    """Bind executed sources, including uncommitted and newly added test/module files.

    HEAD alone cannot detect concurrent edits. Evidence outputs and bytecode are excluded
    because the run itself creates those; Python/config/test inputs are included.
    """
    root = root.resolve()
    files = set()
    for directory in (root / 'src', root / 'tests'):
        files.update(p for p in directory.rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix != '.pyc')
    files.update(p for p in root.glob('*') if p.is_file()
                 and p.suffix in {'.py', '.sh', '.toml', '.lock', '.txt', '.ini', '.cfg'})
    files.add(Path(__file__).resolve())
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


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
                  source_before=source_fingerprint(root),
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
    code = ('import sys,runpy; sys.path[:0]=[sys.argv[1],sys.argv[2],sys.argv[3]]; '
            'runpy.run_path(sys.argv[4],run_name="__main__")')
    result = 1
    with tempfile.TemporaryDirectory(prefix='codex_final_suite_') as scratch:
        env.update(TEMP=scratch, TMP=scratch, TMPDIR=scratch)
        try:
            with log.open('wb') as stream:
                run = subprocess.run([sys.executable, '-u', '-c', code, args.deps,
                                      str(root / 'src'), str(root / 'tests'), str(suite)],
                                     cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                     timeout=args.timeout)
            result = run.returncode
            record.update(status='passed' if result == 0 else 'failed', exit_code=result)
        except subprocess.TimeoutExpired:
            record.update(status='timeout', exit_code=None)
    record.update(finished=datetime.now(timezone.utc).isoformat(),
                  source_after=source_fingerprint(root),
                  head_after=git('rev-parse', 'HEAD'), log=log.name,
                  log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    if record['head_after'] != sha or record['source_before'] != record['source_after']:
        record['status'] = 'invalid_source_changed'
        result = 1
    record_path.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(record, indent=2))
    print(log.read_text(encoding='utf-8', errors='replace')[-5000:])
    return result


if __name__ == '__main__':
    raise SystemExit(main())
