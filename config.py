"""売立目録全文検索システム 共通設定。

対象資料・パス・URLパターンはすべてここで一元管理する。
資料を追加する場合は BOOK_IDS にARC書籍ポータルの資料ID（Call Number）を追記し、
パイプライン（fetch → run_ocr → build_index）を再実行する。
"""

from pathlib import Path

# 検索対象の資料ID（立命館大学ARC 書籍閲覧システム dh-jac.net の books/{book_id}）
BOOK_IDS = [
    "UCB-N7352-B558-0146",  # 佐竹侯爵家御蔵器入札（大正6年, UC Berkeley East Asian Library蔵）
]

# ディレクトリ構成
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"
TOOLS_DIR = BASE_DIR / "tools"
OCR_TOOL_DIR = TOOLS_DIR / "ndlocr-lite"
OCR_PYTHON = BASE_DIR / ".venv" / "bin" / "python"
INDEX_JSON = DOCS_DIR / "data" / "index.json"

# アーカイブ側URLパターン
MANIFEST_URL_TMPL = "https://www.dh-jac.net/db1/books/{book_id}/portal/manifest.json"
PORTAL_URL_TMPL = "https://www.dh-jac.net/db1/books/{book_id}/portal/"
# 公式ビューア相当（IIIF Image Annotator にマニフェストを渡す）
VIEWER_URL_TMPL = (
    "https://www.kanzaki.com/works/2016/pub/image-annotator?manifest="
    "https://www.dh-jac.net/db1/books/{book_id}/portal/manifest.json"
)

# IIIF Image API のパスパターン（{base} は manifest 中の service @id、末尾スラッシュ付き）
IIIF_FULL_IMAGE_TMPL = "{base}full/full/0/default.jpg"
IIIF_THUMB_TMPL = "{base}full/400,/0/default.jpg"

# サーバーへの配慮
REQUEST_WAIT_SEC = 1.5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 uritate-mokuroku-search/0.1"
)


def book_dir(book_id: str) -> Path:
    return DATA_DIR / book_id


def images_dir(book_id: str) -> Path:
    return book_dir(book_id) / "images"


def ocr_dir(book_id: str) -> Path:
    return book_dir(book_id) / "ocr"
