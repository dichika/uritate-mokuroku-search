"""OCR結果とマニフェストのメタデータから検索インデックス docs/data/index.json を生成する。

使い方:
    python3 pipeline/build_index.py

インデックス構造:
{
  "documents": [
    {
      "id": "UCB-N7352-B558-0146",
      "title": "...", "titleReading": "...", "year": "1917", "yearJa": "大正０６",
      "genre": "...", "owner": "...", "code": "...",
      "commentary": "...",       # 資料単位の検索対象（マニフェストの description 等）
      "viewerUrl": "...", "detailUrl": "...",
      "pages": [
        {
          "n": 1,                # コマ番号（マニフェストのcanvas順）
          "label": "p.1",        # マニフェスト上のラベル
          "name": "UCB-N7352-B558-0146_001",
          "iiif": "https://.../iiif/berkeley%21ac%21...%21UCB-N7352-B558-0146_001/",  # IIIF service base
          "w": 2700, "h": 2107,
          "lines": [ {"t": "行テキスト", "b": [x, y, w, h], "c": 0.51}, ... ],
          "ai": ["AI翻刻行", ...]   # data/{id}/ai/{name}.txt があるページのみ
        }, ...
      ]
    }
  ]
}
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


def main() -> None:
    documents = [build_document(book_id) for book_id in config.BOOK_IDS]
    config.INDEX_JSON.parent.mkdir(parents=True, exist_ok=True)
    config.INDEX_JSON.write_text(
        json.dumps({"documents": documents}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    n_pages = sum(len(d["pages"]) for d in documents)
    n_lines = sum(len(p["lines"]) for d in documents for p in d["pages"])
    size_kb = config.INDEX_JSON.stat().st_size // 1024
    print(f"index.json 生成: 資料{len(documents)}点 / {n_pages}ページ / {n_lines}行 / {size_kb} KB")


if __name__ == "__main__":
    main()
