"""
SKILL 商店 WebUI API 路由

注册 AstrBot 管理后台的 Web API，包括：
- 浏览/搜索 GitHub SKILL
- 查看 SKILL 详情
- 一键安装/卸载
- 已安装 SKILL 管理
- 主页面 HTML 服务
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.star import Context

try:
    from quart import jsonify as quart_jsonify
except ImportError:
    quart_jsonify = None

PLUGIN_NAME = "astrbot_plugin_skill_store"


class SkillStoreWebAPI:
    """SKILL 商店 WebUI API"""

    def __init__(self, context: Context, plugin: Any, prefix: str = ""):
        self.context = context
        self.plugin = plugin
        self.prefix = prefix

    def register_routes(self):
        """注册所有路由：页面 + API"""
        if quart_jsonify is None:
            logger.warning("[SkillStoreWeb] Quart 不可用，跳过 WebUI 注册")
            return

        routes = [
            # API
            ("/api/search", self.api_search, ["GET"], "Search Skills (from cache)"),
            ("/api/search/<keyword>/<page>", self.api_search_with_params, ["GET"], "Search Skills with path params"),
            ("/api/detail", self.api_detail, ["GET"], "Skill Detail"),
            ("/api/detail/<full_name>", self.api_detail_with_name, ["GET"], "Skill Detail with path param"),
            ("/api/installed", self.api_installed, ["GET"], "Installed Skills"),
            ("/api/install", self.api_install, ["POST"], "Install Skill"),
            ("/api/uninstall", self.api_uninstall, ["POST"], "Uninstall Skill"),
            ("/api/toggle", self.api_toggle, ["POST"], "Toggle Skill"),
            ("/api/cache/status", self.api_cache_status, ["GET"], "Cache status"),
            ("/api/cache/refresh", self.api_cache_refresh, ["POST"], "Refresh cache"),
            ("/api/log", self.api_log, ["POST"], "Frontend log collector"),
            ("/api/debug", self.api_debug, ["POST"], "Debug: echo body"),
            ("/api/analyze", self.api_analyze, ["POST"], "Analyze skill with LLM"),
            ("/api/smart_search", self.api_smart_search, ["POST"], "LLM-powered skill search"),
        ]

        for suffix, handler, methods, desc in routes:
            path = f"{self.prefix}{suffix}"
            self.context.register_web_api(
                path,
                self._wrap_handler(handler),
                methods,
                desc,
            )

        logger.info(f"[SkillStoreWeb] 已注册 {len(routes)} 个路由 ({self.prefix})")

    # ==================== 页面服务 ====================

    async def _serve_html(self):
        html_path = self._pages_dir / "index.html"
        if not html_path.exists():
            return "<h1>404</h1>", 404
        content = html_path.read_text(encoding="utf-8")
        return content, 200, {"Content-Type": "text/html; charset=utf-8"}

    async def _serve_js(self):
        js_path = self._pages_dir / "app.js"
        if not js_path.exists():
            return "", 404
        content = js_path.read_text(encoding="utf-8")
        return content, 200, {"Content-Type": "application/javascript; charset=utf-8"}

    async def _serve_css(self):
        css_path = self._pages_dir / "style.css"
        if not css_path.exists():
            return "", 404
        content = css_path.read_text(encoding="utf-8")
        return content, 200, {"Content-Type": "text/css; charset=utf-8"}

    @staticmethod
    def _wrap_handler(handler):
        """包装 handler，捕获异常返回 JSON"""
        async def wrapped(*args, **kwargs):
            try:
                return await handler(*args, **kwargs)
            except Exception as exc:
                logger.exception("[SkillStoreWeb] 请求异常")
                return quart_jsonify({"ok": False, "error": str(exc)}), 500
        wrapped.__name__ = handler.__name__
        return wrapped

    # ==================== API 路由 ====================

    async def api_search(self, keyword="", page="1"):
        """只搜索 GitHub 上的 SKILL，按 stars 排列"""
        page = int(page) if str(page).isdigit() else 1

        source = self.plugin.github_source
        result = source.search_github(keyword=keyword, page=page)
        return quart_jsonify({
            "ok": True,
            "skills": result["skills"],
            "total": result["total"],
            "page": result["page"],
            "cache_age": result["cache_age"],
        })

    async def api_search_with_params(self, keyword="", page="1"):
        return await self.api_search(keyword, page)

    async def api_detail(self, full_name=""):
        """获取 SKILL 详情"""
        if not full_name:
            return quart_jsonify({"ok": False, "error": "缺少 full_name"})

        source = self.plugin.github_source
        detail = await source.fetch_skill_detail(full_name)
        if not detail:
            detail = {"name": full_name, "description": "未找到详情", "raw_skill_md_preview": ""}
        return quart_jsonify({"ok": True, "detail": detail})

    async def api_detail_with_name(self, full_name=""):
        return await self.api_detail(full_name)

    async def api_installed(self):
        """获取已安装 SKILL 列表"""
        mgr = self.plugin.skill_manager
        installed = mgr.list_installed()
        return quart_jsonify({"ok": True, "installed": installed})

    async def api_install(self):
        """安装 SKILL"""
        data = await self._get_json_body()
        if not data:
            return quart_jsonify({"ok": False, "error": "无效请求", "success": False})
        mgr = self.plugin.skill_manager
        result = await mgr.install_skill(
            full_name=data.get("full_name", ""),
            skill_name=data.get("skill_name", ""),
            branch=data.get("branch", "main"),
            zip_url=data.get("zip_url", ""),
        )
        return quart_jsonify({"ok": result["success"], **result})

    async def _get_json_body(self):
        """获取请求 JSON body"""
        # 直接通过 Quart request 读取
        try:
            from quart import request
            return await request.get_json()
        except Exception:
            pass
        # fallback: Starlette request from context
        try:
            from starlette.requests import Request
            # 通过 context vars
            import astrbot.dashboard.asgi_runtime as rt
            req = rt._request_var.get()
            if req and hasattr(req, 'json'):
                return await req.json()
        except Exception:
            pass
        return None

    async def api_uninstall(self):
        """卸载 SKILL"""
        try:
            from astrbot.api.web import PluginRequest
            req = PluginRequest.current()
            data = await req.json()
        except Exception:
            data = None
        if not data:
            return quart_jsonify({"ok": False, "error": "无效请求", "success": False})
        mgr = self.plugin.skill_manager
        result = await mgr.uninstall_skill(data.get("skill_name", ""))
        return quart_jsonify({"ok": result["success"], **result})

    async def api_toggle(self):
        """启用/停用 SKILL"""
        try:
            from astrbot.api.web import PluginRequest
            req = PluginRequest.current()
            data = await req.json()
        except Exception:
            data = None
        if not data:
            return quart_jsonify({"ok": False, "error": "无效请求", "success": False})
        mgr = self.plugin.skill_manager
        result = await mgr.toggle_skill(data.get("skill_name", ""), data.get("active", True))
        return quart_jsonify({"ok": result["success"], **result})

    async def api_cache_status(self):
        """缓存状态"""
        source = self.plugin.github_source
        return quart_jsonify({
            "ok": True,
            "cache_age": source.get_cache_age(),
            "is_fresh": source.is_cache_fresh(),
            "skills_count": len(source._load_cache()),
            "ttl_hours": 24,
        })

    async def api_smart_search(self):
        """LLM 智能搜索：理解用户自然语言需求，匹配已拉取的 SKILL"""
        data = await self._get_json_body()
        query = (data or {}).get("query", "").strip()
        if not query:
            return quart_jsonify({"ok": False, "error": "no query"})
        try:
            # 获取已缓存的所有 SKILL
            source = self.plugin.github_source
            cached = source.search_github(keyword="", page=1, per_page=9999)
            all_skills = cached.get("skills", [])
            if not all_skills:
                return quart_jsonify({"ok": False, "error": "no skills in cache"})

            # 构建详细的 SKILL 信息文本
            skill_lines = []
            for i, s in enumerate(all_skills):
                name = s.get('name', '') or s.get('skill_name', '')
                desc = s.get('description', '') or ''
                topics = ', '.join(s.get('topics', [])[:5]) if s.get('topics') else ''
                fn = s.get('full_name', '')
                # 取 SKILL.md 前 300 字作为详细用途说明
                md = s.get('raw_skill_md_preview', '')[:300]
                line = f"{i+1}. [{name}]\n   描述: {desc[:200]}\n   标签: {topics}\n   用途: {md[:200]}"
                skill_lines.append(line)
            
            skill_list_text = "\n".join(skill_lines)

            prompt = f"""## 任务
