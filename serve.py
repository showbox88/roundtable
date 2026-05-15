"""讨论室常驻服务：
- Web 页面浏览历史讨论
- APScheduler 每 3 小时自动跑一次 discussion.py
没有 cron 时也能在用户态保持自动化。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")

import markdown
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / "output"
LOG_DIR = ROOT / "logs"
DISCUSSION_PY = ROOT / "discussion.py"
PYTHON_BIN = ROOT / ".venv" / "bin" / "python"
DISCUSSION_INTERVAL_HOURS = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("smart.serve")


async def run_discussion_once() -> None:
    """跑一次 discussion.py，输出追加到 logs/cron.log。
    用 subprocess 是为了和 FastAPI 事件循环解耦——discussion.py 自己有 asyncio.run()。
    """
    LOG_DIR.mkdir(exist_ok=True)
    log.info("starting discussion run")
    started = datetime.now(TZ).isoformat()
    proc = await asyncio.create_subprocess_exec(
        str(PYTHON_BIN),
        str(DISCUSSION_PY),
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    finished = datetime.now(TZ).isoformat()
    log_path = LOG_DIR / "cron.log"
    with log_path.open("ab") as fh:
        fh.write(f"=== {started} -> {finished} exit={proc.returncode} ===\n".encode())
        fh.write(stdout or b"")
        fh.write(b"\n")
    log.info("discussion run finished exit=%s", proc.returncode)


scheduler = AsyncIOScheduler(timezone=TZ)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ROUNDTABLE_NO_SCHEDULE=1 → 只起 web，不自动开讨论（适合只浏览历史记录）
    if os.environ.get("ROUNDTABLE_NO_SCHEDULE") == "1":
        log.info("scheduler disabled via ROUNDTABLE_NO_SCHEDULE=1; web-only mode")
        yield
        return

    first_run = datetime.now(TZ) + timedelta(hours=DISCUSSION_INTERVAL_HOURS)
    scheduler.add_job(
        run_discussion_once,
        "interval",
        hours=DISCUSSION_INTERVAL_HOURS,
        id="discussion",
        next_run_time=first_run,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    log.info(
        "scheduler started, discussion every %sh, next run at %s",
        DISCUSSION_INTERVAL_HOURS,
        scheduler.get_job("discussion").next_run_time,
    )
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Smart 讨论室", lifespan=lifespan)

CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
       "Microsoft YaHei", "Helvetica Neue", sans-serif;
       max-width: 820px; margin: 1.5em auto; padding: 0 1.2em;
       line-height: 1.75; color: #1a1a1a; }
a { color: #0066cc; text-decoration: none; }
a:hover { text-decoration: underline; }
header { padding-bottom: 0.8em; margin-bottom: 1.4em;
         border-bottom: 1px solid #eee; display: flex;
         justify-content: space-between; align-items: baseline; }
header .next { color: #888; font-size: 0.85em; }
.meta { color: #888; font-size: 0.85em; margin: 0.5em 0 1.5em; }
h1 { font-size: 1.5em; margin: 0.4em 0; }
h2 { font-size: 1.25em; margin-top: 1.8em; padding-bottom: 0.3em;
     border-bottom: 1px solid #f0f0f0; }
h3 { font-size: 1.1em; margin-top: 1.4em; color: #444; }
table { border-collapse: collapse; margin: 1em 0; width: 100%; }
th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
th { background: #f6f6f6; }
blockquote { border-left: 4px solid #ccc; padding: 0.2em 1em;
             color: #555; margin: 1em 0; background: #fafafa; }
strong { color: #c0392b; }
ul.list { list-style: none; padding: 0; }
ul.list li { padding: 0.7em 0; border-bottom: 1px dashed #eee; }
ul.list .when { color: #999; font-size: 0.85em; margin-right: 0.8em; }
ul.list .topic { color: #1a1a1a; }
ul.list a:hover .topic { color: #0066cc; }
"""

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<header>
  <a href="/">讨论室</a>
  <span class="next">{next_run}</span>
</header>
{content}
</body>
</html>
"""


def _list_files() -> list[Path]:
    if not OUTPUT_DIR.exists():
        return []
    return sorted(
        OUTPUT_DIR.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _extract_topic(md_text: str) -> str:
    in_topic = False
    for line in md_text.splitlines():
        if line.strip().startswith("## 话题"):
            in_topic = True
            continue
        if in_topic and line.strip() and not line.startswith("#"):
            return line.strip()
    return "(无话题)"


def _format_stem(stem: str) -> str:
    try:
        return datetime.strptime(stem, "%Y-%m-%d_%H-%M").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return stem


def _next_run_str() -> str:
    job = scheduler.get_job("discussion")
    if job and job.next_run_time:
        return f"下次自动讨论：{job.next_run_time.strftime('%H:%M')}"
    return ""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    files = _list_files()
    if not files:
        body = "<p>还没有讨论记录，第一次讨论正在生成中，刷新几次试试。</p>"
        return PAGE.format(title="讨论室", css=CSS, next_run=_next_run_str(), content=body)
    items = []
    for f in files:
        topic = _extract_topic(f.read_text(encoding="utf-8"))
        when = _format_stem(f.stem)
        items.append(
            f'<li><a href="/d/{f.stem}">'
            f'<span class="when">{when}</span>'
            f'<span class="topic">{topic}</span>'
            f"</a></li>"
        )
    if scheduler.get_job("discussion"):
        meta = f"共 {len(files)} 场讨论 · 每 {DISCUSSION_INTERVAL_HOURS} 小时自动新增一场"
    else:
        meta = f"共 {len(files)} 场讨论 · 自动讨论已关闭"
    body = (
        f"<h1>讨论室</h1>"
        f'<div class="meta">{meta}</div>'
        f'<ul class="list">{"".join(items)}</ul>'
    )
    return PAGE.format(title="讨论室", css=CSS, next_run=_next_run_str(), content=body)


@app.get("/d/{stem}", response_class=HTMLResponse)
def show(stem: str) -> str:
    fpath = OUTPUT_DIR / f"{stem}.md"
    if not fpath.exists():
        raise HTTPException(404, "未找到该讨论")
    html = markdown.markdown(
        fpath.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "nl2br"],
    )
    mtime = datetime.fromtimestamp(fpath.stat().st_mtime, TZ).strftime("%Y-%m-%d %H:%M:%S")
    content = f'<div class="meta">生成时间：{mtime}</div>{html}'
    return PAGE.format(
        title=_format_stem(stem), css=CSS, next_run=_next_run_str(), content=content
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")
