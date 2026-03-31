# web_utils.py
# 把 PASA 里针对 arxiv 的工具函数，替换成面向通用网页搜索的版本
# 供 WebAgent 使用，对应 bamboogle 数据集（通用问答）

import re
import json
import warnings
import requests
from bs4 import BeautifulSoup

# ============================================================
# 配置：在这里填入你的 Serper API Key
# 申请地址：https://serper.dev  （每月免费 2500 次）
# ============================================================
SERPER_KEY = "369343c86092bdbda17a9fb9b444ce36947b30c3"


# ============================================================
# 1. 核心搜索：用 Google Serper 搜索任意问题，返回结果列表
#    对应 PASA 的 google_search_arxiv_id()
#    返回格式：[{"url": ..., "title": ..., "snippet": ...}, ...]
# ============================================================
def google_search_web(query: str, num: int = 10) -> list[dict]:
    """
    用 Google Serper 搜索通用问题，返回 top-num 条结果。
    每条结果包含 url / title / snippet。
    """
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query, "num": num, "page": 1})
    headers = {"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"}

    assert SERPER_KEY != "your_serper_api_key_here", \
        "请先在 web_utils.py 里填入你的 Serper API Key！"

    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, data=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("organic", []):
                    results.append({
                        "url":     item.get("link", ""),
                        "title":   item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                    })
                # 如果有 answerBox（直接答案框），把它放在第一位
                answer_box = data.get("answerBox", {})
                if answer_box:
                    results.insert(0, {
                        "url":     answer_box.get("link", "direct_answer"),
                        "title":   answer_box.get("title", "Answer Box"),
                        "snippet": answer_box.get("answer", answer_box.get("snippet", "")),
                    })
                return results[:num]
        except Exception as e:
            warnings.warn(f"Serper 搜索失败（第{attempt+1}次），query={query}，错误={e}")
    return []


# ============================================================
# 2. 抓取网页正文
#    对应 PASA 的 search_section_by_arxiv_id()
#    返回格式：{"<段落标题或序号>": "<正文文本>", ...}
#    失败时返回 None
# ============================================================
def fetch_webpage_content(url: str, max_chars: int = 8000) -> dict | None:
    """
    抓取网页，提取正文段落，返回 {section_title: text} 字典。
    max_chars：每个页面保留的最大字符数，避免 prompt 过长。
    """
    if url == "direct_answer":
        return None

    headers = { # 好奇怪
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            warnings.warn(f"抓取失败 status={resp.status_code} url={url}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # 移除脚本/样式/导航等噪声标签
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "form", "noscript", "iframe"]):
            tag.decompose()

        # 尝试找主正文容器（article / main / div#content 等）
        main = (
            soup.find("article") or
            soup.find("main") or
            soup.find("div", {"id": re.compile(r"content|main|article", re.I)}) or
            soup.find("div", {"class": re.compile(r"content|main|article|post", re.I)}) or
            soup.body
        )
        if main is None:
            return None

        # 按段落 / 标题切分成小节
        sections = {}
        current_title = "intro"
        current_text = []

        for elem in main.descendants:
            if not hasattr(elem, "name"):
                continue
            if elem.name in ("h1", "h2", "h3", "h4"):
                # 保存上一节
                text = " ".join(current_text).strip()
                if text:
                    sections[current_title] = text[:2000]  # 每节最多2000字
                current_title = elem.get_text(strip=True)[:80]
                current_text = []
            elif elem.name == "p":
                t = elem.get_text(strip=True)
                if len(t) > 20:  # 过滤太短的碎片
                    current_text.append(t)

        # 保存最后一节
        text = " ".join(current_text).strip()
        if text:
            sections[current_title] = text[:2000]

        if not sections:
            # fallback：直接取全文
            full_text = main.get_text(separator=" ", strip=True)
            full_text = re.sub(r"\s+", " ", full_text)[:max_chars]
            if full_text:
                sections["full_text"] = full_text

        return sections if sections else None

    except Exception as e:
        warnings.warn(f"抓取网页异常 url={url}，错误={e}")
        return None


# ============================================================
# 3. 把搜索结果直接包装成 "page 对象"
#    对应 PASA 的 search_paper_by_arxiv_id()
#    返回字段名和 PASA paper 对象保持一致，方便复用 PaperNode
# ============================================================
def build_page_object(search_result: dict) -> dict:
    """
    把 Serper 的一条搜索结果包装成和 PASA paper 对象兼容的字典：
    {
        "page_id":  URL（相当于 arxiv_id），
        "title":    网页标题,
        "abstract": snippet（相当于摘要，快速判断相关性用）,
        "sections": {}（先留空，expand 时再抓完整正文）,
        "source":   "SearchFrom:web",
    }
    """
    return {
        "page_id":  search_result["url"],
        "title":    search_result["title"],
        "abstract": search_result["snippet"],
        "sections": {},          # 懒加载，expand 时才抓
        "source":   "SearchFrom:web",
    }


# ============================================================
# 4. 评估工具：计算 Bamboogle acc
#    Bamboogle 的标准评估用 exact match（不区分大小写，去标点）
# ============================================================
import string

def normalize_answer(s: str) -> str:
    """小写 + 去标点 + 去多余空格"""
    s = s.lower()
    s = s.translate(str.maketrans("", "", string.punctuation))
    s = re.sub(r"\s+", " ", s).strip()
    return s

def exact_match(pred: str, gold: str) -> bool:
    return normalize_answer(pred) == normalize_answer(gold)

def contains_match(pred: str, gold: str) -> bool:
    """宽松版：gold 出现在 pred 里就算对（应对答案是短词/数字的情况）"""
    return normalize_answer(gold) in normalize_answer(pred)
