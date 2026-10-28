# run_web_agent.py
# 对应 PASA 的 run_paper_agent.py
# 跑 Bamboogle 数据集，输出每条结果和最终 Accuracy

import os
import json
import argparse
from models     import Agent
from web_agent  import WebAgent
from web_utils  import exact_match, contains_match

parser = argparse.ArgumentParser()
parser.add_argument("--input_file",     type=str, default="data/bamboogle_data.jsonl")
parser.add_argument("--crawler_path",   type=str, default="/data1/llm/pasa/checkpoints/pasa-7b-crawler") # crawler 模型路径（或 API 模型名）"checkpoints/pasa-7b-crawler"
parser.add_argument("--selector_path",  type=str, default="/data1/llm/pasa/checkpoints/pasa-7b-selector")
parser.add_argument("--output_folder",  type=str, default="results/bamboogle")
parser.add_argument("--prompts_path",   type=str, default="web_agent_prompt.json")
parser.add_argument("--expand_layers",  type=int, default=2)
parser.add_argument("--search_queries", type=int, default=2) # 初始子查询数量 5
parser.add_argument("--search_papers",  type=int, default=10) # 每个查询搜索的页面数 10
parser.add_argument("--expand_papers",  type=int, default=2) # 每层最多展开的页面数 20
parser.add_argument("--threads_num",    type=int, default=1) # 20
parser.add_argument("--match_mode",     type=str, default="contains", choices=["exact", "contains"]) # exact=严格匹配；contains=答案是预测的子串（推荐）
args = parser.parse_args()

# ----------------------------------------------------------------
# 加载模型（和 PASA 完全一样）
# ----------------------------------------------------------------
crawler  = Agent(args.crawler_path)
selector = Agent(args.selector_path)

# ----------------------------------------------------------------
# 准备输出目录
# ----------------------------------------------------------------
os.makedirs(args.output_folder, exist_ok=True)
summary_path = os.path.join(args.output_folder, "prediction.jsonl")

# ----------------------------------------------------------------
# 主循环
# ----------------------------------------------------------------
total, correct = 0, 0
match_fn = contains_match if args.match_mode == "contains" else exact_match

with open(args.input_file) as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    data = json.loads(line)
    id = data["id"]
    question   = data["question"]
    gold_answer = data.get("answer", "")

    print(f"\n[{id+1}/{len(lines)}] Q: {question}")
    print(f"  Gold: {gold_answer}")

    # 构建 WebAgent（和 PASA 的 PaperAgent 接口完全一样）
    agent = WebAgent(
        user_query     = question,
        crawler        = crawler,
        selector       = selector,
        prompts_path   = args.prompts_path,
        expand_layers  = args.expand_layers,
        search_queries = args.search_queries,
        search_papers  = args.search_papers,
        expand_papers  = args.expand_papers,
        threads_num    = args.threads_num,
    )

    # 运行（search + expand + synthesize）
    pred_answer = agent.run()
    print(f"  Pred: {pred_answer}")

    # 评估
    is_correct = match_fn(pred_answer, gold_answer)
    total  += 1
    correct += int(is_correct)
    acc     = correct / total

    print(f"  {'✓' if is_correct else '✗'}  Running Acc: {correct}/{total} = {acc:.4f}")

    # 保存单条结果
    result_path = os.path.join(args.output_folder, f"{id}.json")
    json.dump(
        {
            "id":           data.get("id", id),
            "question":     question,
            "gold_answer":  gold_answer,
            "pred_answer":  pred_answer,
            "correct":      is_correct,
            "search_tree":  agent.root.todic(),
        },
        open(result_path, "w"),
        indent=2,  # 每一层嵌套缩进 2 个空格
        ensure_ascii=False,
    )

    # 实时追加到 summary
    with open(summary_path, "a") as sf:
        sf.write(json.dumps({
            "id":          data.get("id", id),
            "question":    question,
            "gold_answer": gold_answer,
            "pred_answer": pred_answer,
            "correct":     is_correct,
        }, ensure_ascii=False) + "\n")

# ----------------------------------------------------------------
# 最终结果
# ----------------------------------------------------------------
print(f"\n{'='*50}")
print(f"Bamboogle Accuracy ({args.match_mode} match): {correct}/{total} = {correct/total:.4f}")
print(f"Results saved to: {args.output_folder}")
print(f"{'='*50}")
