"""cultural.jp（Cultural Japan）横断検索から「品入札」全件を取得し、取り込みキュー
data/catalog/queue.json を生成・更新する。

使い方:
    python3 pipeline/fetch_catalog.py

キューの各要素:
    {id, book_id, title, manifest, source, access, temporal, provider, status, note, updated}

    provider は "arc"（立命館大学ARC dh-jac.net、第1段階の対象）、
    "ndl"（国立国会図書館デジタルコレクション、第2段階の対象）、
    "other"（画像取得手段が未確立なため対象外）のいずれかである。
    status は "pending"（未取り込み）、"done"（取り込み済み）、
    "skipped"（対象外。理由は note に記す）、"error"（取り込み中に失敗。理由は note に記す）
    のいずれかである。

再実行時は既存要素の status・note・updated を保持し（冪等）、書誌情報（title 等）だけ
最新のAPI応答で更新する。新規に現れた要素は §1.1 の除外規則に従って
pending/skipped を初期設定する。

既存資料 UCB-N7352-B558-0146（佐竹侯爵家御蔵器入札）は cultural.jp の「品入札」検索結果には
含まれない（タイトルが「御蔵器入札」であり「品入札」と一致しないため。2026-09-11 に
api.cultural.jp へ実際に問い合わせて確認した）。作業設計書はこの資料が334件に含まれる前提で
書かれていたが、確認の結果そうではなかったため、この1件は「品入札」検索結果とは別に
status=done で手動追加する。したがってキューの総数は 334＋1＝335件になる
（設計書との差分。詳細は README「資料の追加手順」に記載）。
"""

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

ARC_MANIFEST_RE = re.compile(r"^https://www\.dh-jac\.net/db1/books/(?P<book_id>.+)/portal/manifest\.json$")
NDL_MANIFEST_RE = re.compile(r"^https://www\.dl\.ndl\.go\.jp/api/iiif/(?P<pid>\d+)/manifest\.json$")

# 既存資料（品入札キーワードには含まれないため手動登録する。上記docstring参照）
MANUAL_ENTRIES = [
    {
        "id": "arc_books-UCB_N7352_B558_0146",
        "book_id": "UCB-N7352-B558-0146",
        "title": "佐竹侯爵家御蔵器入札",
        "manifest": "https://www.dh-jac.net/db1/books/UCB-N7352-B558-0146/portal/manifest.json",
        "source": "ARC古典籍ポータルデータベース",
        "access": "カリフォルニア大学バークレー校C. V. スター東アジア図書館",
        "temporal": "1917年",
        "provider": "arc",
        "status": "done",
        "note": "初回導入資料。cultural.jpの「品入札」検索結果には含まれない（タイトルが「御蔵器入札」のため）。",
    },
]


def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode("utf-8"))


def fetch_all_hits() -> list[dict]:
    """api.cultural.jp から「品入札」の全ヒットをページングして取得する。"""
    hits: list[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"keyword": config.CATALOG_KEYWORD, "size": config.CATALOG_PAGE_SIZE, "page": page}
        )
        url = f"{config.CATALOG_API_URL}?{query}"
        data = http_get_json(url)
        page_hits = data.get("hits", {}).get("hits", [])
        hits.extend(page_hits)
        total = data.get("hits", {}).get("total", {}).get("value", len(hits))
        if len(hits) >= total or not page_hits:
            break
        page += 1
    return hits


def _first(field: dict | None, lang: str = "ja") -> str | None:
    if not field:
        return None
    values = field.get(lang) or []
    return values[0] if values else None


def classify(hit: dict) -> dict:
    """1件のAPI応答から queue.json の要素（新規追加時のデフォルト値）を組み立てる。"""
    hit_id = hit["id"]
    title = _first(hit.get("title")) or _first(hit.get("title"), "en") or hit_id
    source = _first(hit.get("source")) or ""
    access = _first(hit.get("access"))
    temporal = _first(hit.get("temporal"))
    manifest_list = hit.get("manifest") or []
    manifest = manifest_list[0] if manifest_list else None

    if source == "ARC古典籍ポータルデータベース" and manifest:
        m = ARC_MANIFEST_RE.match(manifest)
        book_id = m.group("book_id") if m else hit_id
        return {
            "id": hit_id, "book_id": book_id, "title": title, "manifest": manifest,
            "source": source, "access": access, "temporal": temporal,
            "provider": "arc", "status": "pending", "note": "",
        }

    if source == "国立国会図書館デジタルコレクション":
        pid = hit_id.replace("dignl-", "")
        book_id = f"ndl-{pid}"
        if manifest:
            # IIIFマニフェストがある2件（第2段階の対象）。
            return {
                "id": hit_id, "book_id": book_id, "title": title, "manifest": manifest,
                "source": source, "access": access, "temporal": temporal,
                "provider": "ndl", "status": "pending", "note": "第2段階（NDL）の対象。",
            }
        note = "官報は入札目録ではないため対象外。" if title == "官報" else "IIIFマニフェストがないため対象外。"
        return {
            "id": hit_id, "book_id": book_id, "title": title, "manifest": None,
            "source": source, "access": access, "temporal": temporal,
            "provider": "ndl", "status": "skipped", "note": note,
        }

    # オーテピア高知図書館・山梨デジタルアーカイブ・佐賀県立図書館・ADEAC等: IIIFなし、対象外
    if "山梨" in source:
        note = "売立目録ではない文書のため対象外。"
    else:
        note = "IIIFマニフェストがなく画像取得手段が未確立のため対象外。"
    return {
        "id": hit_id, "book_id": hit_id, "title": title, "manifest": manifest,
        "source": source, "access": access, "temporal": temporal,
        "provider": "other", "status": "skipped", "note": note,
    }


def merge_queue(old_queue: list[dict], fresh_entries: list[dict]) -> list[dict]:
    """status/note/updated は既存を保持し、書誌情報だけ最新化する（冪等な再実行）。"""
    old_by_id = {item["id"]: item for item in old_queue}
    today = date.today().isoformat()
    merged: list[dict] = []
    for entry in fresh_entries:
        old = old_by_id.get(entry["id"])
        if old is None:
            entry["updated"] = today
            merged.append(entry)
            continue
        kept = dict(entry)
        kept["status"] = old.get("status", entry["status"])
        kept["note"] = old.get("note", entry["note"])
        kept["updated"] = old.get("updated", today)
        merged.append(kept)
    return merged


def main() -> None:
    print(f"cultural.jp「{config.CATALOG_KEYWORD}」検索を取得中…")
    hits = fetch_all_hits()
    print(f"  {len(hits)} 件取得")

    fresh_entries = [classify(h) for h in hits]
    fresh_entries.extend(dict(e) for e in MANUAL_ENTRIES)

    old_queue = config.load_queue()
    queue = merge_queue(old_queue, fresh_entries)

    config.QUEUE_JSON.parent.mkdir(parents=True, exist_ok=True)
    config.QUEUE_JSON.write_text(
        json.dumps(queue, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    counts: dict[str, int] = {}
    for item in queue:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    print(
        f"queue.json 更新: 総数{len(queue)}件 "
        f"(pending={counts.get('pending', 0)} done={counts.get('done', 0)} "
        f"skipped={counts.get('skipped', 0)} error={counts.get('error', 0)})"
    )


if __name__ == "__main__":
    main()
