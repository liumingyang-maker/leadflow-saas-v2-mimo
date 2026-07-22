from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI


@dataclass
class ReviewResult:
    round: str
    verdict: str  # PASS or FAIL
    notes: str
    issues: list[str]


class DeepSeekReviewer:
    def __init__(self) -> None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is required")

        self.client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.prompts_dir = Path(__file__).parent / "review_prompts"

    def _load_prompt(self, round_name: str) -> str:
        prompt_file = self.prompts_dir / f"{round_name}.txt"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Review prompt not found: {prompt_file}")
        return prompt_file.read_text(encoding="utf-8")

    def _call_api(self, system_prompt: str, user_content: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content

    def review(self, round_name: str, diff: str, context: str, strict: bool = True) -> ReviewResult:
        prompt = self._load_prompt(round_name)
        strictness = "严格审查，任何问题都必须FAIL" if strict else "中等严格度，只关注严重问题"

        user_content = f"""
## 严格度
{strictness}

## 代码变更
```diff
{diff}
```

## 任务上下文
{context}

请返回JSON格式:
{{
  "verdict": "PASS或FAIL",
  "notes": "审查说明",
  "issues": ["问题1", "问题2"]
}}
"""

        response = self._call_api(prompt, user_content)

        # 提取JSON部分
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start == -1 or json_end == 0:
            raise ValueError(f"Invalid response format: {response}")

        result = json.loads(response[json_start:json_end])

        return ReviewResult(
            round=round_name,
            verdict=result.get("verdict", "FAIL"),
            notes=result.get("notes", ""),
            issues=result.get("issues", []),
        )

    def review_all(self, diff: str, context: str) -> dict[str, ReviewResult]:
        rounds = {
            "architecture": True,  # 严格
            "security": True,  # 严格
            "ui": False,  # 中等
            "release": True,  # 严格
        }

        results: dict[str, ReviewResult] = {}
        for round_name, strict in rounds.items():
            results[round_name] = self.review(round_name, diff, context, strict)

        return results


if __name__ == "__main__":
    # 简单测试
    reviewer = DeepSeekReviewer()
    print(f"DeepSeek reviewer initialized, model: {reviewer.model}")
    print(f"Prompts directory: {reviewer.prompts_dir}")
    print("Ready for reviews.")
