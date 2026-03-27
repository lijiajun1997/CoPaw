#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书通讯录同步脚本
使用获取用户列表 API (contact/v3/users) 同步所有用户到本地缓存

支持两种认证方式：
1. user_access_token: 需要用户授权，可获取完整用户信息（推荐）
2. tenant_access_token: 应用身份，需要开通 contact:contact:readonly_as_app 权限

使用方法：
  # 使用 user_access_token（推荐）
  export FEISHU_USER_ACCESS_TOKEN="u-xxx"
  python sync_feishu_contacts.py

  # 或使用应用凭证
  export FEISHU_APP_ID="cli_xxx"
  export FEISHU_APP_SECRET="xxx"
  python sync_feishu_contacts.py
"""
import json
import logging
import os
from pathlib import Path
from datetime import datetime

import httpx

# 配置
USER_ACCESS_TOKEN = os.getenv("FEISHU_USER_ACCESS_TOKEN", "")
APP_ID = os.getenv("FEISHU_APP_ID", "cli_a904639522ba5ced")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
CACHE_FILE = Path.home() / ".proudai" / "feishu_contacts.json"

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class FeishuContactSyncer:
    """飞书通讯录同步器"""

    def __init__(
        self,
        user_access_token: str = None,
        app_id: str = None,
        app_secret: str = None,
    ):
        self.user_access_token = user_access_token
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenant_access_token = None
        self.contacts_map = {}

    def _get_access_token(self) -> tuple[str | None, str | None]:
        """获取访问令牌，返回 (token, token_type)

        token_type: 'user' 或 'tenant'
        """
        if self.user_access_token:
            return self.user_access_token, "user"

        if self.app_id and self.app_secret:
            url = (
                "https://open.feishu.cn/open-apis/auth/v3/"
                "tenant_access_token/internal"
            )
            try:
                response = httpx.post(
                    url,
                    json={
                        "app_id": self.app_id,
                        "app_secret": self.app_secret,
                    },
                    timeout=30.0,
                )
                data = response.json()
                if data.get("code") == 0:
                    self.tenant_access_token = data.get("tenant_access_token")
                    logger.info("获取 tenant_access_token 成功")
                    return self.tenant_access_token, "tenant"
                else:
                    logger.error(f"获取 token 失败: {data}")
            except Exception as e:
                logger.error(f"获取 token 异常: {e}")

        return None, None

    def _load_cache(self) -> dict:
        """加载缓存"""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"加载缓存: {len(data.get('contacts', {}))} 个联系人")
                    return data
            except Exception as e:
                logger.warning(f"加载缓存失败: {e}")
        return {"contacts": {}, "updated_at": None}

    def _save_cache(self, data: dict) -> bool:
        """保存缓存"""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(
                f"缓存已保存: {len(data.get('contacts', {}))} 个联系人 -> {CACHE_FILE}",
            )
            return True
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
            return False

    def sync_all_users(self, page_size: int = 50) -> dict:
        """同步所有用户"""
        token, token_type = self._get_access_token()
        if not token:
            logger.error("无法获取访问令牌")
            return {}

        logger.info(f"使用 {token_type}_access_token 同步飞书通讯录...")
        self.contacts_map = {}
        page_token = ""
        total_count = 0
        page_num = 0

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        while True:
            page_num += 1
            try:
                url = (
                    "https://open.feishu.cn/open-apis/contact/v3/users"
                    f"?user_id_type=open_id&page_size={page_size}"
                )
                if page_token:
                    url += f"&page_token={page_token}"

                logger.info(f"正在获取第 {page_num} 页...")

                response = httpx.get(url, headers=headers, timeout=30.0)
                data = response.json()

                if data.get("code") != 0:
                    logger.error(
                        f"API 错误: code={data.get('code')}, "
                        f"msg={data.get('msg')}",
                    )
                    break

                users = data.get("data", {}).get("items", [])

                if not users:
                    logger.info("没有更多用户数据")
                    break

                for user in users:
                    open_id = user.get("open_id")
                    name = (
                        user.get("name")
                        or user.get("en_name")
                        or user.get("nickname")
                    )

                    if open_id and name:
                        self.contacts_map[open_id] = name
                        total_count += 1
                        logger.info(f"  {name} ({open_id[:20]}...)")

                has_more = data.get("data", {}).get("has_more", False)
                if not has_more:
                    logger.info(f"已获取所有用户，共 {total_count} 个")
                    break

                page_token = data.get("data", {}).get("page_token", "")
                if not page_token:
                    break

            except Exception as e:
                logger.error(f"同步用户列表失败: {e}")
                break

        # 保存缓存
        cache_data = {
            "contacts": self.contacts_map,
            "total_count": total_count,
            "updated_at": datetime.now().isoformat(),
            "token_type": token_type,
        }

        self._save_cache(cache_data)
        return cache_data


def main():
    """主函数"""
    syncer = FeishuContactSyncer(
        user_access_token=USER_ACCESS_TOKEN,
        app_id=APP_ID,
        app_secret=APP_SECRET,
    )

    result = syncer.sync_all_users()

    print("\n✅ 同步完成！")
    print(f"总用户数: {result.get('total_count', 0)}")
    print(f"缓存文件: {CACHE_FILE}")
    print(f"更新时间: {result.get('updated_at')}")


if __name__ == "__main__":
    main()
