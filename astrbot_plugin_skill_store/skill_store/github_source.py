"""
真实的 SKILL 源管理器

策略：
1. 扫描本地 data/skills/ 目录（最可靠）
2. 搜索 GitHub 上名称含 "skill" 的 astrbot 相关仓库
3. 验证每个候选仓库是否有 SKILL.md
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger

GITHUB_API = "https://api.github.com"
SEARCH_REPOS_URL = f"{GITHUB_API}/search/repositories"
RAW_CONTENT = "https://raw.githubusercontent.com"

CACHE_TTL = 24 * 60 * 60

# 本地 skills 目录
LOCAL_SKILLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..", "..", "skills",
)


class GitHubSkillSource:
    """真实的 SKILL 源"""

    def __init__(self, token: str = "", data_dir: str = ""):
        self.token = token
        self.data_dir = data_dir
        self._session_headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AstrBot-SkillStore/0.1.0",
        }
        if token:
            self._session_headers["Authorization"] = f"Bearer {token}"

        self._cache_file = ""
        if data_dir:
            self._cache_file = os.path.join(data_dir, "skills_cache.json")

    # ==================== 缓存管理 ====================

    def is_cache_fresh(self) -> bool:
        if not self._cache_file or not os.path.exists(self._cache_file):
            return False
        try:
            return (time.time() - os.path.getmtime(self._cache_file)) < CACHE_TTL
        except Exception:
            return False

    def get_cache_age(self) -> int:
        if not self._cache_file or not os.path.exists(self._cache_file):
            return -1
        try:
            return int(time.time() - os.path.getmtime(self._cache_file))
        except Exception:
            return -1

    def _load_cache(self) -> list[dict]:
        if not self._cache_file or not os.path.exists(self._cache_file):
            return []
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"[SkillSource] 读取缓存失败: {e}")
            return []

    def _save_cache(self, skills: list[dict]):
        if not self._cache_file:
            return
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(skills, f, ensure_ascii=False, indent=2)
            logger.info(f"[SkillSource] 缓存已保存: {len(skills)} 个 SKILL")
        except Exception as e:
            logger.error(f"[SkillSource] 保存缓存失败: {e}")

    # ==================== 本地 SKILL 扫描 ====================

    def _scan_local_skills(self) -> list[dict]:
        """扫描本地 data/skills/ 目录"""
        skills = []
        skills_dir = self._find_local_skills_dir()
        if not skills_dir or not os.path.isdir(skills_dir):
            return skills

        for item in sorted(os.listdir(skills_dir)):
            item_path = os.path.join(skills_dir, item)
            if not os.path.isdir(item_path):
                continue
            skill_md = os.path.join(item_path, "SKILL.md")
            if not os.path.exists(skill_md):
                continue

            info = self._parse_skill_md_file(skill_md)
            info["name"] = info.get("name") or item
            info["skill_name"] = item
            info["source"] = "local"
            info["full_name"] = f"local/{item}"
            info["stars"] = 0
            info["owner"] = "local"
            info["description"] = info.get("description") or "(本地 SKILL)"
            # 读取文件内容预览
            try:
                with open(skill_md, "r", encoding="utf-8") as f:
                    info["raw_skill_md_preview"] = f.read()[:500]
            except Exception:
                info["raw_skill_md_preview"] = ""
            skills.append(info)
        return skills

    def _find_local_skills_dir(self) -> str | None:
        """查找本地 skills 目录"""
        candidates = [
            os.path.abspath(LOCAL_SKILLS_DIR),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "skills"),
        ]
        astrbot_root = os.environ.get("ASTRBOT_ROOT", "")
        if astrbot_root:
            candidates.insert(0, os.path.join(astrbot_root, "data", "skills"))
        for path in candidates:
            if os.path.isdir(path):
                return path
        return None

    @staticmethod
    def _parse_skill_md_file(filepath: str) -> dict:
        """解析 SKILL.md 文件"""
        result: dict = {"name": "", "description": "", "version": "?", "author": ""}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return result

        # 提取 YAML front matter
        fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).split("\n"):
                line = line.strip()
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip().lower()
                    val = val.strip().strip("\"'")
                    if key in ("name", "description", "version", "author"):
                        result[key] = val
        # 尝试从第一个 # 标题取 name
        if not result.get("name"):
            m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if m:
                result["name"] = m.group(1).strip()
        # 取第一段非空文本作描述
        if not result.get("description"):
            m = re.search(r"\n\n(.+?)\n\n", content)
            if m:
                desc = re.sub(r"[#*`_]", "", m.group(1)).strip()[:200]
                result["description"] = desc
        result["raw_skill_md_preview"] = content[:500]
        return result

    # ==================== 远端 SKILL（GitHub） ====================

    async def _fetch_json(self, url: str) -> dict | list | None:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=self._session_headers)
                if resp.status_code == 403:
                    logger.warning("[SkillSource] GitHub API 限频")
                    return None
                if resp.status_code == 404:
                    return None
                if resp.status_code != 200:
                    return None
                return resp.json()
            except Exception as e:
                logger.warning(f"[SkillSource] 请求失败: {e}")
                return None

    async def _fetch_text(self, url: str) -> str | None:
        import httpx
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            try:
                resp = await client.get(url, headers=self._session_headers)
                return resp.text if resp.status_code == 200 else None
            except Exception:
                return None

    async def _check_skill_md(self, full_name: str, branch: str = "main") -> dict | None:
        """检查远程仓库是否有 SKILL.md，有则解析（用 HEAD 快速探测）"""
        # 先用 HEAD 快速检查
        import httpx
        raw_base = RAW_CONTENT
        async with httpx.AsyncClient(timeout=5.0) as client:
            for b in [branch, "master"]:
                try:
                    r = await client.head(
                        f"{raw_base}/{full_name}/{b}/SKILL.md",
                        headers={"User-Agent": "AstrBot-SkillStore/0.1.0"},
                        follow_redirects=True,
                    )
                    if r.status_code == 200:
                        branch = b
                        break
                except Exception:
                    continue
            else:
                return None  # 两个分支都没有

        # 有 SKILL.md，用 GET 获取内容
        content = await self._fetch_text(f"{raw_base}/{full_name}/{branch}/SKILL.md")
        if not content:
            return None

        # 解析
        result: dict = {"name": "", "description": "", "version": "?", "author": ""}
        fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).split("\n"):
                line = line.strip()
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip().lower()
                    val = val.strip().strip("\"'")
                    if key in ("name", "description", "version", "author"):
                        result[key] = val
        if not result.get("name"):
            m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if m:
                result["name"] = m.group(1).strip()
        if not result.get("description"):
            m = re.search(r"\n\n(.+?)\n\n", content)
            if m:
                desc = re.sub(r"[#*`_]", "", m.group(1)).strip()[:200]
                result["description"] = desc
        result["raw_skill_md_preview"] = content[:500]
        return result

    async def fetch_skill_detail(self, full_name: str, branch: str = "") -> dict | None:
        """获取单个 SKILL 的详情（SKILL.md + 仓库信息），供分析功能使用"""
        # 先查缓存
        cached = self._load_cache()
        for s in cached:
            if s.get("full_name") == full_name:
                return s
        # 不在缓存里，从 GitHub 获取
        if not branch:
            branch = "main"
        # 先查仓库信息获取默认分支
        repo_url = f"{GITHUB_API}/repos/{full_name}"
        repo_data = await self._fetch_json(repo_url)
        if repo_data and isinstance(repo_data, dict):
            branch = repo_data.get("default_branch", branch)
        # 获取 SKILL.md
        skill_info = await self._check_skill_md(full_name, branch)
        if not skill_info:
            return None
        skill_info["full_name"] = full_name
        skill_info["stars"] = (repo_data or {}).get("stargazers_count", 0) if repo_data else 0
        skill_info["owner"] = (repo_data or {}).get("owner", {}).get("login", "") if repo_data else ""
        return skill_info

    async def _search_github_skills(self) -> list[dict]:
        """搜索 GitHub 上所有含 SKILL.md 的仓库（不限生态），按 ⭐ 排列"""
        found = []
        seen = set()

        # 多种搜索策略，覆盖不同生态的 SKILL
        queries = [
            "topic:skill&sort=stars&order=desc&per_page=100",
            "skill+in:name&sort=stars&order=desc&per_page=100",
            "SKILL.md+in:readme&sort=stars&order=desc&per_page=100",
        ]

        # 去重后的仓库列表
        unique_repos = []
        for q in queries:
            url = f"{SEARCH_REPOS_URL}?q={q}"
            data = await self._fetch_json(url)
            if not data or not isinstance(data, dict):
                continue
            for repo in data.get("items", []):
                fn = repo.get("full_name", "")
                if fn not in seen:
                    seen.add(fn)
                    unique_repos.append(repo)

        logger.info(f"[SkillSource] 待检查: {len(unique_repos)} 个仓库")

        # 并发检查 SKILL.md
        sem = asyncio.Semaphore(5)
        async def check(repo):
            async with sem:
                full_name = repo.get("full_name", "")
                branch = repo.get("default_branch", "main")
                skill_info = await self._check_skill_md(full_name, branch)
                if not skill_info:
                    return None
                skill_info["full_name"] = full_name
                skill_info["skill_name"] = repo.get("name", "")
                skill_info["source"] = "github"
                skill_info["stars"] = repo.get("stargazers_count", 0)
                skill_info["owner"] = repo.get("owner", {}).get("login", "")
                skill_info["html_url"] = repo.get("html_url", "")
                skill_info["description"] = skill_info.get("description") or repo.get("description", "") or ""
                skill_info["topics"] = repo.get("topics", [])
                skill_info["default_branch"] = branch
                return skill_info

        tasks = [check(repo) for repo in unique_repos]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r:
                found.append(r)

        # 按 stars 降序
        found.sort(key=lambda s: -(s.get("stars", 0) or 0))
        logger.info(f"[SkillSource] GitHub 搜索完成: {len(found)} 个有效 SKILL")
        return found

    # ==================== 全量刷新缓存 ====================

    async def refresh_cache(self) -> dict:
        """刷新缓存：只保存 GitHub SKILL"""
        logger.info("[SkillSource] 开始刷新 SKILL 缓存...")
        
        # 只保存 GitHub SKILL
        try:
            remote = await asyncio.wait_for(
                self._search_github_skills(),
                timeout=120.0  # 2 分钟超时
            )
            logger.info(f"[SkillSource] GitHub SKILL: {len(remote)} 个")
        except asyncio.TimeoutError:
            logger.error("[SkillSource] GitHub 搜索超时")
            return {"success": False, "count": 0, "message": "GitHub 搜索超时，请稍后重试"}
        except Exception as e:
            logger.error(f"[SkillSource] GitHub 搜索失败: {e}")
            return {"success": False, "count": 0, "message": f"搜索失败: {e}"}

        # 保存（只存 GitHub 的）
        self._save_cache(remote)
        return {
            "success": True,
            "count": len(remote),
            "message": f"从 GitHub 找到 {len(remote)} 个 SKILL，按 ⭐ 排列",
        }

    # ==================== 查询接口 ====================

    def search_github(self, keyword: str = "", page: int = 1, per_page: int = 50) -> dict:
        """只搜索 GitHub 上的 SKILL，按 stars 降序排列"""
        all_skills = self._load_cache()

        # 只筛选 GitHub 来源
        github_skills = [s for s in all_skills if s.get("source") == "github"]

        if keyword:
            kw = keyword.lower()
            github_skills = [
                s for s in github_skills
                if kw in s.get("name", "").lower()
                or kw in s.get("description", "").lower()
                or kw in s.get("skill_name", "").lower()
                or kw in s.get("full_name", "").lower()
            ]

        # 按 stars 降序
        github_skills.sort(key=lambda s: -(s.get("stars", 0) or 0))

        total = len(github_skills)
        start = (page - 1) * per_page
        end = start + per_page

        return {
            "skills": github_skills[start:end],
            "total": total,
            "page": page,
            "cache_age": self.get_cache_age(),
        }