用户需要用自然语言搜索 SKILL。你需要根据用户的需求，从以下 SKILL 列表中找出最匹配的。

## 用户需求
"{query}"

## SKILL 列表（编号. [名称] | 描述 | 标签 | 用途）
{skill_list_text}

## 要求
1. 仔细阅读每个 SKILL 的名称、描述、标签和用途说明
2. 根据用户需求的**语义**进行匹配（不仅仅是关键词）
3. 例如：搜"设计"应匹配设计相关的 SKILL（如 ppt、海报、UI 等），搜"聊天"应匹配对话相关的 SKILL
4. 返回匹配的 SKILL 编号（数字），用逗号分隔
5. 如果不匹配任何 SKILL，只返回 "none"
6. 只返回编号，不要其他文字"""

            provider = None
            pm = getattr(self.context, 'provider_manager', None)
            if pm:
                for p in getattr(pm, 'provider_insts', []):
                    provider = p
                    break
            if not provider:
                return quart_jsonify({"ok": False, "error": "no LLM provider"})

            llm_resp = await provider.text_chat(prompt=prompt)
            result_text = (llm_resp.completion_text or "").strip()
            logger.info(f"[SkillStore] smart_search result: {result_text[:100]}")

            # 解析 LLM 返回的编号
            matched = []
            if result_text.lower() != "none":
                for part in result_text.split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part) - 1
                        if 0 <= idx < len(all_skills):
                            matched.append(all_skills[idx])
            return quart_jsonify({"ok": True, "skills": matched, "total": len(matched)})
        except Exception as e:
            logger.error(f"[SkillStore] smart_search error: {e}")
            return quart_jsonify({"ok": False, "error": str(e)})

    async def api_cache_refresh(self):
        """手动触发缓存刷新"""
        source = self.plugin.github_source
        result = await source.refresh_cache()
        return quart_jsonify({"ok": result["success"], **result})

    async def api_log(self):
        """接收前端日志"""
        data = await self._get_json_body()
        if data:
            lvl = data.get('level', 'info')
            msg = data.get('msg', '')
            extra = data.get('data', '')
            log_fn = logger.info if lvl == 'info' else logger.warning if lvl == 'warn' else logger.error
            log_fn(f"[FE] {msg} | {extra}")
        return quart_jsonify({"ok": True})

    async def api_debug(self):
        """调试：打印收到的请求体"""
        import traceback
        try:
            data = await self._get_json_body()
            logger.info(f"[SkillStore] DEBUG body={data}")
            return quart_jsonify({"ok": True, "received": data})
        except Exception as e:
            logger.error(f"[SkillStore] DEBUG error: {e}\n{traceback.format_exc()}")
            return quart_jsonify({"ok": False, "error": str(e)})

    async def api_analyze(self):
        """用 LLM 分析 SKILL 的用途"""
        import traceback
        try:
            data = await self._get_json_body()
            fn = (data or {}).get("full_name", "")
            logger.info(f"[SkillStore] analyze: fn='{fn}', data={data}")
            if not fn:
                return quart_jsonify({"ok": False, "error": "no full_name"})

            source = self.plugin.github_source
            detail = await source.fetch_skill_detail(fn)
            logger.info(f"[SkillStore] detail={'ok' if detail else 'None'}")
            if not detail:
                return quart_jsonify({"ok": False, "error": "cannot fetch skill detail"})

            md_content = detail.get("raw_skill_md_preview", "")
            logger.info(f"[SkillStore] md_content len={len(md_content)}")
            # 用 LLM 分析
            provider = None
            try:
                pm = self.context.provider_manager
                for p in pm.provider_insts:
                    provider = p
                    break
            except Exception as e:
                logger.warning(f"[SkillStore] no provider from manager: {e}")
            if not provider:
                return quart_jsonify({"ok": False, "error": "no LLM provider"})
            llm_resp = await provider.text_chat(
                prompt=f"用中文简洁说明以下 SKILL 的功能和用途（2-3句话）：\n\n{md_content[:2000]}",
            )
            analysis = llm_resp.completion_text or ""
            logger.info(f"[SkillStore] analysis ok: {analysis[:80]}")
            return quart_jsonify({"ok": True, "analysis": analysis.strip()})
        except Exception as e:
            logger.error(f"[SkillStore] 分析失败: {e}\n{traceback.format_exc()}")
            return quart_jsonify({"ok": False, "error": str(e)})
