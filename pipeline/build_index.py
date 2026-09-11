"""OCR結果とマニフェストのメタデータから検索インデックスを生成する。

使い方:
    python3 pipeline/build_index.py

320件規模の資料を扱うため、インデックスは3種類に分割して生成する
（単一ファイルのままではスマホの初回読み込みに耐えないため。作業設計書 §1.3）。

- docs/data/catalog.json: 全冊の書誌一覧（起動時に読む）。
    {"documents": [{id, title, titleReading, year, yearJa, genre, owner, code,
                     commentary, pages, viewerUrl, detailUrl}, ...]}
    "pages" はコマ数（整数）である。
- docs/data/search.json: 全冊の本文（起動時に読む。座標は含めない軽量版）。
    {"books": [{"id": "...", "p": [[コマ番号, "行テキスト"], ...]}, ...]}
    OCR行・AI翻刻行の両方を含む（表示上の区別は行わない。区別が必要な場合は
    オーバーレイ表示時に取得する books/{book_id}.json 側の情報を使う）。
- docs/data/books/{book_id}.json: 資料1冊分の全データ（座標・OCR/AI区別つき）。
    { id, title, ..., pages: [{n, label, name, iiif, w, h, lines: [...], ai: [...]}, ...] }
    docs/index.html がオーバーレイ表示時に遅延取得してキャッシュする。
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from fetch import canvas_entries


def bbox_to_xywh(bounding_box: list) -> list:
    xs = [p[0] for p in bounding_box]
    ys = [p[1] for p in bounding_box]
    x0, y0 = max(0, min(xs)), max(0, min(ys))
    return [x0, y0, max(xs) - x0, max(ys) - y0]


# 認識崩壊行（同一文字の長い繰り返し）は検索ノイズになるためインデックスから除外する。
DEGENERATE_RE = re.compile(r"(.)\1{4,}")


def is_degenerate(text: str) -> bool:
    return bool(DEGENERATE_RE.search(text))


def load_page_lines(ocr_json_path: Path) -> list[dict]:
    data = json.loads(ocr_json_path.read_text(encoding="utf-8"))
    lines = []
    for block in data.get("contents", []):
        for line in block:
            text = (line.get("text") or "").strip()
            if not text or is_degenerate(text):
                continue
            lines.append(
                {
                    "t": text,
                    "b": bbox_to_xywh(line["boundingBox"]),
                    "c": round(float(line.get("confidence", 0)), 3),
                }
            )
    return lines


def load_ai_lines(ai_txt_path: Path) -> list[str]:
    """AI翻刻（Claudeによる目視翻刻）。1行1列のプレーンテキスト。"""
    if not ai_txt_path.exists():
        return []
    return [
        line.strip()
        for line in ai_txt_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def metadata_map(manifest: dict) -> dict[str, list[str]]:
    """IIIF Presentation 2 の metadata 配列を {label: [値, ...]} に平坦化する。"""
    result: dict[str, list[str]] = {}
    for item in manifest.get("metadata", []):
        label = item.get("label")
        value = item.get("value")
        values: list[str] = []
        if isinstance(value, list):
            for v in value:
                values.append(v.get("@value") if isinstance(v, dict) else str(v))
        elif value is not None:
            values.append(str(value))
        result[label] = [v for v in values if v]
    return result


def first(md: dict, label: str, idx: int = 0) -> str | None:
    vals = md.get(label) or []
    return vals[idx] if len(vals) > idx else None


def build_document(book_id: str) -> dict:
    """資料1冊分の全データ（books/{book_id}.json の内容）を組み立てる。"""
    bdir = config.book_dir(book_id)
    manifest = json.loads((bdir / "manifest.json").read_text(encoding="utf-8"))
    md = metadata_map(manifest)

    pages = []
    for n, entry in enumerate(canvas_entries(manifest), start=1):
        ocr_path = config.ocr_dir(book_id) / f"{entry['name']}.json"
        lines = load_page_lines(ocr_path) if ocr_path.exists() else []
        if not ocr_path.exists():
            print(f"  警告: OCR結果なし {ocr_path.name}", file=sys.stderr)
        page = {
            "n": n,
            "label": entry["label"],
            "name": entry["name"],
            "iiif": entry["service_base"],
            "w": entry["width"],
            "h": entry["height"],
            "lines": lines,
        }
        ai_lines = load_ai_lines(bdir / "ai" / f"{entry['name']}.txt")
        if ai_lines:
            page["ai"] = ai_lines
        pages.append(page)

    title = first(md, "Title") or manifest.get("label") or book_id
    year = first(md, "Publication Date", 0)
    year_ja = first(md, "Publication Date", 1)
    reading = first(md, "Title (reading)")
    genre = first(md, "Genre")
    owner = first(md, "Owner") or manifest.get("attribution")
    commentary_parts = [
        p for p in [
            f"{title}（{reading}）" if reading else title,
            f"刊行: {year_ja} / {year}" if year_ja else (f"刊行: {year}" if year else None),
            f"ジャンル: {genre}" if genre else None,
            f"所蔵: {owner}" if owner else None,
        ] if p
    ]
    return {
        "id": book_id,
        "title": title,
        "titleReading": reading,
        "year": year,
        "yearJa": year_ja,
        "genre": genre,
        "owner": owner,
        "code": first(md, "Call Number") or book_id,
        "commentary": "。".join(commentary_parts) + "。",
        "viewerUrl": config.VIEWER_URL_TMPL.format(book_id=book_id),
        "detailUrl": config.PORTAL_URL_TMPL.format(book_id=book_id),
        "pages": pages,
    }


def catalog_entry(doc: dict) -> dict:
    """docs/data/catalog.json 用に、書誌情報だけを抜き出す（pagesはコマ数に圧縮）。"""
    return {
        "id": doc["id"],
        "title": doc["title"],
        "titleReading": doc["titleReading"],
        "year": doc["year"],
        "yearJa": doc["yearJa"],
        "genre": doc["genre"],
        "owner": doc["owner"],
        "code": doc["code"],
        "commentary": doc["commentary"],
        "pages": len(doc["pages"]),
        "viewerUrl": doc["viewerUrl"],
        "detailUrl": doc["detailUrl"],
    }


def search_entry(doc: dict) -> dict:
    """docs/data/search.json 用に、本文だけを軽量な形（座標なし）で抜き出す。"""
    p: list[list] = []
    for page in doc["pages"]:
        for line in page["lines"]:
            p.append([page["n"], line["t"]])
        for text in page.get("ai", []):
            p.append([page["n"], text])
    return {"id": doc["id"], "p": p}


def main() -> None:
    book_ids = config.done_book_ids()
    documents = [build_document(book_id) for book_id in book_ids]

    config.DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.BOOKS_DIR.mkdir(parents=True, exist_ok=True)

    catalog = {"documents": [catalog_entry(d) for d in documents]}
    config.CATALOG_JSON.write_text(
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    search = {"books": [search_entry(d) for d in documents]}
    config.SEARCH_JSON.write_text(
        json.dumps(search, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    # 既存キューの book_id 一覧に無くなった資料の books/*.json は残置してもUIから参照されないだけで
    # 実害はないため、削除は行わない（誤って全消去する事故を避ける）。
    for doc in documents:
        (config.BOOKS_DIR / f"{doc['id']}.json").write_text(
            json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )

    n_pages = sum(len(d["pages"]) for d in documents)
    n_lines = sum(len(p["lines"]) + len(p.get("ai", [])) for d in documents for p in d["pages"])
    catalog_kb = config.CATALOG_JSON.stat().st_size // 1024
    search_kb = config.SEARCH_JSON.stat().st_size // 1024
    print(
        f"インデックス生成: 資料{len(documents)}点 / {n_pages}ページ / {n_lines}行 / "
        f"catalog.json {catalog_kb}KB / search.json {search_kb}KB / "
        f"books/*.json {len(documents)}冊分"
    )


if __name__ == "__main__":
    main()
