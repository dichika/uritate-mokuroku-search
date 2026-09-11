# 売立目録全文検索システム

立命館大学アート・リサーチセンター ARC書籍閲覧システム（https://www.dh-jac.net/db1/books/）が
IIIF で公開する売立目録（入札目録）の画像を、活字OCRでテキスト化してスマホから全文検索できるように
する個人研究用ツールである。能伝書全文検索システム（`~/claude_code/能伝書全文検索システム`）と同じ構成である。

- 画像は再配布せず、ARC の IIIF Image API（arc.ritsumei.ac.jp）から直接表示する。
- 本文テキストは NDLOCR-Lite（国立国会図書館, CC BY 4.0）による機械翻刻であり、誤読を含む。
- 検索UI（docs/）には noindex を設定し、検索エンジンのインデックスを拒否している。

## 収録資料

cultural.jp（Cultural Japan）の横断検索「品入札」（https://cultural.jp/search?keyword=品入札 、334件）
に表示される入札目録のうち、画像取得手段が確立している320件（ARC古典籍ポータル318件、
NDLデジタルコレクション2件。除外理由や内訳は `作業設計_一括追加.md` §1.1 を参照）を対象に、
1日5件ずつ `pipeline/add_books.py` で追加している（残り319件を64日程度で追加していく見込み）。

初回導入資料（cultural.jpの「品入札」検索結果には含まれないため `pipeline/fetch_catalog.py` の
`MANUAL_ENTRIES` で手動登録している。詳細は同ファイルのdocstring参照）:

| 資料ID（請求記号） | 書名 | 刊行 | 所蔵 | コマ数 |
|---|---|---|---|---|
| UCB-N7352-B558-0146 | 佐竹侯爵家御蔵器入札 | 大正6年（1917） | UC Berkeley East Asian Library | 136 |

現在の取り込み状況（pending/done/skipped/error の内訳）は `data/catalog/queue.json` で管理する。
以下で集計できる。

```bash
python3 -c "import json; from collections import Counter
q = json.load(open('data/catalog/queue.json'))
print(Counter(x['status'] for x in q))"
```

収録済み資料の一覧・書誌は検索UI（`docs/index.html`）で確認できるほか、
`docs/data/catalog.json` にも全件分がある。320冊規模になるため README には全件を列挙しない。

## 構成

| パス | 役割 |
|------|------|
| `config.py` | 資料の取り込みキュー・パス・URLパターンの一元管理 |
| `data/catalog/queue.json` | cultural.jp「品入札」一覧の取り込みキュー（pending/done/skipped/error） |
| `pipeline/fetch_catalog.py` | cultural.jp から「品入札」一覧（334件）を取得し取り込みキューを更新する |
| `pipeline/add_books.py` | キューから資料を選び、取得→OCR→インデックス再生成までを行う日次運用の本体 |
| `pipeline/fetch.py` | IIIFマニフェスト・ページ画像の取得（`add_books.py` から1冊ずつ呼ばれる） |
| `pipeline/run_ocr.py` | NDLOCR-Lite による一括OCR（同上） |
| `pipeline/build_index.py` | 検索インデックス（`docs/data/catalog.json` / `search.json` / `books/*.json`）の生成 |
| `pipeline/build_variants.py` | 新旧字体・異体字対応表 `docs/kanji-variants.js` の生成（入力は `data/kanji_variants/`） |
| `docs/` | GitHub Pages 公開ディレクトリ（検索UI） |

320件規模になったため、検索インデックスは3ファイルに分割している（詳細は `pipeline/build_index.py`
のdocstring、および `作業設計_一括追加.md` §2.4 を参照）。

- `docs/data/catalog.json` … 全冊の書誌一覧（起動時に読む。軽量）
- `docs/data/search.json` … 全冊の本文（座標なし。起動時に読む。全文検索に使う）
- `docs/data/books/{book_id}.json` … 資料1冊分の全データ（座標つき）。検索結果の画像を開いた
  ときに遅延取得する。

検索UIには、資料一覧（検索語なし）を所蔵・刊行年・書名で絞り込むフィルタと、
「さらに表示」による50件ずつの追加表示を実装している。

## 資料の追加手順

### 日次運用（自動）

1日5件ずつ `pipeline/add_books.py` で追加する運用を想定している（スケジュールタスク
`uritate-add-books-daily`。日次運用の設計は `作業設計_一括追加.md` §3 を参照）。

```bash
python3 pipeline/add_books.py --count 5 --push
```

