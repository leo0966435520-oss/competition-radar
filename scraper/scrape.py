#!/usr/bin/env python3
"""
獎金獵人（bhuntr.com）比賽爬蟲
流程：抓列表頁 → 只讀「新出現」的比賽內頁 → 判斷高中能否參加、類型、難易度 → 寫入 docs/data.json

設計原則：
- 遵守 robots.txt，每次請求間隔 DELAY 秒
- 只存標題、連結、截止日、獎金與一小段摘要，詳細內容請學生點連結回原站看
- 已抓過的比賽不重抓，減少對對方網站的負擔
"""
import datetime as dt
import json
import os
import re
import time
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------- 設定（可用環境變數覆寫） ----------
BASE = os.getenv("BASE", "https://bhuntr.com")
LIST_URL = os.getenv("LIST_URL", BASE + "/tw/competitions")
PAGE_PARAM = os.getenv("PAGE_PARAM", "page")
MAX_PAGES = int(os.getenv("MAX_PAGES", "5"))
DELAY = float(os.getenv("DELAY", "3"))
CONTACT = os.getenv("CONTACT", "teacher@example.com")
UA = f"StudentCompetitionFinder/1.0 (teacher tool; contact: {CONTACT})"
# 比賽內頁的網址樣式；若原站改版抓不到東西，通常改這行就好
DETAIL_RE = re.compile(os.getenv("DETAIL_RE", r"^/tw/competitions/(?!category|tag|search|page)[^/?#]+/?$"))

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "..", "docs", "data.json")
TZ = dt.timezone(dt.timedelta(hours=8))
TODAY = dt.datetime.now(TZ).date()

# ---------- 分類關鍵字（網頁端 index.html 也有一份，修改時兩邊一起改） ----------
CATEGORIES = {
    "設計": ["設計", "海報", "插畫", "平面", "logo", "視覺", "包裝", "字體", "吉祥物", "貼圖"],
    "寫作文學": ["徵文", "文學", "小說", "散文", "新詩", "寫作", "劇本", "書評", "作文"],
    "影音攝影": ["影片", "微電影", "短片", "動畫", "影像", "攝影", "拍攝", "youtube", "podcast", "短影音"],
    "音樂表演": ["音樂", "歌曲", "創作曲", "樂團", "舞蹈", "表演", "歌唱"],
    "程式科技": ["程式", "黑客松", "hackathon", "app", "ai", "人工智慧", "資訊", "機器人", "創客", "資安", "科技"],
    "科學研究": ["科展", "科學", "研究", "實驗", "數學", "物理", "化學", "生物", "專題"],
    "商業企劃": ["企劃", "創業", "行銷", "商業", "提案", "品牌", "創意發想"],
    "社會公益": ["公益", "永續", "sdgs", "環保", "社會", "社區", "人權", "防詐", "反毒", "環境"],
    "語言國際": ["英文", "英語", "演講", "辯論", "國際交流", "外語", "日文", "朗讀"],
    "藝術美術": ["繪畫", "美術", "書法", "漫畫", "藝術", "手作", "雕塑"],
}

HS_YES = ["高中", "高職", "中學", "青少年", "不限", "不拘", "皆可報名", "皆可參加", "全國民眾", "一般民眾", "學生組"]
HS_NO = ["限大專", "大專院校在學", "大專校院在學", "限大學", "大學部", "研究所", "碩士", "博士生",
         "年滿18", "年滿 18", "年滿十八", "限社會人士"]

DATE_RE = re.compile(r"(20\d{2})\s*[./\-年]\s*(\d{1,2})\s*[./\-月]\s*(\d{1,2})")


# ---------- 抓取 ----------
session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})

robots = robotparser.RobotFileParser(BASE + "/robots.txt")
try:
    robots.read()
except Exception as e:  # 讀不到 robots.txt 時保守處理：仍慢速抓取，但印出警告
    print("⚠️ 讀不到 robots.txt：", e)
    robots = None


def get(url):
    if robots is not None and not robots.can_fetch(UA, url):
        print("⛔ robots.txt 不允許，略過：", url)
        return None
    time.sleep(DELAY)
    try:
        r = session.get(url, timeout=20)
    except requests.RequestException as e:
        print("❌ 連線失敗：", url, e)
        return None
    if r.status_code != 200:
        print(f"❌ HTTP {r.status_code}：{url}")
        return None
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def links_from_list(html):
    """從列表頁找出比賽內頁連結；若頁面是前端渲染，改從內嵌 JSON 裡找路徑。"""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        path = urlparse(urljoin(BASE, a["href"])).path
        if DETAIL_RE.match(path) and path not in found:
            found.append(path)
    if not found:
        pat = re.compile(r"(?:\\/|/)tw(?:\\/|/)competitions(?:\\/|/)([A-Za-z0-9_\-%]+)")
        for s in soup.find_all("script"):
            for slug in pat.findall(s.string or ""):
                path = f"/tw/competitions/{slug}"
                if DETAIL_RE.match(path) and path not in found:
                    found.append(path)
    return [urljoin(BASE, p) for p in found]


# ---------- 解析內頁 ----------
def meta(soup, key):
    tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
    return (tag.get("content") or "").strip() if tag else ""


def jsonld(soup):
    out = {}
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "{}")
        except json.JSONDecodeError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict):
                out.update({k: v for k, v in d.items() if k not in out})
    return out


def to_date(y, m, d):
    try:
        return dt.date(int(y), int(m), int(d))
    except ValueError:
        return None


