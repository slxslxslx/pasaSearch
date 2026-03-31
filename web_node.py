# web_node.py
# 把 PASA 的 PaperNode 改造为 WebNode，字段名适配网页搜索
# 接口和 PaperNode 完全一致，方便复用 WebAgent 里的排序/序列化逻辑

class WebNode:
    def __init__(self, data: dict):
        # 核心字段
        self.title        = data.get("title", "")
        self.page_id      = data.get("page_id", "")       # 对应 arxiv_id，这里是 URL
        self.depth        = data.get("depth", 0)
        self.abstract     = data.get("abstract", "")      # snippet / 摘要
        self.sections     = data.get("sections", {})      # 正文分节，懒加载
        self.source       = data.get("source", "")        # Root
        self.select_score = data.get("select_score", 0.0)
        self.extra        = data.get("extra", {})
        self.child        = {}                             # {查询/章节 -> [WebNode]}

    # ------------------------------------------------------------------
    # 排序键（供 WebAgent.expand() 用）：高分优先展开
    # ------------------------------------------------------------------
    @staticmethod
    def sort_page(node: "WebNode") -> float:
        return node.select_score

    # ------------------------------------------------------------------
    # 序列化（用于保存结果到 JSON）
    # ------------------------------------------------------------------
    def todic(self) -> dict:
        return {
            "title":        self.title,
            "page_id":      self.page_id,
            "depth":        self.depth,
            "abstract":     self.abstract,
            "sections":     self.sections,
            "source":       self.source,
            "select_score": self.select_score,
            "extra":        self.extra,
            "child": {key: [c.todic() for c in children] for key, children in self.child.items()},
        }
