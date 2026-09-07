# -*- coding: utf-8 -*-
"""
index.html から stable.html（予備版）を作る。

stable.html は「3人の実機で確認が取れた最後の版」。
現地でindex.htmlが壊れたとき、iPhoneから
  https://ytomde15.github.io/America-trip-2026/stable.html
を開けば旅程を取り戻せる ── 最後の命綱。

使い方：  py 予備版を作る.py
          （そのあと 公開サイトを更新.bat で push すること）
"""
import subprocess
import sys
import datetime
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "index.html"
DST = HERE / "stable.html"

MARK = "<!-- STABLE-BANNER -->"


def git(*args):
    try:
        out = subprocess.run(
            ["git"] + list(args), cwd=str(HERE),
            capture_output=True, text=True, encoding="utf-8"
        )
        return (out.stdout or "").strip()
    except Exception:
        return ""


def main():
    if not SRC.exists():
        print("[エラー] index.html が見つかりません")
        return 1

    html = SRC.read_text(encoding="utf-8")

    if MARK in html:
        print("[エラー] index.html に予備版のしるしが入っています。")
        print("        stable.html を index.html に上書きコピーしていませんか？")
        return 1

    if "<body>" not in html:
        print("[エラー] <body> が見つかりません")
        return 1

    today = datetime.date.today().strftime("%Y-%m-%d")
    h = git("rev-parse", "--short", "HEAD") or "?"
    dirty = git("status", "--porcelain")

    banner = MARK + """
<style>
  #stable-banner{
    background:#fff4d6; border-bottom:3px solid #e0a800;
    color:#4a3600; padding:14px 16px; font-size:15px; line-height:1.8;
  }
  #stable-banner b{ color:#8a5a00; }
  #stable-banner .sb-sub{ display:block; margin-top:6px; font-size:14px; }
  #stable-banner a{ color:#0b57d0; font-weight:700; }
</style>
<div id="stable-banner">
  \U0001F4BE これは <b>予備の版</b> です（__DATE__ 時点 / __HASH__）
  <span class="sb-sub">
    ふだんの版は <a href="./index.html">こちら</a>。
    予備版は「壊れたときの避難先」なので、内容が少し古いことがあります。
  </span>
</div>
""".replace("__DATE__", today).replace("__HASH__", h)

    out = html.replace("<body>", "<body>\n" + banner, 1)

    # 予備版と分かるようにタイトルも変える
    out = out.replace("<title>", "<title>【予備版】", 1)

    DST.write_text(out, encoding="utf-8")

    print("=" * 58)
    print("  stable.html を作りました")
    print("=" * 58)
    print("  元にした版 : %s（%s）" % (h, today))
    print("  大きさ     : %s バイト" % format(DST.stat().st_size, ","))
    if dirty:
        print("  [注意] コミットしていない変更があります。")
        print("         stable.html の中身は今のindex.htmlそのものですが、")
        print("         gitの %s とは一致しません。" % h)
    print("")
    print("  次にやること：")
    print("    1) py 検証.py  で FAIL が無いことを確認")
    print("    2) git add . && git commit")
    print("    3) 公開サイトを更新.bat を実行")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    sys.exit(main())
