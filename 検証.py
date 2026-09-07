# -*- coding: utf-8 -*-
"""
index.html 検証スクリプト
------------------------------------------------------------
使い方:
    py 検証.py            … 検証する（HTMLは変更しない）
    py 検証.py --基準更新  … 今の状態を「正しい基準」として保存し直す

判定の種類:
    [FAIL] 確実に壊れている。直すまでコミットしない
    [注意] 人が見て判断する（意図した変更ならOK）
    [OK]   問題なし

2026-09-07 作成（HTML改善会議 Round 1 の検証手順15項目にもとづく）
"""
import sys, re, os, json, subprocess

sys.stdout.reconfigure(encoding='utf-8')

HTML = 'index.html'
BASE = '検証_基準.json'

VOID = {'br','img','input','hr','meta','link','area','base','col',
        'embed','source','track','wbr','param'}

# 動的にJSがidを振る要素（アンカー健全性チェックの除外）
ANCHOR_WHITELIST = re.compile(r'^day\d+$')

# モード切替で使う属性（将来用）。ここにない値が入っていたらFAIL
MODE_ATTR = 'data-hide-in'
MODE_VALUES = {'trip', 'prep'}

fails, warns = [], []


def fail(t, m):
    fails.append((t, m))
    print(f'  [FAIL] {m}')


def warn(t, m):
    warns.append((t, m))
    print(f'  [注意] {m}')


def ok(m):
    print(f'  [OK]   {m}')


def strip_code(html):
    h = re.sub(r'<script\b.*?</script>', '', html, flags=re.S | re.I)
    h = re.sub(r'<style\b.*?</style>', '', h, flags=re.S | re.I)
    return re.sub(r'<!--.*?-->', '', h, flags=re.S)


def visible_text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', strip_code(html))).strip()


# ============================================================
# 1. タグ整合（未閉じ・閉じ過ぎ・入れ子ミス）
# ============================================================
def check_tags(html):
    print('\n■ 1. タグ整合')
    h = strip_code(html)
    stack, errs, op, cl = [], [], {}, {}
    for m in re.finditer(r'<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)\s*>', h):
        slash, tag, self_close = m.group(1), m.group(2).lower(), m.group(3)
        if tag in VOID or self_close == '/':
            continue
        line = h[:m.start()].count('\n') + 1
        if slash:
            cl[tag] = cl.get(tag, 0) + 1
            if not stack:
                errs.append(f'{line}行目: </{tag}> に対応する開始タグがない')
            elif stack[-1][0] == tag:
                stack.pop()
            else:
                errs.append(f'{line}行目: </{tag}> だが直前に開いているのは <{stack[-1][0]}>（{stack[-1][1]}行目）')
        else:
            op[tag] = op.get(tag, 0) + 1
            stack.append((tag, line))
    for e in errs[:10]:
        fail('タグ整合', e)
    for tag, line in stack[:10]:
        fail('タグ整合', f'{line}行目の <{tag}> が閉じられていない')
    if not errs and not stack:
        ok('入れ子・開閉ともに整合')
    counts = {t: (op.get(t, 0), cl.get(t, 0)) for t in
              ['div', 'section', 'table', 'tr', 'td', 'span', 'a', 'details', 'summary']}
    print('       ' + ' / '.join(f'{t} {v[0]}' for t, v in counts.items()))
    return {t: v[0] for t, v in counts.items()}


# ============================================================
# 2. id 重複
# ============================================================
def check_ids(html):
    print('\n■ 2. id の重複')
    # 静的HTML（<script>の外）だけを対象にする
    static = strip_code(html)
    ids = re.findall(r'\sid="([^"]+)"', static)
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        for d in dup:
            fail('id重複', f'id="{d}" が静的HTML内で {ids.count(d)} 回使われている')
    else:
        ok(f'静的HTMLの id {len(ids)}個 はすべて一意')

    # JSが生成する id（分岐によって片方しか出ないので、重複していても即FAILにはしない）
    js = '\n'.join(re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.S))
    jsids = re.findall(r'id="([A-Za-z][\w\-]*)"', js)
    jsdup = sorted({i for i in jsids if jsids.count(i) > 1})
    for d in jsdup:
        warn('id重複', f'JSが生成する id="{d}" が {jsids.count(d)} 箇所にある。'
                       '別々の分岐なら問題ないが、同時に描画されないか確認すること')
    if jsids and not jsdup:
        ok(f'JSが生成する id {len(set(jsids))}種 も重複なし')
    return set(ids) | set(jsids)


# ============================================================
# 3. アンカー健全性
# ============================================================
def check_anchors(html, ids):
    print('\n■ 3. アンカーの飛び先')
    # 静的HTMLのリンクだけを見る（JS内の 'href="#day'+day+'"' のような文字列連結は対象外）
    hrefs = sorted(set(re.findall(r'href="#([^"]+)"', strip_code(html))))
    missing = [h for h in hrefs if h not in ids and not ANCHOR_WHITELIST.match(h)]
    if missing:
        for m in missing:
            fail('アンカー', f'href="#{m}" の飛び先 id が存在しない（押しても何も起きない）')
    else:
        ok(f'{len(hrefs)}個のリンク先はすべて実在（day1〜7 はJSが付与するため除外）')


