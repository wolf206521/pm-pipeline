# Claude Code 接入(pm-pipeline)

## 安装

```bash
python3 install.py --target ~/.claude/skills
# 或直接运行 install.py,会自动探测 ~/.claude/skills 并安装
```

安装后 skill 位于 `~/.claude/skills/pm-pipeline/`,Claude Code 新会话即可通过 Skill 工具调用。

## 工具映射

| pm-pipeline 概念 | Claude Code 对应 |
|---|---|
| `SKILL.md` 启动必读 | Skill 加载后的正文指令 |
| `references/*.md` | 用 Read 工具按需读取 skill 目录下文件 |
| `templates/*.md` | 用 Read 读取后用 Write 落到工程目录并替换占位符 |
| `scripts/*.py` | 用 Bash 工具执行 `python3 <路径>` |
| 开工仪式(读 AGENTS/MEMORY/state) | 每次会话开头用 Read 依次读取 |

## 自检脚本探测

`check_all.py` 自动探测 `~/.claude/skills` 下的 `laowang-prd/scripts/check_prd.py` 与
`laowang-diagram/scripts/check_mermaid.py`,无需额外配置。