def find_deadline(text, ld):
    # 1) 「截止」附近的日期最可靠
    for m in re.finditer(r"(截止|收件|報名期限|徵件期間|繳交期限)", text):
        window = text[m.start(): m.start() + 60]
        dates = [to_date(*x) for x in DATE_RE.findall(window)]
        dates = [d for d in dates if d]
        if dates:
            return max(dates)
    # 2) 結構化資料
    for key in ("endDate", "validThrough"):
        if isinstance(ld.get(key), str):
            m = DATE_RE.search(ld[key])
            if m:
                return to_date(*m.groups())
    return None


def find_prize(text):
    """回傳最大的獎金數字（新台幣），找不到回傳 None。"""
    best = None
    for m in re.finditer(r"(總獎金|獎金|獎學金|NT\$|新台幣|新臺幣)[^0-9]{0,8}([0-9][0-9,，]*)\s*(萬)?", text):
        n = int(re.sub(r"[,，]", "", m.group(2)) or 0)
        if m.group(3):
            n *= 10000
        if 0 < n < 100_000_000:
            best = max(best or 0, n)
    return best


def snippet(text, keys, length=120):
    for k in keys:
        i = text.find(k)
        if i >= 0:
            return text[i: i + length]
    return ""


def high_school_fit(elig, text):
    scope = elig or text
    if any(k in scope for k in HS_YES):
        return "yes"
    if any(k in scope for k in HS_NO):
        return "no"
    return "maybe"


def categorize(text):
    low = text.lower()
    return [c for c, kws in CATEGORIES.items() if any(k in low for k in kws)] or ["其他"]


def difficulty(text, prize, elig=""):
    score, why = 2, []
    if "高中" in elig and not any(k in elig for k in ("大學", "大專", "社會", "不限")):
        score -= 1; why.append("只限高中生參加，對手程度相近")
    if any(k in text for k in ("國際賽", "國際級", "全球", "International", "international")):
        score += 1; why.append("國際級比賽")
    if prize and prize >= 100_000:
        score += 1; why.append("獎金 10 萬以上，競爭通常較激烈")
    if sum(k in text for k in ("初賽", "複賽", "決賽", "初選", "決選")) >= 2:
        score += 1; why.append("有多階段評審")
    elif any(k in text for k in ("高中組", "高中職組", "學生組", "青少年組")):
        score -= 1; why.append("有高中／學生專屬組別")
    if prize and prize < 20_000:
        score -= 1; why.append("獎金規模較小")
    if any(k in text for k in ("入門", "初學", "零基礎", "不限經驗", "心得", "隨手拍")):
        score -= 1; why.append("標示適合初學者")
    return max(1, min(3, score)), why or ["沒有明顯的難易線索，預設為進階"]


def parse_detail(url, html):
    soup = BeautifulSoup(html, "html.parser")
    ld = jsonld(soup)
    for t in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    title = meta(soup, "og:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    title = re.split(r"\s*[|｜]\s*(獎金獵人|Bhuntr)", title)[0].strip() or url
    summary = (meta(soup, "og:description") or meta(soup, "description") or text[:150])[:150]
    organizer = ""
    if isinstance(ld.get("organizer"), dict):
        organizer = ld["organizer"].get("name", "")
    if not organizer:
        m = re.search(r"主辦(單位)?[:：\s]*([^\s，,。]{2,30})", text)
        organizer = m.group(2) if m else ""

    elig = snippet(text, ("參賽資格", "參加對象", "徵件對象", "報名資格", "參賽對象"))
    deadline = find_deadline(text, ld)
    prize = find_prize(text)
    diff, why = difficulty(text, prize, elig)
    return {
        "url": url,
        "title": title,
        "organizer": organizer,
        "summary": summary,
        "eligibility": elig,
        "deadline": deadline.isoformat() if deadline else None,
        "prize": prize,
        "categories": categorize(title + " " + text[:3000]),
        "difficulty": diff,
        "difficulty_reasons": why,
        "high_school": high_school_fit(elig, text),
    }


# ---------- 主程式 ----------
def load_existing():
    try:
        with open(OUT, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("sample"):
            return {}
        return {it["url"]: it for it in data.get("items", [])}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def still_open(it):
    if it.get("deadline"):
        return dt.date.fromisoformat(it["deadline"]) >= TODAY
    seen = dt.date.fromisoformat(it.get("first_seen", TODAY.isoformat()))
    return (TODAY - seen).days <= 60  # 沒寫截止日的，60 天後自動移除


def main():
    known = load_existing()
    urls = []
    for page in range(1, MAX_PAGES + 1):
        page_url = LIST_URL if page == 1 else f"{LIST_URL}?{PAGE_PARAM}={page}"
        html = get(page_url)
        if not html:
            break
        new = [u for u in links_from_list(html) if u not in urls]
        print(f"📄 第 {page} 頁：找到 {len(new)} 個比賽連結")
        if not new:
            break
        urls += new

    added = 0
    for u in urls:
        if u in known:
            continue
        html = get(u)
        if not html:
            continue
        item = parse_detail(u, html)
        item["first_seen"] = TODAY.isoformat()
        if item["high_school"] == "no":
            print("  ⏭  不適合高中：", item["title"])
            continue
        known[u] = item
        added += 1
        print("  ✅", item["title"])

    items = sorted((it for it in known.values() if still_open(it)),
                   key=lambda it: it.get("deadline") or "9999")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "updated": dt.datetime.now(TZ).isoformat(timespec="minutes"),
            "source": BASE,
            "sample": False,
            "items": items,
        }, f, ensure_ascii=False, indent=1)
    print(f"🎯 完成：新增 {added} 筆，目前共 {len(items)} 筆仍可報名")
    if not urls:
        print("⚠️ 列表頁一個連結都沒抓到，原站結構可能不同，請調整 LIST_URL 或 DETAIL_RE")


if __name__ == "__main__":
    main()
