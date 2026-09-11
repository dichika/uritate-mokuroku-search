"""NDLOCR-Lite（活字向け）で全資料の画像をOCRする。

使い方:
    python3 pipeline/run_ocr.py

tools/ndlocr-lite の CLI (src/ocr.py) をディレクトリ一括モードで .venv の Python から呼び出し、
結果（json/txt/xml）を data/{book_id}/ocr/ に保存する。
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


def run_ocr(book_id: str) -> None:
    src_dir = config.OCR_TOOL_DIR / "src"
    images = config.images_dir(book_id)
    out = config.ocr_dir(book_id)
    out.mkdir(parents=True, exist_ok=True)

    n_images = len(list(images.glob("*.jpg")))
    done = {p.stem for p in out.glob("*.json")}
    if len(done) >= n_images and n_images > 0:
        print(f"[{book_id}] OCR済み ({len(done)}/{n_images}) スキップ")
        return

    print(f"[{book_id}] OCR開始: {n_images} 画像", flush=True)
    subprocess.run(
        [
            str(config.OCR_PYTHON),
            "ocr.py",
            "--sourcedir",
            str(images),
            "--output",
            str(out),
        ],
        cwd=src_dir,
        check=True,
    )
    n_out = len(list(out.glob("*.json")))
    print(f"[{book_id}] OCR完了: {n_out}/{n_images} 件のJSONを出力")


def main() -> None:
    for book_id in config.done_book_ids():
        run_ocr(book_id)


if __name__ == "__main__":
    main()
