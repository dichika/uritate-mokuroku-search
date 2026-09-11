# 新旧字体・異体字の対応表

検索UIで旧字体・異体字を新字体に正規化するための対応表である。`pipeline/build_variants.py` が
これらを統合して `docs/kanji-variants.js` を生成する。

| ファイル | 内容 | 出典 |
|---|---|---|
| `joyo_kanji.json` | 旧字体→新字体 359組（常用漢字表に基づく） | [new-village/joyo-kanji](https://github.com/new-village/joyo-kanji) `kanji.json`（Apache-2.0） |
| `joyo_variants.json` | 人名等の異体字 17組 | 同上 `variants.json` |
| `extra.json` | 売立目録・美術書でよく見る異体字の補足（本プロジェクトで追加） | 手作業 |

優先順位は extra.json > joyo_variants.json > joyo_kanji.json とし、同じ文字が重複した場合は前者が勝つ。
