# 通用模型接入(pm-pipeline · GENERIC)

适用于没有 skill 加载器的模型:DeepSeek、豆包、通义、Kimi 网页版、ChatGPT 网页版等。

## 核心用法:SKILL.md 即系统提示

本 skill 的 `SKILL.md` 是**自包含指令**,不依赖任何工具加载器:

1. 打开 `skills/pm-pipeline/SKILL.md`,复制 frontmatter(`---` 之间)以下的全部正文
2. 粘贴为对话的**系统提示 / 项目指令 / 自定义指令**
3. 再把 `references/workflow.md` 与 `references/checklist.md` 全文一并粘贴(或作为知识库/上下文文件上传)

模型即获得完整方法论:五阶段循环、闸门、硬性规则、记忆仪式。

## 工程文件初始化

无文件系统权限的模型(网页版)无法直接建目录,两种方式:

- **让模型输出文件清单**:要求按「工程目录结构」逐个输出文件内容(路径+全文),你本地保存
- **本地跑脚本**:clone 本仓库后,把 `skills/pm-pipeline/templates/` 复制为工程骨架,`scripts/` 复制为工程 `scripts/`,手动执行

## 有代码执行环境的模型(如 DeepSeek 终端 agent)

直接 clone 本仓库,参照 `agents/claude.md` 的工具映射:Read/Write/Bash 对应其文件读写与命令执行能力即可,脚本是纯 Python 3 跨平台,无需改造。

## 续跑关键

无论哪个模型,接续已有工程时只需说:

> 按开工仪式来:先读 AGENTS.md,再读 01-记忆/MEMORY.md,再读当前模块 state.md,告诉我下一步做什么。

模型即可从文件现场重建上下文——这正是本体系的设计目标。
