# models.py
# 用 vLLM 重写 PASA 的 Agent 类，适配 internlm2_5-7b-chat
# 接口与原版完全一致：infer() / infer_score() / batch_infer()

import math
from vllm import LLM, SamplingParams
from transformers import AutoTokenizer

class Agent:
    def __init__(self, model_name: str):
        """
        model_name: 模型路径，例如 /data1/llm/internlm2_5-7b-chat
        crawler 和 selector 都用这个类，传同一个路径即可共享权重，
        也可以分别传不同路径（如果你以后想用不同模型）。
        """
        # vLLM 引擎：自动使用所有可见 GPU
        self.llm = LLM(
            model            = model_name,
            trust_remote_code = True,      # internlm 需要
            dtype            = "auto",
            max_model_len    = 4096,       # 防止显存不够，可以按需调小
            gpu_memory_utilization = 0.85, # 留一点给系统，可按需调整
        )
        # tokenizer 单独加载，用于 apply_chat_template
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code = True,
            padding_side      = "left",
        )

    # ------------------------------------------------------------------
    # 私有工具：把 prompt 字符串列表转成 chat 格式的文本列表
    # ------------------------------------------------------------------
    def _to_chat_texts(self, prompts: list[str]) -> list[str]:
        texts = []
        for prompt in prompts:
            text = self.tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt.strip()}],
                tokenize             = False,
                add_generation_prompt = True,
            )
            texts.append(text)
        return texts

    # ------------------------------------------------------------------
    # infer_score：批量打相关性分（对应 selector 的用途）
    # 原版：取下一个 token 是 "True" 的 softmax 概率
    # vLLM 版：用 logprobs=20 拿 top-20 token 的 log 概率，
    #          找 "True" / "true" / "Yes" / "yes" 等肯定词，
    #          softmax 归一化后返回概率
    # ------------------------------------------------------------------
    def infer_score(self, prompts: list[str]) -> list[float]:
        if not prompts:
            return []

        texts = self._to_chat_texts(prompts)

        # 只生成 1 个 token，拿 logprobs
        sampling_params = SamplingParams(
            max_tokens  = 1,
            temperature = 0.0,       # greedy
            logprobs    = 20,        # 拿 top-20 token 的 log 概率
        )
        outputs = self.llm.generate(texts, sampling_params)

        # 肯定词 token（internlm 分词后这些词通常是单 token）
        # 如果你的模型把 "True" 分成多个 token，fallback 到 yes/Yes
        pos_words = {"True", "true", "Yes", "yes", "TRUE", "YES"}

        scores = []
        for output in outputs:
            token_logprobs = output.outputs[0].logprobs  # list[dict]
            if not token_logprobs:
                scores.append(0.0)
                continue

            # token_logprobs[0] 是第一个（也是唯一一个）生成位置的 top-k dict
            # 格式：{token_id: Logprob(logprob=..., decoded_token=...)}
            top_tokens = token_logprobs[0]  # dict: token_id -> Logprob

            # 收集肯定词和全部词的 log 概率，用于 softmax
            pos_logprob = None
            all_logprobs = []

            for token_id, logprob_obj in top_tokens.items():
                lp = logprob_obj.logprob
                all_logprobs.append(lp)
                decoded = logprob_obj.decoded_token.strip()
                if decoded in pos_words:
                    # 有多个肯定词时取最大的（概率最高的那个）
                    if pos_logprob is None or lp > pos_logprob:
                        pos_logprob = lp

            if pos_logprob is None:
                # top-20 里没有任何肯定词，视为不相关
                scores.append(0.0)
            else:
                # softmax：pos_prob / sum(all_probs)
                # 在 log 空间计算避免数值溢出
                max_lp   = max(all_logprobs)
                sum_exp  = sum(math.exp(lp - max_lp) for lp in all_logprobs)
                pos_prob = math.exp(pos_logprob - max_lp) / sum_exp
                scores.append(pos_prob)

        return scores

    # ------------------------------------------------------------------
    # infer：单条推理（对应 crawler 生成子查询/选章节/综合答案）
    # ------------------------------------------------------------------
    def infer(self, prompt: str, sample: bool = False) -> str:
        texts = self._to_chat_texts([prompt])

        if sample:
            sampling_params = SamplingParams(
                max_tokens  = 512,
                temperature = 0.8,
                top_p       = 0.9,
            )
        else:
            sampling_params = SamplingParams(
                max_tokens  = 512,
                temperature = 0.0,  # greedy
            )

        outputs = self.llm.generate(texts, sampling_params)
        return outputs[0].outputs[0].text.strip()

    # ------------------------------------------------------------------
    # batch_infer：批量推理（对应 crawler 批量选章节）
    # vLLM 原生支持批量，直接传列表即可，不需要手动分 batch
    # ------------------------------------------------------------------
    def batch_infer(self, prompts: list[str], batch_size: int = 8, sample: bool = False) -> list[str]:
        if not prompts:
            return []

        texts = self._to_chat_texts(prompts)

        if sample:
            sampling_params = SamplingParams(
                max_tokens  = 512,
                temperature = 0.8,
                top_p       = 0.9,
            )
        else:
            sampling_params = SamplingParams(
                max_tokens  = 512,
                temperature = 0.0,
            )

        # vLLM 内部自动做连续批处理，batch_size 参数保留但不需要手动分块
        outputs = self.llm.generate(texts, sampling_params)
        return [out.outputs[0].text.strip() for out in outputs]


# ------------------------------------------------------------------
# 快速验证脚本
# ------------------------------------------------------------------
if __name__ == "__main__":
    MODEL_PATH = "/data1/llm/internlm2_5-7b-chat"

    print("Loading model...")
    agent = Agent(MODEL_PATH)

    # 测试 infer_score
    test_prompts = [
        "Is Paris the capital of France? Output format: Decision: True/False\nDecision:",
        "Is the moon made of cheese? Output format: Decision: True/False\nDecision:",
    ]
    scores = agent.infer_score(test_prompts)
    print(f"\ninfer_score results: {scores}")
    # 期望：第一个接近 1.0，第二个接近 0.0

    # 测试 infer
    answer = agent.infer("What is 2 + 2? Answer with just the number.")
    print(f"\ninfer result: {answer}")

    # 测试 batch_infer
    batch_answers = agent.batch_infer([
        "What is the capital of Japan? Answer in one word.",
        "What color is the sky? Answer in one word.",
    ])
    print(f"\nbatch_infer results: {batch_answers}")
