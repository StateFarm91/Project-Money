"""A CPU face embedder for the identity biometric floor (ENG-VIS-IDENTITY, option (a)).

Two small ONNX models from the OpenCV model zoo, run with `onnxruntime` and numpy only (no
OpenCV dependency):

* **YuNet** `face_detection_yunet_2023mar.onnx` (MIT licence, Shiqi Yu): finds the face and
  its five landmarks (eyes, nose tip, mouth corners).
* **SFace** `face_recognition_sface_2021dec.onnx` (Apache-2.0, Yaoyao Zhong / OpenCV zoo): a
  MobileFaceNet trained with the SFace loss; 128-d embedding of a 112x112 aligned face.

Both licences permit commercial use. InsightFace's ArcFace weights (buffalo_l, antelopev2) are
NOT used: their model licence is non-commercial research only.

The weights are never committed. `scripts/fetch_face_models.py` downloads them and this module
refuses any file whose sha256 is not the pinned one (`MODELS`). A missing or altered model is
`FaceModelUnavailable`, which `identity_gate.measure_biometric` turns into UNMEASURED -- never
PASS.

Interface (consumed by `identity_gate.measure_biometric` and `vision_judges.Adapters`):

    emb = SFaceEmbedder.load(model_dir)        # raises FaceModelUnavailable
    emb.name, emb.version, emb.weights_sha256  # matched against the qualification record
    emb.embed(image_bytes) -> list[float]      # raises NoFace / MultipleFaces
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

EMBEDDER_NAME = "sface-yunet-onnx"
EMBEDDER_VERSION = "sface_2021dec+yunet_2023mar/1"

MODELS = {
    "detector": {
        "file": "face_detection_yunet_2023mar.onnx",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "url": ("https://huggingface.co/opencv/face_detection_yunet/resolve/main/"
                "face_detection_yunet_2023mar.onnx"),
        "licence": "MIT (Copyright (c) 2020 Shiqi Yu)",
        "bytes": 232589,
    },
    "recogniser": {
        "file": "face_recognition_sface_2021dec.onnx",
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "url": ("https://huggingface.co/opencv/face_recognition_sface/resolve/main/"
                "face_recognition_sface_2021dec.onnx"),
        "licence": "Apache-2.0 (OpenCV model zoo)",
        "bytes": 38696353,
    },
}


def weights_sha256() -> str:
    """One hash for the pair: sha256 of 'detector_sha:recogniser_sha'."""
    return hashlib.sha256(f"{MODELS['detector']['sha256']}:{MODELS['recogniser']['sha256']}"
                          .encode()).hexdigest()


DEFAULT_MODEL_DIR = os.environ.get("BRAMBLELOOP_FACE_MODEL_DIR", "/app/models/face")

# ArcFace/SFace canonical 5-point template for a 112x112 crop.
_TEMPLATE = ((38.2946, 51.6963), (73.5318, 51.5014), (56.0252, 71.7366),
             (41.5493, 92.3655), (70.7299, 92.2041))
DET_SIZE = 640
DET_SCORE = 0.6
NMS_IOU = 0.3
# A second face this large relative to the largest is a second person, not background noise.
SECOND_FACE_RATIO = 0.5
MIN_FACE_PX = 24


class FaceModelUnavailable(RuntimeError):
    pass


class NoFace(ValueError):
    pass


class MultipleFaces(ValueError):
    pass


def _verify(path: Path, want: str) -> None:
    if not path.is_file():
        raise FaceModelUnavailable(f"{path.name} is not installed at {path.parent} "
                                   f"(run scripts/fetch_face_models.py)")
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    if h != want:
        raise FaceModelUnavailable(f"{path.name} sha256 {h[:12]} is not the pinned {want[:12]}")


def _nms(boxes, scores, iou):
    import numpy as np

    order = np.argsort(-scores)
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        xx1 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy1 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx2 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy2 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        a = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        b = (boxes[order[1:], 2] - boxes[order[1:], 0]) * (boxes[order[1:], 3] - boxes[order[1:], 1])
        order = order[1:][inter / (a + b - inter + 1e-9) <= iou]
    return keep


def similarity_transform(src, dst):
    """Umeyama: the 2x3 similarity matrix mapping src points onto dst points."""
    import numpy as np

    src, dst = np.asarray(src, float), np.asarray(dst, float)
    mu_s, mu_d = src.mean(0), dst.mean(0)
    s_c, d_c = src - mu_s, dst - mu_d
    cov = d_c.T @ s_c / len(src)
    u, sig, vt = np.linalg.svd(cov)
    d = np.ones(2)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        d[-1] = -1
    r = u @ np.diag(d) @ vt
    var = (s_c ** 2).sum() / len(src)
    scale = (sig * d).sum() / var
    t = mu_d - scale * r @ mu_s
    return np.hstack([scale * r, t[:, None]])


class SFaceEmbedder:
    name = EMBEDDER_NAME
    version = EMBEDDER_VERSION

    def __init__(self, det, rec):
        self._det, self._rec = det, rec
        self.weights_sha256 = weights_sha256()

    @classmethod
    def load(cls, model_dir: str | os.PathLike | None = None) -> "SFaceEmbedder":
        d = Path(model_dir or DEFAULT_MODEL_DIR)
        for m in MODELS.values():
            _verify(d / m["file"], m["sha256"])
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise FaceModelUnavailable("onnxruntime is not installed") from exc
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = int(os.environ.get("BRAMBLELOOP_FACE_THREADS", "1"))
        opts.log_severity_level = 3
        # RAM budget (~120 MB over the worker): no pre-grown CPU arena, no pattern cache.
        opts.enable_cpu_mem_arena = False
        opts.enable_mem_pattern = False
        mk = lambda f: ort.InferenceSession(str(d / f), sess_options=opts,  # noqa: E731
                                            providers=["CPUExecutionProvider"])
        return cls(mk(MODELS["detector"]["file"]), mk(MODELS["recogniser"]["file"]))

    # -- detection
    def detect(self, img) -> list[dict]:
        """Faces in a PIL RGB image: [{box, score, landmarks}] in image pixels, largest first."""
        import numpy as np
        from PIL import Image

        w, h = img.size
        scale = DET_SIZE / max(w, h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        canvas = Image.new("RGB", (DET_SIZE, DET_SIZE), (0, 0, 0))
        canvas.paste(img.resize((nw, nh), Image.BILINEAR), (0, 0))
        arr = np.asarray(canvas, dtype=np.float32)[:, :, ::-1]          # BGR, 0..255
        blob = np.ascontiguousarray(arr.transpose(2, 0, 1)[None])
        outs = dict(zip([o.name for o in self._det.get_outputs()],
                        self._det.run(None, {self._det.get_inputs()[0].name: blob})))
        boxes, scores, kpss = [], [], []
        for s in (8, 16, 32):
            cols = DET_SIZE // s
            cls_, obj = outs[f"cls_{s}"][0, :, 0], outs[f"obj_{s}"][0, :, 0]
            bb, kp = outs[f"bbox_{s}"][0], outs[f"kps_{s}"][0]
            score = np.sqrt(np.clip(cls_, 0, 1) * np.clip(obj, 0, 1))
            idx = np.nonzero(score >= DET_SCORE)[0]
            for i in idx:
                r, c = divmod(int(i), cols)
                cx, cy = (c + bb[i, 0]) * s, (r + bb[i, 1]) * s
                bw, bh = np.exp(bb[i, 2]) * s, np.exp(bb[i, 3]) * s
                boxes.append([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2])
                scores.append(float(score[i]))
                kpss.append([((kp[i, 2 * n] + c) * s, (kp[i, 2 * n + 1] + r) * s)
                             for n in range(5)])
        if not boxes:
            return []
        boxes_a, scores_a = np.array(boxes), np.array(scores)
        out = []
        for k in _nms(boxes_a, scores_a, NMS_IOU):
            b = boxes_a[k] / scale
            out.append({"box": [float(x) for x in b], "score": round(scores[k], 4),
                        "landmarks": [(x / scale, y / scale) for x, y in kpss[k]]})
        out.sort(key=lambda f: -(f["box"][2] - f["box"][0]) * (f["box"][3] - f["box"][1]))
        return out

    # -- alignment and embedding
    @staticmethod
    def align(img, landmarks):
        import numpy as np
        from PIL import Image

        m = similarity_transform(landmarks, _TEMPLATE)
        inv = np.linalg.inv(np.vstack([m, [0, 0, 1]]))[:2]
        return img.transform((112, 112), Image.AFFINE, tuple(inv.flatten()), Image.BILINEAR)

    def embed_face(self, aligned) -> list[float]:
        import numpy as np

        arr = np.asarray(aligned.convert("RGB"), dtype=np.float32)           # RGB, 0..255
        blob = np.ascontiguousarray(arr.transpose(2, 0, 1)[None])
        vec = self._rec.run(None, {self._rec.get_inputs()[0].name: blob})[0][0]
        n = float(np.linalg.norm(vec))
        if n == 0:
            raise NoFace("zero embedding")
        return [float(x) / n for x in vec]

    def faces(self, data: bytes):
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        return img, [f for f in self.detect(img)
                     if min(f["box"][2] - f["box"][0], f["box"][3] - f["box"][1]) >= MIN_FACE_PX]

    def embed(self, data: bytes) -> list[float]:
        """The embedding of the one person in the image. No face or two people: refused."""
        img, faces = self.faces(data)
        if not faces:
            raise NoFace("no face found")
        if len(faces) > 1:
            area = lambda f: (f["box"][2] - f["box"][0]) * (f["box"][3] - f["box"][1])  # noqa
            if area(faces[1]) >= SECOND_FACE_RATIO * area(faces[0]):
                raise MultipleFaces(f"{len(faces)} faces; identity needs exactly one person")
        return self.embed_face(self.align(img, faces[0]["landmarks"]))


def cosine(a, b) -> float:
    import math

    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def try_load(model_dir=None):
    """The embedder, or None with the reason (never raises)."""
    try:
        return SFaceEmbedder.load(model_dir), ""
    except FaceModelUnavailable as exc:
        return None, str(exc)
