"""新旧字体・異体字の対応表から docs/kanji-variants.js を生成する。

使い方:
    python3 pipeline/build_variants.py

data/kanji_variants/ の JSON（joyo_kanji.json → joyo_variants.json → extra.json の順に読み、
後から読んだものが優先）を統合し、検索UIが読み込む 1文字→1文字 の対応表を出力する。
自分自身への対応（同じ文字）や、変換先がさらに別の文字へ変換される連鎖は解消しておく。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

SOURCE_FILES = ["joyo_kanji.json", "joyo_variants.json", "extra.json"]


def load_tables() -> dict[str, str]:
    table: dict[str, str] = {}
    for name in SOURCE_FILES:
        path = config.KANJI_VARIANTS_DIR / name
        data = json.loads(path.read_text(encoding="utf-8"))
        for old, new in data.items():
            if len(old) != 1 or len(new) != 1:
                print(f"  警告: 1文字対応でないため無視 {name}: {old!r}→{new!r}", file=sys.stderr)
                continue
            table[old] = new
    # 自己対応の除去と連鎖の解消（A→B, B→C なら A→C）
    resolved: dict[str, str] = {}
    for old, new in table.items():
        seen = {old}
        while new in table and new not in seen:
            seen.add(new)
            new = table[new]
        if new != old:
            resolved[old] = new
    return resolved


def main() -> None:
    table = load_tables()
    js = (
        "// 自動生成: pipeline/build_variants.py（data/kanji_variants/ を参照）\n"
        "// 旧字体・異体字 → 新字体 の1文字対応表。検索語と本文の両方に適用する。\n"
        "window.KANJI_VARIANTS = "
        + json.dumps(table, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )
    config.KANJI_VARIANTS_JS.write_text(js, encoding="utf-8")
    print(f"{config.KANJI_VARIANTS_JS.name} 生成: {len(table)} 組 / {config.KANJI_VARIANTS_JS.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
