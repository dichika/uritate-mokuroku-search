# 売立目録全文検索システム

立命館大学アート・リサーチセンター ARC書籍閲覧システム（https://www.dh-jac.net/db1/books/）が
IIIF で公開する売立目録（入札目録）の画像を、活字OCRでテキスト化してスマホから全文検索できるように
する個人研究用ツールである。能伝書全文検索システム（`~/claude_code/能伝書全文検索システム`）と同じ構成である。

- 画像は再配布せず、ARC の IIIF Image API（arc.ritsumei.ac.jp）から直接表示する。
- 本文テキストは NDLOCR-Lite（国立国会図書館, CC BY 4.0）による機械翻刻であり、誤読を含む。
- 検索UI（docs/）には noindex を設定し、検索エンジンのインデックスを拒否している。

## 収録資料

| 資料ID（請求記号） | 書名 | 刊行 | 所蔵 | コマ数 |
|---|---|---|---|---|
| UCB-N7352-B558-0146 | 佐竹侯爵家御蔵器入札 | 大正6年（1917） | UC Berkeley East Asian Library | 136 |

## 構成

| パス | 役割 |
|------|------|
| `config.py` | 対象資料ID・パス・URLパターンの一元管理 |
| `pipeline/fetch.py` | IIIFマニフェスト・ページ画像の取得 |
| `pipeline/run_ocr.py` | NDLOCR-Lite による一括OCR |
| `pipeline/build_index.py` | 検索インデックス `docs/data/index.json` の生成 |
| `docs/` | GitHub Pages 公開ディレクトリ（検索UI） |

## 資料の追加手順

1. `config.py` の `BOOK_IDS` に ARC 書籍ポータルの資料ID（`books/{id}/portal/` の `id`、請求記号）を追記する。
2. 以下を順に実行する。

```bash
python3 pipeline/fetch.py
python3 pipeline/run_ocr.py
python3 pipeline/build_index.py
```

### マニフェストが取得できない場合

dh-jac.net のマニフェスト URL は curl や urllib からのアクセスに対して
「アクセスが集中しています」（HTTP 429, Retry-After 3600）を返すことがある（2026-09-10 に確認）。
その場合は、ブラウザで `https://www.dh-jac.net/db1/books/{id}/portal/manifest.json` を開いて
JSON を `data/{id}/manifest.json` に保存してから `fetch.py` を再実行する。
既存の `manifest.json` があればダウンロードはスキップされる。
画像サーバ（arc.ritsumei.ac.jp）は通常の HTTP アクセスで取得できる。

### 画像サーバ（arc.ritsumei.ac.jp）の挙動（2026-09-10 確認）

- User-Agent に `Claude/` や `curl/` を含む要求は HTTP 403 で拒否される。`config.USER_AGENT` は
  Chrome 相当の文字列にしている。Claude Code のアプリ内ブラウザ（UA に `Claude/` を含む）では
  画像が一切表示されないため、動作確認は通常の Chrome で行う。
- WAF（F5 系。`TS…`/`DMZ` クッキー）がセッション初回の並列要求を落とすことがある。
  検索UIではサムネイルの `onerror` 再試行（最大3回）と OpenSeadragon の `tileRetryMax: 3` で吸収している。

## 初回セットアップ

```bash
git clone https://github.com/ndl-lab/ndlocr-lite tools/ndlocr-lite
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r tools/ndlocr-lite/requirements.txt
```

## ローカルプレビュー

```bash
python3 -m http.server 8124 --directory docs
```

## クレジット

- 画像・マニフェスト: 立命館大学アート・リサーチセンター ARC書籍閲覧システム（原資料は各所蔵機関の所蔵）
- OCR: [NDLOCR-Lite](https://github.com/ndl-lab/ndlocr-lite)（国立国会図書館, CC BY 4.0）
- ビューア: OpenSeadragon（BSD-3-Clause）
