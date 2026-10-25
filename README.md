# Academic Vocabulary

这是本地 Agent Skill + Python 标准库脚本项目，可在 Codex、Claude Code 等支持 skills 的本地运行环境中使用。主要入口是 `SKILL.md`。

完整的简短安装、使用与排障说明见 [references/setup.md](references/setup.md)。

主要文件：

- `scripts/intake.py`：验证、持久化、自动尝试同步。
- `scripts/sync.py`：初始化、检查、补同步。
- `scripts/lookup.py`：查找已知词义。
- `scripts/common.py`：固定数据结构、持久化和 API 通信。
- `assets/`：两套 Front/Back 和 CSS。
- `tests/`：非破坏性自动化测试。
- `evals/`：语言生成示例和评估用例。
- `config.json`：本机接口与配置档绑定，不含密钥。
- `data/pending.jsonl`：待同步记录，首次收词时创建。
- `data/history.jsonl`：已确认导入的凭据和上下文历史。

没有后台 Agent，也没有持续运行的服务。下一次收词自动补同步；只打开 Anki 不会主动处理队列。

许可证：[MIT](LICENSE)。
