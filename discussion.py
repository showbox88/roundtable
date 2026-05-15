"""讨论室：每天一个话题，3 个不同立场的 agent 轮番发言，最后总结。
走 Claude Code 订阅（claude-agent-sdk），不消耗 API key。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from agents import AGENTS

log = logging.getLogger(__name__)

MODEL = "sonnet"
ROUNDS = 2
OUTPUT_DIR = Path(__file__).parent / "output"
QUERY_TIMEOUT_S = 180.0


def _options(system_prompt: str | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        allowed_tools=[],
        permission_mode="default",
        model=MODEL,
        system_prompt=system_prompt,
    )


async def _run(prompt: str, system: str | None = None) -> str:
    """单次查询，把 AssistantMessage 里的 TextBlock 拼起来返回。
    注意：要让 async generator 自然结束，不能 break，否则 SDK 内部 cleanup 会告警。
    """
    out: list[str] = []
    try:
        async with asyncio.timeout(QUERY_TIMEOUT_S):
            async for msg in query(prompt=prompt, options=_options(system)):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            out.append(block.text)
    except asyncio.TimeoutError:
        log.warning("query timed out after %ss", QUERY_TIMEOUT_S)
    return "\n".join(out).strip()


async def generate_topic() -> str:
    return await _run(
        "请生成一个适合多人辩论的今日话题。要求：\n"
        "1) 有思辨价值，存在多种合理立场\n"
        "2) 一句话，不超过 30 字\n"
        "3) 贴近当下，可以涉及科技、社会、生活、工作\n"
        "4) 直接输出话题本身，不要任何前缀、解释、引号、标点装饰"
    )


async def agent_speak(
    agent: dict,
    topic: str,
    transcript: str,
    round_num: int,
) -> str:
    system = (
        agent["persona"]
        + "\n\n规则：发言简洁有力，200 字以内。"
        "如果别人已发言，请明确回应、补充或反驳具体观点，不要重复立场表态。"
    )

    if transcript:
        prompt = (
            f"今日话题：{topic}\n\n"
            f"目前讨论记录：\n{transcript}\n"
            f"现在轮到你（{agent['name']}）发言，第 {round_num} 轮。"
        )
    else:
        prompt = (
            f"今日话题：{topic}\n\n"
            f"你是第一位发言者（{agent['name']}），请开场表态。"
        )
    return await _run(prompt, system=system)


async def summarize(topic: str, transcript: str) -> str:
    return await _run(
        f"以下是关于「{topic}」的多方讨论：\n\n{transcript}\n\n"
        "请作为中立观察者，输出一份结构化总结：\n"
        "1. 各方核心观点（每方一句）\n"
        "2. 共识与真正的分歧点\n"
        "3. 留给读者的一个开放问题\n"
        "用 markdown 小节，控制在 400 字以内。"
    )


async def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    now = datetime.now(TZ)
    stamp = now.strftime("%Y-%m-%d_%H-%M")
    out_file = OUTPUT_DIR / f"{stamp}.md"

    print("[1/3] 生成今日话题…", file=sys.stderr)
    topic = await generate_topic()
    print(f"      话题：{topic}", file=sys.stderr)

    lines: list[str] = [
        f"# {now.strftime('%Y-%m-%d %H:%M')} 讨论室",
        "",
        "## 话题",
        "",
        topic,
        "",
        "## 讨论",
        "",
    ]
    transcript = ""

    for r in range(1, ROUNDS + 1):
        lines.append(f"### 第 {r} 轮")
        lines.append("")
        for agent in AGENTS:
            print(f"[2/3] 第 {r} 轮 - {agent['name']} 发言中…", file=sys.stderr)
            speech = await agent_speak(agent, topic, transcript, r)
            entry = f"**{agent['name']}**：{speech}"
            lines.append(entry)
            lines.append("")
            transcript += entry + "\n\n"

    print("[3/3] 生成总结…", file=sys.stderr)
    summary = await summarize(topic, transcript)
    lines.append("## 总结")
    lines.append("")
    lines.append(summary)
    lines.append("")

    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n已保存：{out_file}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
