# roundtable

3 个不同立场的 AI agent 围绕一个话题轮流发言，最后由中立观察者出一份结构化总结。

## 是什么

- **话题**：每场由 LLM 自动生成一个有思辨价值的题目
- **发言**：「乐观派 / 怀疑派 / 实用派」3 个 agent 各自带人设，共 2 轮共 6 条发言；后发言者要点名回应或反驳前面具体观点，不能各说各话
- **总结**：另起一通 LLM，作为中立观察者输出「各方观点 / 共识与分歧 / 一个开放问题」
- **输出**：每场写一份 `output/YYYY-MM-DD_HH-MM.md`
- **浏览**：自带一个 FastAPI 简易 viewer
- **常驻**：`serve.py` 启动后用 APScheduler 每 3 小时自动新增一场讨论
- **模型**：默认 `sonnet`，走 [`claude-agent-sdk`](https://github.com/anthropics/claude-agent-sdk-python)——用本地 Claude Code 订阅认证，不消耗 Anthropic API key

## 安装

依赖：Python 3.10+ · 已登录的 Claude Code（`~/.claude/` 存在即可）

```bash
git clone https://github.com/showbox88/roundtable-.git
cd roundtable-
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 用法

跑一次讨论：

```bash
.venv/bin/python discussion.py
```

启动常驻服务（web viewer + 每 3 小时自动跑）：

```bash
mkdir -p logs
nohup .venv/bin/python serve.py > logs/serve.log 2>&1 & disown
echo $! > logs/serve.pid
```

打开 http://localhost:8090 浏览历史讨论。

停止：

```bash
kill $(cat logs/serve.pid)
```

## 可调参数

| 文件 | 改什么 |
|---|---|
| `agents.py` | agent 数量、人设、立场 |
| `discussion.py` | `MODEL`（模型）、`ROUNDS`（轮数）、`QUERY_TIMEOUT_S` |
| `serve.py` | `DISCUSSION_INTERVAL_HOURS`（自动间隔）、监听端口 |

## 项目结构

```
.
├── agents.py          agent 人设
├── discussion.py      单次讨论执行
├── serve.py           web viewer + 内嵌定时器
├── run-cron.sh        cron 包装（系统有 cron 时备用）
├── requirements.txt
├── output/            生成的 markdown（gitignore）
└── logs/              进程/任务日志（gitignore）
```
