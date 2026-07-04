"""
SKILL 安装/卸载/本地管理器

负责从 GitHub 下载 SKILL 并安装到 AstrBot，
以及管理已安装的 SKILL。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.core.skills.skill_manager import SkillManager as CoreSkillManager


class SkillStoreManager:
    """SKILL 安装/卸载管理器"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 已安装 SKILL 记录文件
        self.installed_file = self.data_dir / "installed.json"
        self._cache: list[dict] = []
        self._load_cache()

    # ==================== 缓存管理 ====================

    def _load_cache(self):
        """加载已安装 SKILL 缓存"""
        try:
            if self.installed_file.exists():
                with open(self.installed_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
        except Exception as e:
            logger.warning(f"[SkillStore] 加载已安装缓存失败: {e}")
            self._cache = []

    def _save_cache(self):
        """保存已安装 SKILL 缓存"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.installed_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[SkillStore] 保存已安装缓存失败: {e}")

    # ==================== 本地 SKILL 查询 ====================

    def list_installed(self) -> list[dict]:
        """列出已安装的 SKILL"""
        # 先从 AstrBot 核心获取最新状态
        try:
            core_mgr = CoreSkillManager()
            core_skills = core_mgr.list_skills()
            core_names = {s.name for s in core_skills if hasattr(s, "name")}

            # 同步缓存中的激活状态
            for item in self._cache:
                item["active"] = item.get("name", "") in core_names
        except Exception:
            pass
        return self._cache

    def get_installed(self, skill_name: str) -> dict | None:
        """获取指定已安装 SKILL 信息"""
        for item in self._cache:
            if item.get("name") == skill_name or item.get("skill_name") == skill_name:
                return item
        return None

    def is_installed(self, skill_name: str) -> bool:
        """检查 SKILL 是否已安装"""
        return self.get_installed(skill_name) is not None

    # ==================== 安装 SKILL ====================

    async def install_skill(
        self,
        full_name: str,
        skill_name: str,
        branch: str = "main",
        zip_url: str = "",
    ) -> dict:
        """
        从 GitHub 安装 SKILL

        Args:
            full_name: 仓库全名 "user/repo"
            skill_name: SKILL 名称
            branch: 分支
            zip_url: ZIP 下载地址

        Returns:
            安装结果 {"success": bool, "message": str, ...}
        """
        if self.is_installed(skill_name):
            return {"success": False, "message": f"SKILL「{skill_name}」已安装"}

        if not zip_url:
            zip_url = f"https://github.com/{full_name}/archive/refs/heads/{branch}.zip"

        tmp_dir = None
        try:
            # 1. 下载 ZIP
            tmp_dir = tempfile.mkdtemp(prefix="skill_install_")
            zip_path = os.path.join(tmp_dir, "skill.zip")

            import httpx

            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(zip_url)
                if resp.status_code != 200:
                    return {
                        "success": False,
                        "message": f"下载失败 (HTTP {resp.status_code})",
                    }
                with open(zip_path, "wb") as f:
                    f.write(resp.content)

            # 2. 解压 ZIP
            extract_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as zf:
                # 解压后第一层是仓库名目录，需要跳过
                members = zf.namelist()
                # 找到顶层目录前缀
                top_dir = ""
                for m in members:
                    parts = m.split("/")
                    if parts[0]:
                        top_dir = parts[0]
                        break
                for m in members:
                    # 跳过顶层目录
                    rel_path = m[len(top_dir) + 1:] if m.startswith(top_dir + "/") else m
                    if not rel_path:
                        continue
                    target = os.path.join(extract_dir, rel_path)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    if not m.endswith("/"):
                        with zf.open(m) as source, open(target, "wb") as dest:
                            dest.write(source.read())

            # 3. 查找 SKILL.md 确认是有效 SKILL
            skill_md_path = os.path.join(extract_dir, "SKILL.md")
            if not os.path.exists(skill_md_path):
                # 检查子目录
                for root, _dirs, files in os.walk(extract_dir):
                    if "SKILL.md" in files:
                        skill_md_path = os.path.join(root, "SKILL.md")
                        break

            if not os.path.exists(skill_md_path):
                return {
                    "success": False,
                    "message": "无效的 SKILL：未找到 SKILL.md",
                }

            # 4. 安装到 AstrBot SKILL 目录
            skills_dir = self._get_skills_dir()
            target_dir = os.path.join(skills_dir, skill_name)

            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            shutil.copytree(extract_dir, target_dir)

            # 5. 注册到 AstrBot
            result = self._register_skill(skill_name)

            # 6. 记录到缓存
            installed_info = {
                "name": skill_name,
                "full_name": full_name,
                "version": "?",
                "installed_at": __import__("time").time(),
                "active": True,
            }
            self._cache.append(installed_info)
            self._save_cache()

            return {
                "success": True,
                "message": f"SKILL「{skill_name}」安装成功！",
                "detail": installed_info,
            }

        except Exception as e:
            logger.error(f"[SkillStore] 安装失败: {e}", exc_info=True)
            return {"success": False, "message": f"安装失败: {e}"}
        finally:
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)

    def _get_skills_dir(self) -> str:
        """获取 AstrBot 的 skills 目录"""
        # 尝试常见位置
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "skills"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "skills"),
        ]
        astrbot_root = os.environ.get("ASTRBOT_ROOT", "")
        if astrbot_root:
            candidates.insert(0, os.path.join(astrbot_root, "data", "skills"))
            candidates.insert(0, os.path.join(astrbot_root, "skills"))

        for path in candidates:
            resolved = os.path.abspath(path)
            if os.path.isdir(resolved):
                return resolved

        # 如果都不存在，创建一个
        default = os.path.abspath(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data",
                "skills",
            )
        )
        os.makedirs(default, exist_ok=True)
        return default

    def _register_skill(self, skill_name: str) -> bool:
        """向 AstrBot 注册 SKILL"""
        try:
            from astrbot.core.skills.skill_manager import SkillManager
            mgr = SkillManager()
            mgr.load_skill(skill_name)
            logger.info(f"[SkillStore] SKILL「{skill_name}」已加载")
            return True
        except Exception as e:
            logger.warning(f"[SkillStore] 注册加载 SKILL 失败: {e}")
            return False

    # ==================== 卸载 SKILL ====================

    async def uninstall_skill(self, skill_name: str) -> dict:
        """
        卸载 SKILL

        Returns:
            卸载结果
        """
        try:
            # 1. 从 AstrBot 卸载
            from astrbot.core.skills.skill_manager import SkillManager
            mgr = SkillManager()
            mgr.unload_skill(skill_name)

            # 2. 删除文件
            skills_dir = self._get_skills_dir()
            target_dir = os.path.join(skills_dir, skill_name)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)

            # 3. 从缓存移除
            self._cache = [
                item for item in self._cache
                if item.get("name") != skill_name and item.get("skill_name") != skill_name
            ]
            self._save_cache()

            return {"success": True, "message": f"SKILL「{skill_name}」已卸载"}
        except Exception as e:
            logger.error(f"[SkillStore] 卸载失败: {e}", exc_info=True)
            return {"success": False, "message": f"卸载失败: {e}"}

    # ==================== 激活/停用 ====================

    async def toggle_skill(self, skill_name: str, active: bool) -> dict:
        """启用或停用 SKILL"""
        try:
            from astrbot.core.skills.skill_manager import SkillManager
            mgr = SkillManager()

            if active:
                mgr.enable_skill(skill_name)
            else:
                mgr.disable_skill(skill_name)

            # 更新缓存
            for item in self._cache:
                if item.get("name") == skill_name:
                    item["active"] = active
            self._save_cache()

            status = "已启用" if active else "已停用"
            return {"success": True, "message": f"SKILL「{skill_name}」{status}"}
        except Exception as e:
            return {"success": False, "message": f"操作失败: {e}"}
