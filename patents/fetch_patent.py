"""Google Patents 원문에서 서지·초록·대표 청구항·PDF 링크를 뽑는다.

usage: python3 -I patents/fetch_patent.py <out_dir> <번호> [<번호> ...]
요청 사이에 8초씩 쉬고, 차단 페이지("Sorry...")가 나오면 그 번호는 건너뛰고 표시만 한다.
"""
import html, json, re, subprocess, sys, time, os

out_dir, nums = sys.argv[1], sys.argv[2:]
os.makedirs(out_dir, exist_ok=True)

def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()

res = []
for i, n in enumerate(nums):
    if i:
        time.sleep(8)
    path = os.path.join(out_dir, n + ".html")
    subprocess.run(["curl", "-s", "-m", "40", "-o", path,
                    f"https://patents.google.com/patent/{n}/en"], check=False)
    t = open(path, encoding="utf-8", errors="ignore").read() if os.path.exists(path) else ""
    if "<title>Sorry" in t or len(t) < 5000:
        res.append({"번호": n, "상태": "원문 못 읽음(차단/없음)"})
        continue
    g = lambda p: (re.search(p, t, re.S) or [None, ""])[1]
    a = t.find('itemprop="abstract"')
    ab = text(t[a:a + 4000]).replace("Abstract ", "", 1).split(" Description ")[0] if a >= 0 else ""
    c = t.find('itemprop="claims"')
    cl = text(t[c:c + 6000]) if c >= 0 else ""
    cl = re.split(r" 2\. ", cl)[0]
    res.append({
        "번호": n, "상태": "OK",
        "제목": text(g(r'<meta name="DC.title" content="([^"]*)"')),
        "출원인": text(g(r'<dd itemprop="assigneeOriginal"[^>]*>(.*?)</dd>')),
        "출원일": g(r'<time itemprop="filingDate"[^>]*>([^<]+)'),
        "공개일": g(r'<time itemprop="publicationDate"[^>]*>([^<]+)'),
        "초록": ab[:1500],
        "대표청구항": cl[:2500],
        "PDF": g(r'<a href="(https://patentimages[^"]+\.pdf)"'),
    })
print(json.dumps(res, ensure_ascii=False, indent=1))