# ============================================================
# 4. <script> の IIFE 包囲（B2 の再発防止）
# ============================================================
def check_scripts(html):
    print('\n■ 4. <script> のグローバル汚染')
    blocks = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.S)
    for i, b in enumerate(blocks, 1):
        body = re.sub(r'^\s*(//[^\n]*\n|/\*.*?\*/\s*)+', '', b.strip(), flags=re.S).strip()
        wrapped = body.startswith('(function') or body.startswith('(()') or body.startswith('!function')
        decls = re.findall(r'^\s{0,2}(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)', b, re.M)
        if not wrapped and decls:
            fail('script', f'script#{i} が IIFE で包まれておらず、{decls[:6]} をグローバル宣言している'
                           '（新しいスクリプトと変数名が衝突すると、そのブロックが丸ごと動かなくなる）')
        else:
            ok(f'script#{i} は安全（IIFE で包まれている）')


# ============================================================
# 5. 外部依存ゼロの維持（圏外で開けることの根拠）
# ============================================================
def check_selfcontained(html):
    print('\n■ 5. 外部依存ゼロ（圏外で開けることの根拠）')
    probes = [
        ('画像/外部JS (src=)', r'\ssrc\s*='),
        ('外部CSS (<link rel=stylesheet)', r'<link[^>]+stylesheet'),
        ('CSSのurl()', r'url\(\s*["\']?https?:'),
        ('@import', r'@import'),
        ('fetch()', r'\bfetch\s*\('),
        ('XMLHttpRequest', r'XMLHttpRequest'),
        ('Web Worker', r'new\s+Worker'),
    ]
    bad = False
    for name, pat in probes:
        n = len(re.findall(pat, html, re.I))
        if n:
            fail('外部依存', f'{name} が {n} 件ある。1つでも足すと圏外で開けなくなる')
            bad = True
    if not bad:
        ok('外部依存ゼロを維持（単一ファイルで完全自己完結）')


# ============================================================
# 6. day-card の必須属性
# ============================================================
def check_daycards(html):
    print('\n■ 6. 日程カードの必須属性')
    need = ['data-day', 'data-date', 'data-hotel', 'data-addr', 'data-tel']
    cards = re.findall(r'<details class="day-card"([^>]*)>', html)
    if not cards:
        fail('dayカード', 'day-card が1枚も見つからない')
        return
    days, empty_tel = [], []
    for a in cards:
        for n in need:
            if f'{n}=' not in a:
                fail('dayカード', f'属性 {n} が無いカードがある: {a[:70]}')
        d = re.search(r'data-day="([^"]*)"', a)
        t = re.search(r'data-tel="([^"]*)"', a)
        h = re.search(r'data-hotel="([^"]*)"', a)
        if d:
            days.append(d.group(1))
        hotel = h.group(1) if h else ''
        # 宿泊しない日（帰国便など）は電話番号が無くて当然なので対象外
        if t is not None and not t.group(1).strip() and '宿泊なし' not in hotel:
            empty_tel.append((d.group(1) if d else '?', hotel[:26]))
    if len(days) != len(set(days)):
        fail('dayカード', f'data-day が重複している: {days}')
    else:
        ok(f'{len(cards)}枚すべてに必須5属性あり／data-day は一意（{",".join(days)}）')
    if empty_tel:
        for d, h in empty_tel:
            warn('電話番号', f'Day{d} の data-tel が空 → 「今夜の宿」に📞ボタンが出ない（{h}）')


# ============================================================
# 7. モード属性の表記ゆれ／セクション単位の非表示禁止
# ============================================================
def check_mode_attrs(html):
    print('\n■ 7. モード属性（将来のモード切替用）')
    vals = re.findall(MODE_ATTR + r'="([^"]*)"', html)
    if not vals:
        ok(f'{MODE_ATTR} は未使用（モード切替は未実装）')
        return
    badv = sorted({v for v in vals if v not in MODE_VALUES})
    if badv:
        fail('モード属性', f'想定外の値: {badv}（使ってよいのは {sorted(MODE_VALUES)} だけ）')
    else:
        ok(f'{len(vals)}件すべて正しい値')
    for m in re.finditer(r'<section\b[^>]*>', html):
        if MODE_ATTR in m.group(0):
            fail('モード属性', f'<section> に {MODE_ATTR} が付いている。'
                              'セクション単位で隠すと、中の当日必要な情報まで巻き添えで消える')


