"""IIIFマニフェストと全ページ画像を取得する。

使い方:
    python3 pipeline/fetch.py

注意:
    dh-jac.net のマニフェストは自動アクセスに対して HTTP 429 を返すことがある。
    その場合はブラウザでマニフェストを開いて data/{book_id}/manifest.json に保存してから
    再実行する（既存ファイルがあればダウンロードをスキップする）。
    画像は arc.ritsumei.ac.jp の IIIF Image API から取得する。
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as res:
        return res.read()


def fetch_manifest(book_id: str) -> dict:
    dest = config.book_dir(book_id) / "manifest.json"
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))
    url = config.MANIFEST_URL_TMPL.format(book_id=book_id)
    try:
        data = http_get(url)
    except urllib.error.HTTPError as e:
        sys.exit(
            f"マニフェスト取得失敗 HTTP {e.code}: {url}\n"
            f"ブラウザで開いて {dest} に保存してから再実行してください。"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    time.sleep(config.REQUEST_WAIT_SEC)
    return json.loads(data.decode("utf-8"))


def canvas_entries(manifest: dict) -> list[dict]:
    """manifest から (画像名, ラベル, IIIF service base URL, 幅, 高さ) を順に取り出す。"""
    entries = []
    for canvas in manifest["sequences"][0]["canvases"]:
        resource = canvas["images"][0]["resource"]
        service_base = resource["service"]["@id"]
        if not service_base.endswith("/"):
            service_base += "/"
        # 例: .../iiif/berkeley%21ac%21N7352-B558-0146%21UCB-N7352-B558-0146_001/
        #     → UCB-N7352-B558-0146_001
        ident = service_base.rstrip("/").split("/")[-1]
        name = ident.replace("%21", "!").split("!")[-1]
        entries.append(
            {
                "name": name,
                "label": canvas.get("label"),
                "service_base": service_base,
                "width": resource.get("width") or canvas.get("width"),
                "height": resource.get("height") or canvas.get("height"),
            }
        )
    return entries


def fetch_book(book_id: str) -> None:
    manifest = fetch_manifest(book_id)
    entries = canvas_entries(manifest)
    img_dir = config.images_dir(book_id)
    img_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{book_id}] {manifest.get('label')} : {len(entries)} 画像")

    for i, entry in enumerate(entries, start=1):
        dest = img_dir / f"{entry['name']}.jpg"
        if dest.exists() and dest.stat().st_size > 0:
            continue
        url = config.IIIF_FULL_IMAGE_TMPL.format(base=entry["service_base"])
        dest.write_bytes(http_get(url))
        print(f"  {i}/{len(entries)} {dest.name} ({dest.stat().st_size // 1024} KB)", flush=True)
        time.sleep(config.REQUEST_WAIT_SEC)


def main() -> None:
    for book_id in config.BOOK_IDS:
        fetch_book(book_id)
    print("完了")


if __name__ == "__main__":
    main()
