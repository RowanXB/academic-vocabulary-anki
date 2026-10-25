# 安装、使用与故障排除

要求：macOS、Python 3.9+、本地 Anki 和 AnkiConnect。运行脚本只依赖 Python 标准库。macOS 不一定预装 Python；本次机器已检测到 Python 3.13.7。

仓库与 Skill 默认位置：`~/.agents/skills/academic-vocabulary-anki/`。`SKILL.md`、scripts、references 等直接位于仓库根目录，完整 Git 历史一并保留。`config.json` 和运行数据放在项目根目录；换电脑时同时备份整个项目目录，尤其是 pending、history 和 config。

Codex 原生本地安装位置：`~/.codex/skills/academic-vocabulary-anki/`。本次保留指向上述仓库根目录的符号链接，避免维护两份代码。`~/.agents/skills/academic-vocabulary-anki/SKILL.md` 也是可直接调用的标准 Skill 入口。新开 Codex 对话加载新技能；如未出现，重启 Codex。也可显式提供 SKILL.md 路径。此安装不等于 ChatGPT Cloud 已安装或可以访问本机。

在另一台 Mac 上，将文件包解压后放到同样的项目目录，再安装链接（如目标已存在，先人工检查，不覆盖）：

```sh
mkdir -p ~/.codex/skills
ln -s ~/.agents/skills/academic-vocabulary-anki ~/.codex/skills/academic-vocabulary-anki
```

首次在词汇专用对话发送：`使用 $academic-vocabulary-anki，把这个对话作为词汇收集对话。之后我发来的词汇请自动保存到 Anki。` 之后发送词或截图即可。自动发现是模型行为，无法保证每次都触发；显式启用一次并使用专门对话最稳妥。本项目没有后台常驻程序，打开 Anki 本身不会触发补同步；下次收词或执行同步时会重试。

首次初始化（已在本机完成时不必重跑）：

```sh
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/sync.py --init
```

初始化会绑定当前 Anki 配置档，创建缺少的目标卡组/Note Type，检查字段和模板。已有不兼容的同名结构会停止，绝不覆盖。更换配置档需要用户主动检查并修改项目 config 中的 expected_profile；不要在同一队列中混用配置档。

如果你自行清空当前配置档：先保留本地项目；清空完成后运行 `sync.py --init` 重建目标结构。history 不会自动重导入，只有 pending 会在下一次同步处理。新建不同名称的配置档时，先确认队列内容是否属于新配置档，再将 config.json 的 expected_profile 改为该配置档准确名称并初始化。不要只因接口显示不同配置档就自动改绑定。清空 Anki 与清空本地词汇历史是两个独立操作。

常用命令：

```sh
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/sync.py --status
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/sync.py
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/lookup.py attenuate
python3 ~/.agents/skills/academic-vocabulary-anki/scripts/intake.py records.json
python3 -m unittest discover -s ~/.agents/skills/academic-vocabulary-anki/tests -v
```

模型生成结构化数据；脚本不包含 AI API，也不接受裸词并自行生成定义。日常由 Skill 完成这一层。默认数据目录从脚本实际位置推导，不再依赖 Documents 路径。`--root PATH` 用于隔离测试数据或显式指定其他数据目录，不更改 Anki 目标名称或 localhost 地址。

若 AnkiConnect 未安装，在 Anki → Tools → Add-ons → Get Add-ons 输入官方编号 `2055492159`，重启 Anki。本次已存在该插件，未重装。保持绑定地址 `127.0.0.1`、端口 `8765`；无需 CORS 通配符、无需关闭安全设置。若插件已启用 API key，使用环境变量 `ANKICONNECT_API_KEY` 传给脚本；不要把密钥写进笔记、Skill 或聊天。

排障：

- `pending`：内容仍在 data/pending.jsonl。打开或唤醒 Anki，完成尚未结束的对话框，再运行同步。macOS 后台应用休眠也可能导致暂时超时；先唤醒再试，不需要自动修改系统设置。
- `failed`：查看 JSON 错误。若此前已打印 saved_pending，缓存仍已保存；否则不要假定已保存。损坏的 JSONL 会停止且原文件保留，不自动丢弃坏行。
- 同词义重复：先 lookup，沿用 sense。脚本只保证稳定 Key 的幂等性，词义比较由 AI 完成；不能通过重命名 sense 来绕过去重。
- 已有内容：只填完全空的兼容字段；人工文字、复习记录、卡片启用标记、现有 CSS 不覆盖。替换旧语境和主动增加卡片方向是另一个明确编辑动作。同步时不要同时在 Anki 编辑同一笔记或切换配置档，AnkiConnect 没有跨请求的原子条件更新。
- 相同 Key 的卡片已移到别的卡组：同步停止，待人工确认；不会搬回或修改其他卡组。
- 字段/模板不一致：停止同步，人工核对；不自动覆盖用户模板。CSS 可以自行调整，不影响脚本检查。
- 标签 context_user/context_generated 描述 Anki 当前语境；重复输入的新原句保存在 history，而不冒充 Anki 已替换语境。
- Anki 原生标签不区分大小写，可能复用已有 `Statistics` 等拼写；脚本按此规则比较，不全库重命名标签。
- IPA 留空是有意的未核实状态。TTS 使用设备内置 en_US 语音：桌面可在系统语音设置安装美式声音并重启 Anki。模板不固定某个 Apple 声音，便于移动端使用。
- iOS/Android：通过你已有的 AnkiWeb 同步同步卡组，在设备上配置 en_US TTS 引擎/声音。脚本只导入本机，不自动执行 AnkiWeb 全库同步。实际移动端显示和播放仍需各设备检查。

data/pending.jsonl 首次收词时创建；data/history.jsonl 只在回读确认成功后记录凭据和完整词汇数据。写入使用同目录临时文件、fsync、macOS F_FULLFSYNC、原子替换和进程锁。若在成功写入 Anki 后中断，下一次通过 Key 找回原笔记，不重新创建。历史记录写入成功后才删除待同步条目。目录私有，数据文件权限 0600；不创建每天一个文件、不使用数据库、不读取 Anki 内部数据库。

测试默认使用临时目录和模拟 API，不运行任何 HTTP 服务器，不触碰真实 Anki。真实验证另行使用目标卡组中的有效学习示例；不会向其他卡组写入或重置复习。
