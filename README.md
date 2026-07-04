# SKILL Store - AstrBot Plugin

一个功能完整的 SKILL 商店插件，支持从 GitHub 浏览、搜索、安装各类 AI Agent SKILL。

## 功能特性

- **浏览 GitHub SKILL** — 自动搜索 GitHub 上所有包含 `SKILL.md` 的仓库，按 ⭐ 排列
- **智能搜索** — 使用 LLM 理解自然语言需求，语义匹配最佳 SKILL
- **一键安装** — 从 GitHub 直接下载并安装到 AstrBot
- **已安装管理** — 查看、启用、停用、卸载已安装的 SKILL
- **本地缓存** — 7 天本地缓存，秒开不等待
- **精美 UI** — 渐变毛玻璃设计，卡片悬浮动效，翻页浏览

## 安装方法

### 方法一：AstrBot 插件市场（推荐）
1. 打开 AstrBot 管理后台 → 插件管理
2. 点击「安装插件」→ 上传本插件 ZIP
3. 重启 AstrBot

### 方法二：手动安装
1. 将 `astrbot_plugin_skill_store` 文件夹复制到 `data/plugins/` 目录
2. 重启 AstrBot 或在管理后台重载插件

## 配置说明

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `github_token` | string | （可选）GitHub Personal Access Token，提高 API 频率限制（从 60次/h 到 5000次/h） |

## 使用方法

### WebUI 方式
1. 打开 AstrBot 管理后台
2. 左侧菜单点击「SKILL Store」
3. 点击「Refresh Cache」从 GitHub 拉取 SKILL 列表
4. 浏览、搜索、安装你需要的 SKILL

### 命令方式
- `/skillstore` — 查看 SKILL 商店状态
- `/skill_refresh` — 手动刷新缓存
- `/skill_cache_status` — 查看缓存状态

## 目录结构

```
astrbot_plugin_skill_store/
├── __init__.py          # 插件入口
├── main.py              # 主逻辑
├── metadata.yaml        # 插件元数据
├── _conf_schema.json    # 配置项定义
├── README.md            # 本文件
├── LICENSE              # 开源协议
├── skill_store/         # 核心模块
│   ├── github_source.py # GitHub 搜索 & 缓存
│   └── skill_manager.py # 安装/卸载/管理
├── webui/               # Web API
│   └── web_api.py       # API 路由
└── pages/
    └── skill-store/     # 前端页面
        ├── index.html
        ├── app.js
        └── style.css
```

## 技术细节

- **SKILL 识别**: 通过搜索 GitHub 上含 `SKILL.md` 文件的仓库
- **搜索策略**: `topic:skill` + `skill in:name` + `SKILL.md in:readme`
- **缓存策略**: 7 天 localStorage + 24h 后端缓存
- **安装流程**: 下载 GitHub ZIP → 提取 SKILL.md → 复制到 `data/skills/` → 注册到 SkillManager

## 协议

MIT License