# ============================================================
# 8. 重要な事実の出現数（訂正もれの検出）
# ============================================================
def check_facts(html, base):
    print('\n■ 8. 重要な事実の出現数')
    exp = base.get('重要値', {})
    if not exp:
        ok('基準が未登録（--基準更新 で作成してください）')
        return
    drift = False
    for k, v in sorted(exp.items()):
        n = html.count(k)
        if n != v:
            drift = True
            if n == 0:
                fail('重要値', f'「{k}」が消えた（基準 {v}件 → 現在 0件）')
            else:
                warn('重要値', f'「{k}」の出現数が変わった（基準 {v}件 → 現在 {n}件）'
                              '／意図した変更なら --基準更新')
    if not drift:
        ok(f'{len(exp)}件すべて基準どおり（訂正もれなし）')

    print('\n■ 8b. 使ってはいけない旧値')
    banned = base.get('禁止値', [])
    if not banned:
        ok('禁止値は未登録')
    else:
        hit = False
        for k in banned:
            n = html.count(k)
            if n:
                hit = True
                fail('旧値', f'「{k}」が {n} 件残っている')
        if not hit:
            ok(f'{len(banned)}件すべて 0 件')


# ============================================================
# 9. 未記入・電話番号の形式
# ============================================================
def check_content(html):
    print('\n■ 9. 未記入・電話番号')
    n = html.count('class="fillin"') + html.count('（未記入）')
    if n:
        warn('未記入', f'手書きで埋める欄が {n} 件残っている。'
                      '緊急連絡先が空欄のまま出発する事故に直結（#emergency の記入欄）')
    else:
        ok('記入欄はすべて埋まっている')
    jp = re.findall(r'href="tel:(0\d[^"]*)"', html)
    if jp:
        warn('電話形式', f'日本の番号が国際形式でない（米国からかけると繋がらない）: {sorted(set(jp))}'
                        ' → tel:+81... にする')
    else:
        ok('tel: リンクはすべて国際形式')


# ============================================================
# 10. 参考情報
# ============================================================
def report_info(html):
    print('\n■ 10. 参考（初回表示の重さ）')
    h = strip_code(html)
    total = len(visible_text(html))
    # 閉じている details の中身だけを「畳まれている量」として数える。
    # open が付いていれば見えているし、入れ子は一番外側の閉じたものだけ数える
    hidden, depth, start = 0, 0, None
    for m in re.finditer(r'<details\b([^>]*)>|</details>', h):
        if m.group(0).startswith('</'):
            depth -= 1
            if start is not None and depth == start[0]:
                inner = h[start[1]:m.start()]
                hidden += len(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', inner)).strip())
                start = None
        else:
            if ' open' not in m.group(1) and start is None:
                start = (depth, m.end())
            depth += 1
    print(f'       本文 {total:,}字 ／ 畳まれている {hidden:,}字 ／ 初回表示 約{total-hidden:,}字')
    print(f'       <h2>{len(re.findall(r"<h2[ >]", h))} <h3>{len(re.findall(r"<h3[ >]", h))} '
          f'checklist-title {len(re.findall(r"checklist-title", h))} '
          f'（うちid付き {len([x for x in re.findall(r"<div class=.checklist-title.[^>]*>", h) if "id=" in x])}）')


# ============================================================
def git_diff_note():
    try:
        r = subprocess.run(['git', 'status', '--short', HTML],
                           capture_output=True, text=True, encoding='utf-8', timeout=10)
        if r.stdout.strip():
            print(f'\n※ {HTML} は未コミットの変更あり')
    except Exception:
        pass


def main():
    if not os.path.exists(HTML):
        print(f'{HTML} が見つかりません'); sys.exit(2)
    html = open(HTML, encoding='utf-8').read()
    base = json.load(open(BASE, encoding='utf-8')) if os.path.exists(BASE) else {}

    print('=' * 60)
    print(f'  index.html 検証   （{len(html):,} バイト相当）')
    print('=' * 60)

    counts = check_tags(html)
    ids = check_ids(html)
    check_anchors(html, ids)
    check_scripts(html)
    check_selfcontained(html)
    check_daycards(html)
    check_mode_attrs(html)
    check_facts(html, base)
    check_content(html)
    report_info(html)

    if '--基準更新' in sys.argv:
        keys = base.get('重要値', {}) or {k: 0 for k in [
            'AS669', '23:51', 'FUU9JX', '23616375JP6', 'L893300', '374070232',
            '14:40', '18:55', '6,300', '11,110', '8,000', '2,250', '23:25', '10:45']}
        base['重要値'] = {k: html.count(k) for k in keys}
        base.setdefault('禁止値', ['AS3298', '2,350円', 'ザイオン'])
        base['タグ数'] = counts
        json.dump(base, open(BASE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f'\n★ 基準を更新しました → {BASE}')

    print('\n' + '=' * 60)
    if fails:
        print(f'  結果： FAIL {len(fails)}件 ／ 注意 {len(warns)}件')
        print('  🔴 FAIL があります。直すまでコミットしないでください')
    elif warns:
        print(f'  結果： FAIL なし ／ 注意 {len(warns)}件')
        print('  🟡 注意の内容が「意図した変更」ならコミットして構いません')
    else:
        print('  結果： すべてPASS 🟢')
    print('=' * 60)
    git_diff_note()
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
