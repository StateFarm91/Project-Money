"""Run selected existing tests offline, without editing them. All output persisted."""
import argparse,hashlib,json,os,runpy,socket,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
ap=argparse.ArgumentParser();ap.add_argument("--deps",required=True)
ap.add_argument("--child",choices=["test_closure","test_cert_orders","test_cert_growth_ops","test_cert_dependencies","test_cert_takeover","test_cert_trend_evidence","test_moat"])
args=ap.parse_args();deps=str(Path(args.deps).resolve())
if args.child:
    sys.path[:0]=[deps,str(ROOT/"src"),str(ROOT)]
    for k in list(os.environ):
        if k.startswith(("ANTHROPIC","OPENAI","ETSY","GEMINI","GOOGLE_API","DATABASE_URL","BRAMBLELOOP_DATABASE")):os.environ.pop(k,None)
    os.environ.update(BRAMBLELOOP_PHASE="shadow",BRAMBLELOOP_REQUIRE_POSTGRES="0",PYTHONDONTWRITEBYTECODE="1")
    def blocked(*a,**k):raise RuntimeError("Network forbidden by isolated Codex harness")
    socket.socket.connect=blocked;socket.socket.connect_ex=blocked;socket.create_connection=blocked
    runpy.run_path(str(ROOT/"tests"/(args.child+".py")),run_name="__main__")
else:
    out=HERE/"out";out.mkdir(exist_ok=True);results=[]
    for name in ["test_closure","test_cert_orders","test_cert_growth_ops","test_cert_dependencies","test_cert_takeover","test_cert_trend_evidence","test_moat"]:
        start=time.perf_counter()
        try:
            p=subprocess.run([sys.executable,str(Path(__file__).resolve()),"--deps",deps,"--child",name],
              cwd=ROOT,capture_output=True,timeout=240)
            raw=p.stdout+p.stderr;rc=p.returncode
        except subprocess.TimeoutExpired as e:
            raw=(e.stdout or b"")+(e.stderr or b"")+b"\nTIMEOUT";rc=124
        (out/(name+".log")).write_bytes(raw)
        result={"suite":name,"returncode":rc,"seconds":round(time.perf_counter()-start,3),
          "test_sha256":hashlib.sha256((ROOT/"tests"/(name+".py")).read_bytes()).hexdigest(),
          "output_sha256":hashlib.sha256(raw).hexdigest(),"tail":raw.decode("utf-8","replace").splitlines()[-5:]}
        results.append(result);print(json.dumps(result),flush=True)
        (out/"focused_suites.json").write_text(json.dumps({"base":"4edacff1f8b445a84749464dc1d7271e6c71173e","results":results,
          "note":"Existing scripts unchanged. Exit0 is that suite result, not certification. Offline local environment."},indent=2)+"\n",encoding="utf-8",newline="\n")
