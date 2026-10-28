# web_utils.py
# 把 PASA 里针对 arxiv 的工具函数，替换成面向通用网页搜索的版本
# 供 WebAgent 使用，对应 bamboogle 数据集（通用问答）

import re
import json
import warnings
import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException

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
            resp = requests.post(url, headers=headers, data=payload, timeout=10) # <Response [200]>
            print(f"web_utils.py里面的 GGGGGoogle_search_web里面的 resp：{resp}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"web_utils.py里面的 GGGGGoogle_search_web里面的 data：{data}") # web_utils.py里面的 GGGGGoogle_search_web里面的 data：{'searchParameters': {'q': 'president of the United States when Citibank was founded', 'type': 'search', 'num': 10, 'page': 1, 'engine': 'google'}, 'organic': [{'title': 'Citibank - Wikipedia', 'link': 'https://en.wikipedia.org/wiki/Citibank', 'snippet': 'Citibank was founded in 1812 as City Bank of New York, and later became First National City Bank of New York.', 'position': 1}, {'title': 'A new bank born in New York - Citi', 'link': 'https://www.citigroup.com/global/about-us/heritage/1812/new-bank-born-in-new-york', 'snippet': '... U.S. President James Madison applied to set up a new bank. Noting that it ... United States. Enter one Samuel Osgood, elder statesman. He had a plan ...', 'position': 2}, {'title': 'Citigroup - Wikipedia', 'link': 'https://en.wikipedia.org/wiki/Citigroup', 'snippet': 'Citi established the first fully operational U.S. bank branch in Hanoi in 1994. Following the branch opening in Ho Chi Minh City in 1998, ...', 'position': 3}, {'title': 'Citibank: Teetering Since 1812 - TIME', 'link': 'https://time.com/archive/6687482/citibank-teetering-since-1812/', 'snippet': "James Stillman, who became City's president in 1891, combined prudence with great ambition. City Bank cruised through the Panic of 1893, thanks ...", 'date': 'Jan 20, 2009', 'position': 4}, {'title': "The Dramatic Highlights From Citi's 200-Year History", 'link': 'https://www.businessinsider.com/presenting-a-history-of-citi-2012-4', 'snippet': 'In 1891, James Stillman is elected president of the bank and helps lead America onto the world stage. James Stillman. Timeline. Stillman ...', 'date': 'Apr 4, 2012', 'attributes': {'Missing': 'founded | Show results with:founded'}, 'position': 5}, {'title': '[PDF] Citi Historic Records Review Summary The history of Citigroup Inc ...', 'link': 'https://www.citigroup.com/rcs/citigpa/storage/public/Citi%20Historic%20Records%20Review%20Summary.pdf', 'snippet': 'Between 1837 and 1882, Moses Taylor was a director, controlling shareholder, and. President (1856-1882) of City Bank of New York. Taylor was also a director of ...', 'position': 6}, {'title': "What is Brief History of Citi Company? - Porter's Five Forces", 'link': 'https://portersfiveforce.com/blogs/brief-history/citigroup', 'snippet': 'Chartered on June 16, 1812; operations began September 14, 1812 · First president: Samuel Osgood, former U.S. Postmaster General and ...', 'date': 'Nov 10, 2025', 'attributes': {'Missing': 'United States'}, 'position': 7}, {'title': 'Citigroup Profile | Street Of Walls', 'link': 'https://www.streetofwalls.com/articles/investment-banking/learn-the-basics/citigroup/', 'snippet': 'Beginning as the City Bank of New York, and later being renamed to Citibank in 1812, it became Bank Handlowy in 1870, Smith Barney in 1873, Banamex in 1884, ...', 'position': 8}, {'title': "From 1812 Origins to One of America's Largest Banks - YouTube", 'link': 'https://www.youtube.com/watch?v=ah0V2gCDa80', 'snippet': 'How did Citibank grow from a small bank founded in 1812 in New York City into one of the largest financial institutions in the United States ...', 'date': 'Mar 8, 2026', 'attributes': {'Missing': 'president | Show results with:president'}, 'position': 9}, {'title': 'Who Owns Citi Company? - PESTEL Analysis', 'link': 'https://pestel-analysis.com/blogs/owners/citigroup', 'snippet': 'Founding (1812), City Bank of New York chartered by New York merchants with Samuel Osgood as first President. Initial capital: $2 million. ; Post ...', 'date': 'Sep 30, 2025', 'attributes': {'Missing': 'United | Show results with:United'}, 'position': 10}], 'peopleAlsoAsk': [{'question': 'Who was the first president of Citi?', 'snippet': "Since the bank's founding in 1812, it has been led by a President, with Samuel Osgood being elected as the first President.", 'title': 'Citibank - Wikipedia', 'link': 'https://en.wikipedia.org/wiki/Citibank'}], 'relatedSearches': [{'query': 'Citibank login'}, {'query': 'Citibank international branches'}, {'query': 'Citibank origin country'}, {'query': 'Citibank CEO'}, {'query': 'Citibank Bangladesh'}, {'query': 'Citi bank India'}, {'query': 'Citibank headquarters'}, {'query': 'Citi Bank customer service'}], 'credits': 1}
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
                print(f"web_utils.py里面的 google_search_web()的 最后返回results[:num]：{results[:num]}")
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
def fetch_webpage_content(url: str, max_chars: int = 8000) -> dict | None: # 通过 requests + BeautifulSoup 抓取网页 → 清洗噪声 → 定位正文主容器 → 按照“标题 + 段落”结构切分成字典
    """
    抓取网页，提取正文段落，返回 {section_title: text} 字典。
    max_chars：每个页面保留的最大字符数，避免 prompt 过长。
    """
    if url == "direct_answer":
        return None
    
    # === 关键：设置 SOCKS5 代理（走你的 1824 端口）===
    proxies = {
        "http": "socks5h://127.0.0.1:1824",
        "https": "socks5h://127.0.0.1:1824"
    }

    # headers = { # 好奇怪
    #     "User-Agent": (
    #         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    #         "AppleWebKit/537.36 (KHTML, like Gecko) "
    #         "Chrome/120.0.0.0 Safari/537.36"
    #     )
    # }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.google.com/", # 伪装是从搜索引擎跳转过来的
    }
    try:
        resp = requests.get(url, headers=headers, timeout=50,proxies=proxies,allow_redirects=True)
        print(f"web_utils.py里面的 fetch_webpage_content里面的 resp：{resp}")
        if resp.status_code != 200:
            warnings.warn(f"抓取失败：fetch_webpage_content resp.status_code != 200 status={resp.status_code} url={url}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser") # 解析成dom树

        # 暴力删除所有噪声标签（脚本、样式、导航、页眉页脚等）
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "form", "noscript", "iframe"]):
            tag.decompose()

        # 尝试找到正文主容器（优先级从高到低）
        main = (
            soup.find("article") or
            soup.find("main") or
            soup.find("div", {"id": re.compile(r"content|main|article", re.I)}) or
            soup.find("div", {"class": re.compile(r"content|main|article|post", re.I)}) or
            soup.body
        )
        print(f"wen_utils.py里面的 fetch_webpage_content()里面的 main:{main}")
        if main is None:
            return None

        # 按段落 / 标题切分成小节
        sections = {} # # 最终要返回的字典：{标题: 正文}
        current_title = "intro" # # 当前正在收集的章节标题，初始是“引言”？？？？？？？？？？
        current_text = [] # # 当前章节正在累积的段落列表

        for elem in main.descendants: # BeautifulSoup 提供的生成器，它会按照文档顺序（depth-first, document order） 遍历 main 标签下的所有后代节点（包括子节点、孙节点……一直到最深层的文本节点）。相当于把整个正文区域“从上到下、从左到右”线性扫一遍，不会漏掉嵌套的结构。
            if not hasattr(elem, "name"): # 这里直接跳过所有纯文本节点，只处理标签节点
                continue
            if elem.name in ("h1", "h2", "h3", "h4"): # 遇到一级到四级标题时，就认为“新的一节开始了”。
                # 保存上一节
                text = " ".join(current_text).strip()
                if text:
                    sections[current_title] = text[:2000]  # 每节最多2000字
                current_title = elem.get_text(strip=True)[:80]
                current_text = []
            elif elem.name == "p": # 遇到 <p> 标签时，才认为是正文段落。
                t = elem.get_text(strip=True) # 会把标签内所有文本提取出来，并自动去除首尾空格、换行等。
                if len(t) > 20:  # 过滤太短的碎片
                    current_text.append(t)

        # 保存最后一节。如果页面最后一段没有被标题打断（最常见情况），循环结束后 current_text 里还有内容，必须手动保存一次。
        text = " ".join(current_text).strip()
        if text:
            sections[current_title] = text[:2000]

        if not sections: # 有些极简/古怪页面可能没有 <h1>~<h4> 和 <p>（比如全是 <div>），这时就退化为“把整个正文区打平”作为 fallback。
            # fallback：直接取全文
            full_text = main.get_text(separator=" ", strip=True)
            full_text = re.sub(r"\s+", " ", full_text)[:max_chars]
            if full_text:
                sections["full_text"] = full_text

        return sections if sections else None

    except RequestException as e:   # 更精确捕获网络异常
        warnings.warn(f"fetch_webpage_content 抓取异常 url={url}，错误={e}")
        return None
    except Exception as e:
        warnings.warn(f"fetch_webpage_content except 抓取网页异常 url={url}，错误={e}")
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
