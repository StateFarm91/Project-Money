"""E5 — the frozen benchmark package. Every input is the E4 SC camera package, byte for byte,
and `verify()` refuses to let a provider be tested if any digest has moved. The E4 baseline
image is frozen too, because it is the quality floor every candidate is measured against."""
import hashlib, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))

FROZEN = {
    "geometry_npz": ("research/d/out/sc_draped.npz", "3eaae06df07b2a8410a98d84f45a430b32396a50e95aab775b8a61377a3f2f56"),
    "assessment": ("research/d/out/milestone_d_sc_final.json", "4aaca8f9ab5ceb4159026a01353d29d40bb708f8a4389838c20409ca4cae8a24"),
    "reference_rgb": ("research/d/out/sc_draped_presentation3_camera.png", "acdfc2d869dac12780a8f363e8beff8886866633f120c153c4d97b66a2d348db"),
    "mask": ("research/e4/out/sc_camera_mask.png", "c0980cec58e3e8b960d436a0c7798720a1f4469bf052a3e6834560633ba4f9eb"),
    "normal": ("research/e4/out/sc_camera_normal.png", "8d3b03ecaab2e416ede9cb7661a113af0e034f457f2850359ef4ca42cbc1e9f3"),
    "depth_npz": ("research/e4/out/sc_camera_depth.npz", "1c191852de387958a7b714756dae45a4225dd84910bea469cec3c3cd44ad0c5e"),
    "manifest": ("research/e4/out/sc_camera_manifest.json", "c9b35caf4201b7704d957ec8b26b5dc4b2825ffa6182b0bc7058e9efdabd9989"),
    "e4_baseline": ("research/e4/out/gen/sc_camera_e4.png", "46eebcecd2c19e123c358f7da9f7c76e8c48035f65e22c972fb73db43d0eaf40"),
}
GEOMETRY_SHA256 = "e0762cc081abbda5b602bab8c4dff097aeacbc7786891c0785108d073860c433"  # draped points, as milestone_d_sc_final.json records


def path(key: str) -> str:
    return os.path.join(ROOT, FROZEN[key][0])


def sha256(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def verify() -> dict:
    """Every frozen file's digest, or a RuntimeError naming the one that moved."""
    out = {}
    for key, (rel, want) in FROZEN.items():
        got = sha256(os.path.join(ROOT, rel))
        if got != want:
            raise RuntimeError(f"frozen input {key} ({rel}) has changed: {got} != {want}; E5 does not run on a moved benchmark")
        out[key] = got
    return out


if __name__ == "__main__":
    for k, v in verify().items():
        print(f"OK   {k} {v[:16]}")
