# web_agent.py
# 把 PASA 的 PaperAgent 改造为面向通用问答的 WebAgent
# 架构完全保留：search -> expand（多层）-> 最终生成答案
# 只替换：
#   1. 搜索函数：google_search_arxiv_id -> google_search_web
#   2. 抓取函数：search_section_by_arxiv_id -> fetch_webpage_content
#   3. PaperNode -> WebNode（字段名适配）
#   4. 新增：synthesize() 用 crawler LLM 综合所有证据生成最终答案

import re
import json
import threading
from web_node   import WebNode          # 见下面的 web_node.py
from models     import Agent
from web_utils  import (
    google_search_web,
    fetch_webpage_content,
    build_page_object,
)


class WebAgent:
    def __init__(
        self,
        user_query:     str,
        crawler:        Agent,   # 生成子查询 / 选择章节 / 综合答案
        selector:       Agent,   # 对每个网页打相关分
        prompts_path:   str = "web_agent_prompt.json",
        expand_layers:  int = 2,
        search_queries: int = 5,
        search_papers:  int = 10,   # 每个子查询搜多少条结果
        expand_papers:  int = 20,   # 每层展开多少个页面
        threads_num:    int = 20,
    ) -> None:
        self.user_query    = user_query
        self.crawler       = crawler
        self.selector      = selector
        # self.prompts       = json.load(open(prompts_path))
        with open(prompts_path, "r", encoding="utf-8") as f:
            self.prompts = json.load(f)

        self.expand_layers = expand_layers
        self.search_queries = search_queries
        self.search_papers  = search_papers
        self.expand_papers  = expand_papers
        self.threads_num    = threads_num


        # 根节点：存储整个搜索树的元信息
        self.root = WebNode({
            "title": user_query,
            "extra": {
                "touch_ids":              [],   # 已访问过的 URL（去重用）
                "crawler_recall_pages":   [],   # 所有抓到的页面标题
                "recall_pages":           [],   # selector 认为相关的页面标题
                "final_answer":           "",   # 最终答案
            }
        })

        self.pages_queue  = []   # 所有待展开的页面节点
        self.expand_start = 0    # 当前层展开的起始位置
        self.lock         = threading.Lock()

        # 正则模板（和 PASA 保持一致，改 prompt 里的占位符即可）
        self.templates = {
            "search_template": r"Search\](.*?)\[",   # 从 crawler 输出里提取子查询
            "expand_template": r"Expand\](.*?)\[",   # 从 crawler 输出里提取要展开的章节
        }

    # ------------------------------------------------------------------
    # 工具：并行执行
    # ------------------------------------------------------------------
    @staticmethod
    def do_parallel(func, args, num):
        threads = []
        for _ in range(num):
            thread = threading.Thread(target=func, args=args)
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()

    # ------------------------------------------------------------------
    # STEP 1 : search
    # 对应 PASA 的 search() + search_paper()
    # 用 crawler 生成若干子查询，对每个子查询调用 Serper，
    # 用 selector 打分，高分页面进入 pages_queue
    # ------------------------------------------------------------------
    def _search_one_query(self, queries: list):
        """worker：从 queries 队列取一个查询，搜索并打分"""
        while queries:
            with self.lock:
                if not queries:
                    return
                query,self.root.child[query]  = queries.pop(),[]

            search_results = google_search_web(query, self.search_papers)
            page_objects   = [build_page_object(r) for r in search_results] # 这里的r是什么 # page_objects ~~ searched_papers
            print(f"web_agent里面的page_objects：{page_objects}") # web_agent里面的page_objects：[{'page_id': 'https://en.wikipedia.org/wiki/Citibank', 'title': 'Citibank - Wikipedia', 'abstract': 'Citibank was founded in 1812 as City Bank of New York, and later became First National City Bank of New York.', 'sections': {}, 'source': 'SearchFrom:web'}, {'page_id': 'https://www.citigroup.com/global/about-us/heritage/1812/new-bank-born-in-new-york', 'title': 'A new bank born in New York - Citi', 'abstract': '... U.S. President James Madison applied to set up a new bank. Noting that it ... United States. Enter one Samuel Osgood, elder statesman. He had a plan ...', 'sections': {}, 'source': 'SearchFrom:web'}, {'page_id': 'https://en.wikipedia.org/wiki/Citigroup', 'title': 'Citigroup - Wikipedia', 'abstract': 'Citi established the first fully operational U.S. bank branch in Hanoi in 1994. Following the branch opening in Ho Chi Minh City in 1998, ...', 'sections': {}, 'source': 'SearchFrom:web'}, {'page_id': 'https://time.com/archive/6687482/citibank-teetering-since-1812/', 'title': 'Citibank: Teetering Since 1812 - TIME', 'abstract': "James Stillman, who became City's president in 1891, combined prudence with great ambition. City Bank cruised through the Panic of 1893, thanks ...", 'sections': {}, 'source': 'SearchFrom:web'}, {'page_id': 'https://www.businessinsider.com/presenting-a-history-of-citi-2012-4', 'title': "The Dramatic Highlights From Citi's 200-Year History", 'abstract': 'In 1891, James Stillman is elected president of the bank and helps lead America onto the world stage. James Stillman. Timeline. Stillman ...', 'sections': {}, 'source': 'SearchFrom:web'}, {'page_id': 'https://www.citigroup.com/rcs/citigpa/storage/public/Citi%20Historic%20Records%20Review%20Summary.pdf', 'title': '[PDF] Citi Historic Records Review Summary The history of Citigroup Inc ...', 'abstract': 'Between 1837 and 1882, Moses Taylor was a director, controlling shareholder, and. President (1856-1882) of City Bank of New York. Taylor was also a director of ...', 'sections': {}, 'source': 'SearchFrom:web'}, {'page_id': 'https://portersfiveforce.com/blogs/brief-history/citigroup', 'title': "What is Brief History of Citi Company? - Porter's Five Forces", 'abstract': 'Chartered on June 16, 1812; operations began September 14, 1812 · First president: Samuel Osgood, former U.S. Postmaster General and ...', 'sections': {}, 'source': 'SearchFrom:web'}, {'page_id': 'https://www.streetofwalls.com/articles/investment-banking/learn-the-basics/citigroup/', 'title': 'Citigroup Profile | Street Of Walls', 'abstract': 'Beginning as the City Bank of New York, and later being renamed to Citibank in 1812, it became Bank Handlowy in 1870, Smith Barney in 1873, Banamex in 1884, ...', 'sections': {}, 'source': 'SearchFrom:web'}, {'page_id': 'https://www.youtube.com/watch?v=ah0V2gCDa80', 'title': "From 1812 Origins to One of America's Largest Banks - YouTube", 'abstract': 'How did Citibank grow from a small bank founded in 1812 in New York City into one of the largest financial institutions in the United States ...', 'sections': {}, 'source': 'SearchFrom:web'}, {'page_id': 'https://pestel-analysis.com/blogs/owners/citigroup', 'title': 'Who Owns Citi Company? - PESTEL Analysis', 'abstract': 'Founding (1812), City Bank of New York chartered by New York merchants with Samuel Osgood as first President. Initial capital: $2 million. ; Post ...', 'sections': {}, 'source': 'SearchFrom:web'}]

            # 用 selector 对每个页面的 snippet 打相关分
            select_prompts = [
                self.prompts["get_selected"].format(
                    title=p["title"],
                    abstract=p["abstract"],   # snippet 当摘要
                    user_query=self.user_query
                )
                for p in page_objects
            ]
            scores = self.selector.infer_score(select_prompts)

            with self.lock:
                for score, page in zip(scores, page_objects):
                    url = page["page_id"]
                    # 去重
                    if url in self.root.extra["touch_ids"]:
                        continue
                    self.root.extra["touch_ids"].append(url)

                    self.root.extra["crawler_recall_pages"].append(page["title"])
                    if score > 0.5:
                        self.root.extra["recall_pages"].append(page["title"])

                    node = WebNode({
                        "title":        page["title"],
                        "page_id":      url,
                        "depth":        0,
                        "abstract":     page["abstract"],
                        "sections":     {}, # 什么数据结构？？
                        "source":       page["source"],
                        "select_score": score,
                        "extra":        {},
                    })
                    self.root.child[query].append(node)
                    self.pages_queue.append(node)

    def search(self):
        """生成子查询，并行搜索"""
        prompt  = self.prompts["generate_query"].format(user_query=self.user_query).strip()
        raw_out = self.crawler.infer(prompt)
        queries = [
            q.strip()
            for q in re.findall(self.templates["search_template"], raw_out, flags=re.DOTALL)
        ][:self.search_queries]

        if not queries:
            # fallback：直接用原始问题搜索
            queries = [self.user_query]

        WebAgent.do_parallel(self._search_one_query, (queries,), len(queries))

    # ------------------------------------------------------------------
    # STEP 2 : expand（多层展开）
    # 对应 PASA 的 expand() + get_paper_content() + do_expand()
    # 选出高分页面 -> 抓完整正文 -> crawler 决定展开哪些段落 ->
    # 从段落里提取新的子查询/链接 -> 继续搜索
    # ------------------------------------------------------------------
    def _get_page_content(self, new_expand: list, crawl_prompts: list, have_full_pages: list):
        """worker：抓取页面完整正文，准备 crawler prompt"""
        while new_expand:
            with self.lock:
                if not new_expand:
                    break
                page = new_expand.pop(0)

            # 懒加载正文
            if not page.sections:
                sections = fetch_webpage_content(page.page_id)
                if not sections:
                    page.extra["expand"] = "fetch error"
                    continue
                page.sections = sections

            page.extra["expand"] = "not expand"
            # 让 crawler 决定展开哪些章节（用于判断哪些段落与问题最相关）
            prompt = self.prompts["select_section"].format(
                user_query = self.user_query,
                title      = page.title,
                abstract   = page.abstract,
                sections   = list(page.sections.keys()),
            ).strip()
            with self.lock:
                have_full_pages.append(page)
                crawl_prompts.append(prompt)

    def _do_expand(self, depth: int, have_full_pages: list, crawl_results: list):
        """
        worker：根据 crawler 选出的章节，提取段落文本，
        再生成新子查询，搜索新页面，打分，加入队列。
        """
        while have_full_pages:
            with self.lock:
                if not have_full_pages:
                    break
                page         = have_full_pages.pop(0)
                crawl_result = crawl_results.pop(0)

            # 解析 crawler 选择的章节
            chosen_sections = re.findall(self.templates["expand_template"], crawl_result, flags=re.DOTALL)
            chosen_sections = [s.strip() for s in chosen_sections if s.strip() in page.sections] # 有何意义？？？
            print(f"web_agent里面的 _do_expand里面的 chosen_sections：{chosen_sections}")
            print(f"web_agent里面的 _do_expand里面的 page.sections：{page.sections}") # 什么数据结构，怎么就是字典了？？

            if not chosen_sections:
                page.extra["expand"] = "no section chosen"
                continue

            # 把选中章节的文本拼起来，生成展开子查询
            context_text = "\n\n".join(
                f"[{sec}]\n{page.sections[sec]}" for sec in chosen_sections
            )
            expand_prompt = self.prompts["generate_expand_query"].format(
                user_query   = self.user_query,
                context_text = context_text[:4000],  # 防止 prompt 过长 # 4000够不够用啊
            ).strip()
            sub_queries_raw = self.crawler.infer(expand_prompt)
            sub_queries = [
                q.strip()
                for q in re.findall(self.templates["search_template"], sub_queries_raw, flags=re.DOTALL)
            ]

            if not sub_queries:
                page.extra["expand"] = "no sub-query generated"
                continue

            # 搜索子查询，打分，加入队列
            for sub_q in sub_queries[:3]:  # 每个页面最多展开3个子查询  3 # 是每个页面吗？？
                results    = google_search_web(sub_q, self.search_papers // 2)
                page_objs  = [build_page_object(r) for r in results]
                print(f"web_agent里面的 _do_expand里面的 page_objs：{page_objs}") # 什么数据结构？？
                s_prompts  = [
                    self.prompts["get_selected"].format(
                        title=p["title"], abstract=p["abstract"], user_query=self.user_query
                    )
                    for p in page_objs
                ]
                scores = self.selector.infer_score(s_prompts)

                # for score, pg in zip(scores, page_objs):
                #     url = pg["page_id"]
                #     with self.lock:
                with self.lock:
                    for score, pg in zip(scores, page_objs):
                        url = pg["page_id"]
                        if url in self.root.extra["touch_ids"]:
                            continue
                        self.root.extra["touch_ids"].append(url)
                        self.root.extra["crawler_recall_pages"].append(pg["title"])
                        if score > 0.5:
                            self.root.extra["recall_pages"].append(pg["title"])

                        child_node = WebNode({
                            "title":        pg["title"],
                            "page_id":      url,
                            "depth":        depth + 1,
                            "abstract":     pg["abstract"],
                            "sections":     {},
                            "source":       "Expand " + pg["source"],
                            "select_score": score,
                            "extra":        {},
                        })
                        if sub_q not in page.child:
                            page.child[sub_q] = []
                        page.child[sub_q].append(child_node)
                        page.extra["expand"] = "success"
                        self.pages_queue.append(child_node)

    def expand(self, depth: int):
        """按 select_score 排序，取 top-expand_papers 个节点展开"""
        new_pages = sorted(self.pages_queue[self.expand_start:],key=WebNode.sort_page,reverse=True)
        self.pages_queue = self.pages_queue[:self.expand_start] + new_pages
        if depth > 0:
            new_pages = new_pages[:self.expand_papers]
        self.expand_start = len(self.pages_queue)

        crawl_prompts, have_full_pages = [], []
        WebAgent.do_parallel(self._get_page_content,(new_pages, crawl_prompts, have_full_pages),self.threads_num)
        crawl_results = self.crawler.batch_infer(crawl_prompts)
        WebAgent.do_parallel(self._do_expand,(depth, have_full_pages, crawl_results),self.threads_num,)

    # ------------------------------------------------------------------
    # STEP 3 : synthesize
    # PASA 没有这步（它只输出论文列表），这是为了生成最终答案新增的
    # 把所有高分页面的 snippet 汇总，让 crawler 综合出最终答案
    # ------------------------------------------------------------------
    def synthesize(self) -> str:
        """综合所有相关页面的证据，生成最终答案"""
        # 收集所有高分节点的信息
        evidence_parts = []
        for node in self.pages_queue:
            if node.select_score > 0.5:
                evidence_parts.append(
                    f"[Source: {node.title}]\n{node.abstract}"
                )
                # 如果已经抓到正文，也加进来（截断）
                if node.sections:
                    for sec_title, sec_text in list(node.sections.items())[:2]:
                        evidence_parts.append(f"  [{sec_title}]: {sec_text[:500]}")

        if not evidence_parts:
            # 兜底：用所有节点
            for node in self.pages_queue[:5]:
                evidence_parts.append(f"[Source: {node.title}]\n{node.abstract}")

        evidence_text = "\n\n".join(evidence_parts[:20])  # 最多20条证据

        prompt = self.prompts["synthesize_answer"].format(
            user_query    = self.user_query,
            evidence_text = evidence_text[:6000],
        ).strip()

        answer = self.crawler.infer(prompt)
        self.root.extra["final_answer"] = answer.strip()
        return self.root.extra["final_answer"]

    # ------------------------------------------------------------------
    # 主流程：search -> expand x N -> synthesize
    # ------------------------------------------------------------------
    def run(self) -> str:
        self.search()
        for depth in range(self.expand_layers):
            self.expand(depth)
        return self.synthesize()
