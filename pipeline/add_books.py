"""取り込みキュー（data/catalog/queue.json）から資料を追加する日次運用の本体。

使い方:
    python3 pipeline/add_books.py --count 5 [--push] [--book-id UCB-N7352-B558-0066]

処理内容（作業設計書 §2.3）:
    1. queue.json から status=pending かつ provider=arc の資料を先頭から --count 件選ぶ
       （--book-id 指定時はその1件のみを選ぶ。再試行用）。
    2. 各冊についてマニフェスト取得（dh-jac.net。クッキー取得手順は fetch.py 参照）→
       画像取得 → OCR の順に処理し、成功すれば status=done にする。
       マニフェスト取得が HTTP 429 になった場合はその回のバッチ処理を直ちに中止する
       （dh-jac.net の WAF はIP/セッション単位でブロックするとみられるため、以降の冊も
       429になる可能性が高い）。中止した冊の status は pending のまま変更しない
       （翌日に持ち越す。エラー扱いにはしない）。
       それ以外の例外は、その冊だけ status=error とし note に記録して次の冊へ進む。
    3. バッチの試行後（1件以上処理しても、429で0件のときも）インデックスを再生成する。
    4. --push 指定時は変更を commit し、origin/main へ push する。
    5. 結果を logs/add_books_YYYYMMDD.log に追記し、標準出力の最終行に
       「追加 N冊 / エラー M冊 / 残り pending K冊」を1行で出す。
    6. logs/add_books.lock が存在する場合は二重起動とみなし、何もせず終了する。
"""

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_index
import config
from fetch import Manifest429, fetch_book
from run_ocr import run_ocr

LOCK_FILE = config.LOG_DIR / "add_books.lock"


def log_path_for_today() -> Path:
    return config.LOG_DIR / f"add_books_{date.today().strftime('%Y%m%d')}.log"


def append_log(lines: list[str]) -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path_for_today().open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(f"[{ts}] {line}\n")


def select_targets(queue: list[dict], count: int, book_id: str | None) -> list[dict]:
    if book_id:
        matched = [item for item in queue if item.get("book_id") == book_id]
        if not matched:
            sys.exit(f"queue.json に book_id={book_id} が見つかりません。")
        return matched
    return [
        item for item in queue
        if item.get("status") == "pending" and item.get("provider") == "arc"
    ][:count]


def save_queue(queue: list[dict]) -> None:
    config.QUEUE_JSON.write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def process_one(item: dict) -> tuple[str, str]:
    """1冊を取り込む。戻り値は (結果, 詳細) で 結果 は "done" | "error" | "429"。"""
    book_id = item["book_id"]
    try:
        fetch_book(book_id)
    except Manifest429 as e:
        return "429", str(e)
    except Exception as e:  # noqa: BLE001 - 例外の種類を問わずerror扱いにして次へ進む
        return "error", f"画像取得失敗: {e!r}"
    try:
        run_ocr(book_id)
    except Exception as e:  # noqa: BLE001
        return "error", f"OCR失敗: {e!r}"
    return "done", ""


def git_commit_and_push(added_titles: list[str]) -> None:
    if not added_titles:
        return
    if len(added_titles) == 1:
        message = f"資料追加: {added_titles[0]}"
    else:
        message = f"資料追加: {added_titles[0]} 他{len(added_titles) - 1}件"
    subprocess.run(["git", "add", "-A"], cwd=config.BASE_DIR, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=config.BASE_DIR, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=config.BASE_DIR, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=config.DAILY_BATCH_SIZE)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--book-id", default=None, help="指定した book_id のみ処理する（再試行用）")
    args = parser.parse_args()

    if LOCK_FILE.exists():
        print("二重起動を検知しました（logs/add_books.lock が存在します）。何もせず終了します。")
        return

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(f"{datetime.now().isoformat()}\n", encoding="utf-8")
    try:
        queue = config.load_queue()
        targets = select_targets(queue, args.count, args.book_id)
        queue_by_id = {item["id"]: item for item in queue}

        added_titles: list[str] = []
        n_done = 0
        n_error = 0
        stopped_by_429 = False
        log_lines: list[str] = [f"開始: count={args.count} book_id={args.book_id or '-'}"]

        for item in targets:
            book_id = item["book_id"]
            result, detail = process_one(item)
            entry = queue_by_id[item["id"]]
            if result == "done":
                entry["status"] = "done"
                entry["note"] = ""
                entry["updated"] = date.today().isoformat()
                n_done += 1
                added_titles.append(entry.get("title") or book_id)
                log_lines.append(f"完了: {book_id} {entry.get('title')}")
            elif result == "429":
                log_lines.append(f"中断(429): {book_id} {detail}")
                stopped_by_429 = True
                save_queue(queue)
                break
            else:  # error
                entry["status"] = "error"
                entry["note"] = detail
                entry["updated"] = date.today().isoformat()
                n_error += 1
                log_lines.append(f"エラー: {book_id} {detail}")
            save_queue(queue)

        if n_done > 0 or n_error > 0:
            build_index.main()
            log_lines.append("インデックス再生成 完了")

        if args.push:
            git_commit_and_push(added_titles)
            log_lines.append(f"git push 完了（{len(added_titles)}件）")

        remaining_pending = sum(
            1 for item in queue if item.get("status") == "pending" and item.get("provider") == "arc"
        )
        if stopped_by_429:
            print("HTTP 429 のため中断しました。翌回に持ち越します。")
        summary = f"追加 {n_done}冊 / エラー {n_error}冊 / 残り pending {remaining_pending}冊"
        log_lines.append(summary)
        append_log(log_lines)
        print(summary)
    finally:
        LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
