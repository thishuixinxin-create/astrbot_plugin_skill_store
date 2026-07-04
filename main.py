"""
AstrBot Skill 商店插件

浏览、搜索、一键安装来自 GitHub 的 AstrBot Skills。
SKILL 源为 GitHub 上标记了 astrbot-skill Topic 的仓库。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .skill_store.github_source import GitHubSkillSource
from .skill_store.skill_manager import SkillStoreManager
from .webui.web_api import SkillStoreWebAPI

# 避免 pages/ 目录被当作 Python 包加载（AstrBot 的 page 发现机制）
try:
    import pages  # type: ignore
except ImportError:
    pass

PLUGIN_NAME = "astrbot_plugin_skill_store"


@register(
    PLUGIN_NAME,
    "灰心心",
    "浏览、搜索、一键安装来自 GitHub 的 AstrBot Skills",
    "0.1.1",
    "https://github.com/your-repo/astrbot_plugin_skill_store",
)
class SkillStorePlugin(Star):
    """Skill 商店插件主类"""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.context = context
        self.config = config if config is not None else {}

        # 数据目录：用于缓存 SKILL 列表和已安装记录
        self.data_dir = Path(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "data",
            )
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # GitHub API Token（可选，提高 API 限频）
        self.github_token = str(self.config.get("github_token", "") if isinstance(self.config, dict) else "").strip()

        # 初始化核心模块
        self.github_source = GitHubSkillSource(
            token=self.github_token,
            data_dir=str(self.data_dir),
        )
        self.skill_manager = SkillStoreManager(data_dir=str(self.data_dir))

        # 注册 WebUI API
        try:
            self.web_api = SkillStoreWebAPI(
                context=self.context,
                plugin=self,
                prefix=f"/{PLUGIN_NAME}",
            )
            self.web_api.register_routes()
            logger.info(f"[{PLUGIN_NAME}] WebUI API 已注册")
        except Exception as e:
            logger.error(f"[{PLUGIN_NAME}] WebUI API 注册失败: {e}")

        # 确保有初始缓存（即使是空的，避免前端报错）
        if not os.path.exists(os.path.join(str(self.data_dir), "skills_cache.json")):
            self.github_source._save_cache([])
            logger.info(f"[{PLUGIN_NAME}] 已创建初始空缓存")

        # 启动后台缓存检查（非阻塞）
        self._bg_task = None
        self._start_background_cache_check()

    # ==================== 后台缓存刷新 ====================

    def _start_background_cache_check(self):
        """启动后台缓存检查，缓存过期则异步更新"""
        async def _check_and_refresh():
            try:
                if not self.github_source.is_cache_fresh():
                    logger.info(
                        f"[{PLUGIN_NAME}] 缓存已过期（或不存在），"
                        "开始后台刷新..."
                    )
                    result = await self.github_source.refresh_cache()
                    logger.info(f"[{PLUGIN_NAME}] 后台刷新结果: {result.get('message')}")
                else:
                    age = self.github_source.get_cache_age()
                    logger.info(
                        f"[{PLUGIN_NAME}] 缓存仍有效（{age//3600}h "
                        f"{(age%3600)//60}m），跳过刷新"
                    )
            except Exception as e:
                logger.warning(f"[{PLUGIN_NAME}] 后台缓存检查异常: {e}")

        # 延迟 5 秒启动，避免阻塞插件加载
        async def _delayed_start():
            await asyncio.sleep(5)
            await _check_and_refresh()

        self._bg_task = asyncio.create_task(_delayed_start())

    # ==================== 命令入口 ====================

    @filter.command("skillstore", alias={"skill-store", "skills"})
    async def skill_store_cmd(self, event: AstrMessageEvent):
        """SKILL 商店命令"""
        cache_age = self.github_source.get_cache_age()
        if cache_age >= 0:
            age_str = f"{cache_age//3600}h{(cache_age%3600)//60}m"
        else:
            age_str = "无缓存"

        yield event.plain_result(
            "📦 **SKILL 商店**\n"
            f"缓存状态：{age_str}\n"
            "请在 AstrBot 管理后台访问 SKILL 商店喵~\n"
        )

    @filter.command("skill_refresh")
    async def skill_refresh_cmd(self, event: AstrMessageEvent):
        """手动触发 SKILL 缓存刷新"""
        yield event.plain_result("🔄 正在刷新 SKILL 缓存（从 GitHub 全量检索）...")
        result = await self.github_source.refresh_cache()
        yield event.plain_result(
            f"{'✅' if result['success'] else '❌'} {result.get('message')}"
        )

    @filter.command("skill_cache_status")
    async def skill_cache_status_cmd(self, event: AstrMessageEvent):
        """查看 SKILL 缓存状态"""
        cache_age = self.github_source.get_cache_age()
        if cache_age < 0:
            yield event.plain_result("📭 缓存不存在，请发送 /skill_refresh 刷新")
            return

        hours = cache_age // 3600
        mins = (cache_age % 3600) // 60
        is_fresh = self.github_source.is_cache_fresh()
        skills = self.github_source._load_cache()

        yield event.plain_result(
            "📊 **SKILL 缓存状态**\n"
            f"• SKILL 数量：{len(skills)} 个\n"
            f"• 缓存时间：{hours}h{mins}m 前\n"
            f"• 状态：{'✅ 有效' if is_fresh else '❌ 已过期'}"
        )

    async def terminate(self):
        """插件卸载时的清理"""
        logger.info(f"[{PLUGIN_NAME}] 插件正在卸载...")
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