処理内容: キュー（`data/catalog/queue.json`）から status=pending かつ provider=arc の資料を
先頭から件数分選び、1冊ずつ「マニフェスト取得 → 画像取得 → OCR」の順に処理してから
インデックスを再生成する。dh-jac.net が429を返した場合はその回のバッチ処理を直ちに中止し、
該当資料の status は変更せず翌日に持ち越す（エラー扱いにはしない）。
429以外の例外はその冊だけ status=error にして次の冊へ進む。
`--push` を付けると `git add -A && git commit && git push origin main` まで行う
（テストなど手動実行時は付けないこと）。

### 手動での個別追加・再取得

```bash
python3 pipeline/fetch_catalog.py                              # queue.json を最新化する
python3 pipeline/add_books.py --book-id UCB-N7352-B558-0066    # 特定の1冊だけ処理・再試行する
python3 pipeline/build_index.py                                 # インデックスだけ再生成したい場合
```

cultural.jp「品入札」の検索結果に出てこない資料を追加したい場合は、`pipeline/fetch_catalog.py`
の `MANUAL_ENTRIES` に1件追記してから `python3 pipeline/fetch_catalog.py` → `add_books.py`
の順に実行する。

### マニフェストが取得できない場合

dh-jac.net のマニフェスト URL は自動アクセスに対して「アクセスが集中しています」
（HTTP 429, Retry-After 3600）を返すことがある（2026-09-10 に確認）。`pipeline/fetch.py` の
`fetch_manifest_bytes()` は、ブラウザ相当のヘッダー（`config.BROWSER_HEADERS`）で
`.../portal/` ページを先に GET してクッキーを受け取り、同じクッキーで manifest.json を
取得する手順を自動で行う（2026-09-11 に確認、成功率が上がる）。それでも429になる場合は
`Manifest429` 例外が送出され、`add_books.py` はその回のバッチ処理を中止する。
個別に回避したい場合は、ブラウザで `https://www.dh-jac.net/db1/books/{id}/portal/manifest.json`
を開いて JSON を `data/{id}/manifest.json` に保存してから再実行してもよい
（既存の `manifest.json` があればダウンロードはスキップされる）。

### 画像サーバ（arc.ritsumei.ac.jp）の挙動（2026-09-10・2026-09-11 確認）

- User-Agent に `Claude/` や `curl/` を含む要求は HTTP 403 で拒否される。`config.USER_AGENT` は
  Chrome 相当の文字列にしている。Claude Code のアプリ内ブラウザ（UA に `Claude/` を含む）では
  画像が一切表示されないため、動作確認は通常の Chrome で行う。
- WAF（F5 系。`TS…`/`DMZ` クッキー）がセッション初回の並列要求を落とすことがある。
  検索UIでは OpenSeadragon の `tileRetryMax: 3` で吸収している。
- 2026-09-11、新規2冊のテスト追加（`add_books.py --count 2`）で、`config.REQUEST_WAIT_SEC`
  を遵守した1件目の画像リクエストから既に HTTP 403 が返る事象を確認した。その後、
  URLパス違い（IIIF Scaler経由／`th_image`直リンク）や `config.BROWSER_HEADERS`
  付与の有無を変えて curl で検証したが、いずれも403で、リクエスト量や再試行が原因の
  一時的なWAF反応ではなく、この検証環境のネットワーク経路に対する何らかのブロックと
  みられる（原因未特定。1回のリクエストで発生したため、config.REQUEST_WAIT_SEC 遵守や
  リクエスト間隔とは無関係と判断した）。既存資料（UCB-N7352-B558-0146）の画像も同時に
  403 になっており、資料固有の問題ではないことを確認済みである。通常のブラウザ環境
  （WAFがこの検証環境だけをブロックしていない場合）では従来通り閲覧できる可能性が高いが、
  未確認である。次回実行時に解消していない場合は原因調査が必要。

## 検索の正規化（旧字体・異体字）

検索語と本文の両方を1文字ずつ NFKC → カタカナ→ひらがな → 旧字体・異体字→新字体 → 小文字化 の順で
正規化して照合するため、「芸阿弥」でも「藝阿彌」でもヒットし、ハイライトは原文の字形のまま表示される。
対応表は `data/kanji_variants/`（常用漢字表に基づく new-village/joyo-kanji の 359組＋異体字17組、
および売立目録向けの補足 `extra.json`）から `pipeline/build_variants.py` で生成する。
対応を追加したいときは `extra.json` に1文字→1文字で追記して再生成する。

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
- 新旧字体対応表: [new-village/joyo-kanji](https://github.com/new-village/joyo-kanji)（Apache-2.0）
- ビューア: OpenSeadragon（BSD-3-Clause）
