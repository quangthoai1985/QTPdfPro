"""Dựng bộ mô hình OCR tiếng Việt `QTPdfPro_OCR_vi_v<N>.zip` để đăng lên GitHub Release (mục B3/V5).

Ứng dụng KHÔNG kèm mô hình trong bộ cài: lần đầu dùng OCR, `core/ocr_models.py` tải tệp zip này (kiểm SHA-256)
rồi giải nén vào `%LOCALAPPDATA%\\QTPdfPro\\modules\\ocr-vi-<N>\\`.

Chạy trong môi trường RIÊNG (không phải môi trường của ứng dụng) vì cần PyTorch + VietOCR:

    uv venv --python 3.13 .venv-ocr-export
    uv pip install --python .venv-ocr-export/Scripts/python.exe torch torchvision onnx onnxruntime pillow pyyaml requests gdown prefetch_generator einops
    uv pip install --python .venv-ocr-export/Scripts/python.exe --no-deps vietocr
    .venv-ocr-export/Scripts/python.exe tools/export_ocr_models.py <thư mục ra>

Nội dung tệp zip (phẳng, không thư mục con):
- `ppocrv6_det_small.onnx` — PP-OCRv6 det small (Apache-2.0), bản ONNX của RapidOCR 3.10, tìm dòng chữ.
- `vietocr_seq2seq_encoder.onnx` + `vietocr_seq2seq_decoder.onnx` — VietOCR `vgg_seq2seq` (Apache-2.0) tách thành
  bộ mã hoá ảnh và MỘT bước giải mã (vòng giải mã tham lam viết bằng numpy trong `core/ocr.py`).
- `vietocr_vocab.txt` — bảng ký tự (chỉ số = vị trí + 4; 0 pad, 1 bắt đầu, 2 kết thúc, 3 mask).
- `manifest.json` — tham số tiền xử lý / hậu xử lý + SHA-256 từng tệp; `NOTICE.txt` — nguồn và giấy phép.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

BUNDLE_VERSION = 1
ZIP_NAME = f"QTPdfPro_OCR_vi_v{BUNDLE_VERSION}.zip"

DET_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv6/det/PP-OCRv6_det_small.onnx"
DET_SHA256 = "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f"  # rapidocr 3.10 default_models.yaml
VIETOCR_WEIGHTS = "https://vocr.vn/data/vietocr/vgg_seq2seq.pth"

DET_FILE = "ppocrv6_det_small.onnx"
ENC_FILE = "vietocr_seq2seq_encoder.onnx"
DEC_FILE = "vietocr_seq2seq_decoder.onnx"
VOCAB_FILE = "vietocr_vocab.txt"

NOTICE = """Bộ mô hình OCR tiếng Việt của QT PDF Pro (https://github.com/quangthoai1985/QTPdfPro)

1. ppocrv6_det_small.onnx — PP-OCRv6 det small của PaddleOCR (https://github.com/PaddlePaddle/PaddleOCR),
   giấy phép Apache-2.0; bản ONNX do RapidOCR (https://github.com/RapidAI/RapidOCR, Apache-2.0) chuyển đổi.
2. vietocr_seq2seq_encoder.onnx, vietocr_seq2seq_decoder.onnx, vietocr_vocab.txt — mô hình vgg_seq2seq của
   VietOCR (https://github.com/pbcquoc/vietocr, Apache-2.0, tác giả Phạm Bá Cường Quốc), trọng số gốc
   https://vocr.vn/data/vietocr/vgg_seq2seq.pth, chuyển sang ONNX bằng tools/export_ocr_models.py của QT PDF Pro.

Toàn văn giấy phép Apache-2.0: https://www.apache.org/licenses/LICENSE-2.0
"""


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "QTPdfPro-export"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)


def export_vietocr(out: Path, work: Path) -> str:
    import torch
    from vietocr.tool.config import Cfg
    from vietocr.tool.translate import build_model

    cfg = Cfg.load_config_from_name("vgg_seq2seq")
    cfg["device"] = "cpu"
    cfg["cnn"]["pretrained"] = False  # không tải trọng số ImageNet (549 MB) — bị ghi đè ngay sau đó
    weights = work / "vgg_seq2seq.pth"
    if not weights.exists():
        download(VIETOCR_WEIGHTS, weights)
    model, _vocab = build_model(cfg)
    model.load_state_dict(torch.load(weights, map_location="cpu"))
    model.eval()

    class Encoder(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, img):
            # như Vgg.forward nhưng chỉ số chiều không âm: ONNX Runtime từ chối Transpose có perm âm
            vgg = self.m.cnn.model
            conv = vgg.last_conv_1x1(vgg.dropout(vgg.features(img)))
            conv = conv.transpose(2, 3).flatten(2).permute(2, 0, 1)
            hidden, enc_out = self.m.transformer.forward_encoder(conv)
            return hidden, enc_out

    class Decoder(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, token, hidden, enc_out):
            out, hidden, _ = self.m.transformer.decoder(token, hidden, enc_out)
            return out, hidden

    img = torch.rand(1, 3, 32, 320)
    with torch.no_grad():
        hidden, enc_out = Encoder(model)(img)
        torch.onnx.export(Encoder(model), (img,), out / ENC_FILE, input_names=["img"],
                          output_names=["hidden", "enc_out"], dynamic_axes={"img": {3: "w"}, "enc_out": {0: "t"}},
                          opset_version=17, dynamo=False)
        torch.onnx.export(Decoder(model), (torch.tensor([1]), hidden, enc_out), out / DEC_FILE,
                          input_names=["token", "hidden", "enc_out"], output_names=["logits", "hidden_out"],
                          dynamic_axes={"enc_out": {0: "t"}}, opset_version=17, dynamo=False)
    _check_vietocr(model, out)
    return cfg["vocab"]


def _check_vietocr(model, out: Path) -> None:
    """Giải mã ONNX phải trùng PyTorch trên vài ảnh ngẫu nhiên có độ rộng khác nhau."""
    import numpy as np
    import onnxruntime as ort
    import torch
    from vietocr.tool.translate import translate

    enc = ort.InferenceSession(str(out / ENC_FILE), providers=["CPUExecutionProvider"])
    dec = ort.InferenceSession(str(out / DEC_FILE), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(0)
    for w in (40, 200, 512):
        x = rng.random((1, 3, 32, w), dtype=np.float32)
        ref, _ = translate(torch.from_numpy(x), model)
        hidden, enc_out = enc.run(None, {"img": x})
        toks = [1]
        for _ in range(128):
            logits, hidden = dec.run(None, {"token": np.array([toks[-1]], dtype=np.int64), "hidden": hidden, "enc_out": enc_out})
            toks.append(int(logits[0].argmax()))
            if toks[-1] == 2:
                break
        if toks != ref[0].tolist()[: len(toks)]:
            raise SystemExit(f"ONNX lệch PyTorch ở ảnh rộng {w}: {toks} vs {ref[0].tolist()}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir", type=Path)
    args = ap.parse_args()
    out = args.out_dir / f"ocr-vi-{BUNDLE_VERSION}"
    work = args.out_dir / "work"
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    det = out / DET_FILE
    if not det.exists() or sha256_of(det) != DET_SHA256:
        download(DET_URL, det)
    if sha256_of(det) != DET_SHA256:
        raise SystemExit("SHA-256 của mô hình PP-OCRv6 det không khớp RapidOCR — dừng.")

    vocab = export_vietocr(out, work)
    (out / VOCAB_FILE).write_text(vocab, encoding="utf-8", newline="\n")
    (out / "NOTICE.txt").write_text(NOTICE, encoding="utf-8", newline="\n")

    files = [DET_FILE, ENC_FILE, DEC_FILE, VOCAB_FILE, "NOTICE.txt"]
    manifest = {
        "id": "ocr-vi",
        "version": BUNDLE_VERSION,
        "detector": {
            "file": DET_FILE, "max_side_len": 2000, "limit_side_len": 736, "mean": [0.5, 0.5, 0.5],
            "std": [0.5, 0.5, 0.5], "thresh": 0.3, "box_thresh": 0.5, "unclip_ratio": 1.6, "max_candidates": 1000,
        },
        "recognizer": {
            "encoder": ENC_FILE, "decoder": DEC_FILE, "vocab": VOCAB_FILE, "image_height": 32,
            "image_min_width": 32, "image_max_width": 512, "max_length": 128,
        },
        "files": {name: {"sha256": sha256_of(out / name), "size": (out / name).stat().st_size} for name in files},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    zip_path = args.out_dir / ZIP_NAME
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in files + ["manifest.json"]:
            zf.write(out / name, name)
    print(f"{zip_path.name}: {zip_path.stat().st_size} byte, SHA-256 {sha256_of(zip_path)}")
    for name, info in manifest["files"].items():
        print(f"  {name}: {info['size']} byte")


if __name__ == "__main__":
    main()
