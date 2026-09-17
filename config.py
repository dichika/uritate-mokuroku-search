"""売立目録全文検索システム 共通設定。

対象資料・パス・URLパターンはすべてここで一元管理する。
検索対象の資料IDは固定リストではなく `data/catalog/queue.json`（cultural.jp「品入札」一覧の
取り込みキュー）で管理する。新規資料の取り込みは `pipeline/fetch_catalog.py` で一覧を更新し、
`pipeline/add_books.py --count N` を実行する（詳細は README「資料の追加手順」を参照）。
"""

import json
from pathlib import Path

# ディレクトリ構成
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"
DOCS_DATA_DIR = DOCS_DIR / "data"
TOOLS_DIR = BASE_DIR / "tools"
OCR_TOOL_DIR = TOOLS_DIR / "ndlocr-lite"
OCR_PYTHON = BASE_DIR / ".venv" / "bin" / "python"
LOG_DIR = BASE_DIR / "logs"

# 取り込みキュー（cultural.jp「品入札」一覧の取り込み状況を管理する）
CATALOG_DIR = DATA_DIR / "catalog"
CULTURAL_JP_HITS_JSON = CATALOG_DIR / "cultural_jp_hits.json"
QUEUE_JSON = CATALOG_DIR / "queue.json"
DAILY_BATCH_SIZE = 5

# 検索インデックス（分割済み。docs/index.html は起動時に catalog.json と search.json だけを読み、
# 資料単位の座標付き全データは books/{book_id}.json をオーバーレイ表示時に遅延読み込みする）
CATALOG_JSON = DOCS_DATA_DIR / "catalog.json"
SEARCH_JSON = DOCS_DATA_DIR / "search.json"
BOOKS_DIR = DOCS_DATA_DIR / "books"

# 新旧字体・異体字の対応表（入力）と、検索UIが読み込む生成物
KANJI_VARIANTS_DIR = DATA_DIR / "kanji_variants"
KANJI_VARIANTS_JS = DOCS_DIR / "kanji-variants.js"

# cultural.jp（Cultural Japan）横断検索API。「品入札」で検索し、取り込み候補一覧を得る。
CATALOG_API_URL = "https://api.cultural.jp/search"
CATALOG_KEYWORD = "品入札"
CATALOG_PAGE_SIZE = 100

# アーカイブ側URLパターン（ARC 立命館大学アート・リサーチセンター dh-jac.net）
MANIFEST_URL_TMPL = "https://www.dh-jac.net/db1/books/{book_id}/portal/manifest.json"
PORTAL_URL_TMPL = "https://www.dh-jac.net/db1/books/{book_id}/portal/"
# 公式ビューア相当（IIIF Image Annotator にマニフェストを渡す）
VIEWER_URL_TMPL = (
    "https://www.kanzaki.com/works/2016/pub/image-annotator?manifest="
    "https://www.dh-jac.net/db1/books/{book_id}/portal/manifest.json"
)

# NDL（国立国会図書館デジタルコレクション）用テンプレート（第2段階で使用する）
NDL_MANIFEST_URL_TMPL = "https://www.dl.ndl.go.jp/api/iiif/{pid}/manifest.json"
NDL_PORTAL_URL_TMPL = "https://dl.ndl.go.jp/pid/{pid}"

# IIIF Image API のパスパターン（{base} は manifest 中の service @id、末尾スラッシュ付き）
IIIF_FULL_IMAGE_TMPL = "{base}full/full/0/default.jpg"
IIIF_THUMB_TMPL = "{base}full/400,/0/default.jpg"

# サーバーへの配慮
REQUEST_WAIT_SEC = 5.0  # 2026-09-11 に1.5秒間隔の一括取得後に約6日間IP遮断されたため広げた
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 uritate-mokuroku-search/0.1"
)
# dh-jac.net は自動アクセスに HTTP 429 を返すことがある。ブラウザ相当の Accept 系ヘッダーを
# 付けたうえで portal ページを先に GET してクッキーを受け取ると通ることを確認済み（fetch.py参照）。
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def book_dir(book_id: str) -> Path:
    return DATA_DIR / book_id


def images_dir(book_id: str) -> Path:
    return book_dir(book_id) / "images"


def ocr_dir(book_id: str) -> Path:
    return book_dir(book_id) / "ocr"


def load_queue() -> list[dict]:
    """取り込みキュー（queue.json）を読む。未生成なら空リストを返す。"""
    if not QUEUE_JSON.exists():
        return []
    return json.loads(QUEUE_JSON.read_text(encoding="utf-8"))


def done_book_ids() -> list[str]:
    """queue.json 上で status=done の book_id を、キュー内の出現順で返す。

    fetch.py / run_ocr.py / build_index.py はこの関数が返す一覧を処理対象とする。
    固定の BOOK_IDS リストは廃止した（資料が334件規模になるため）。
    """
    return [item["book_id"] for item in load_queue() if item.get("status") == "done"]
