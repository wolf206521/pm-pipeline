# Cursor 接入(pm-pipeline)

Cursor 没有标准 skills 加载器,用 **Rules + 手动脚本** 方式接入。

## 接入步骤

1. 在工程根目录建 `.cursor/rules/pm-pipeline.mdc`,内容为:

   ```markdown
   ---
   description: 多模块需求工程流水线
   alwaysApply: true
   ---
   本工程遵循 pm-pipeline 体系。每次会话开始:
   1. 读 AGENTS.md
   2. 读 01-记忆/MEMORY.md
   3. 读当前模块 10-模块/*/state.md
   然后按 00-体系/WORKFLOW.md 的五阶段循环推进,硬性规则见 AGENTS.md。
   ```

2. 把 `templates/AGENTS.md` 复制为工程根 `AGENTS.md` 并替换占位符;`references/` 四个文件复制到工程 `00-体系/`(去掉通用模板后缀说明)。

3. 脚本直接终端执行:`python3 scripts/new_module.py M01 客户中心` 等。

## 注意

- Cursor 的 AI 对话不会自动加载 SKILL.md;关键流程已浓缩进 `.mdc` rule,细节引导 AI 读 `00-体系/` 文件。
- 自检脚本(check_prd/check_mermaid)若未安装对应 skill,`check_all.py` 会跳过并提示,不影响主流程。
