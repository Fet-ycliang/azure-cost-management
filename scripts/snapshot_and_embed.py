#!/usr/bin/env python3
"""對指定 subscription 列表執行：
  1. az resource list → Lakebase tag_snapshots
  2. Databricks AI Gateway → tag_embeddings

用法：
    python scripts/snapshot_and_embed.py [--date YYYY-MM-DD] [--batch-size 50] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SUBSCRIPTIONS = [
    {"id": "23adb6f9-dc6a-40ed-aad6-c549b9bbe4c0", "name": "IDTT-AIVerse_Prod"},
    {"id": "ae0cdff2-430d-4d9c-8b1f-56f7f7163261", "name": "IDTT-Customer Data Platform"},
    {"id": "1d077479-3fc2-4f1f-82b4-0a5789393fd2", "name": "IDTT-AIVerse_Dev"},
]

EXCLUDE_TYPES = {
    "microsoft.network/networkinterfaces",
    "microsoft.network/privateendpoints",
    "microsoft.network/privatednszones",
    "microsoft.network/privatednszones/virtualnetworklinks",
    "microsoft.automation/automationaccounts/runbooks",
    "microsoft.cognitiveservices/accounts/projects",
    "microsoft.powerplatform/enterprisepolicies",  # 不支援 ARM tag 寫入
}

AZ = "az.cmd" if sys.platform == "win32" else "az"


def list_resources(subscription_id: str, resource_group: str | None = None) -> list[dict]:
    """透過 az resource list 取得訂閱內所有資源（含 tags）。"""
    cmd = [AZ, "resource", "list", "--subscription", subscription_id]
    if resource_group:
        cmd += ["--resource-group", resource_group]
    logger.info(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"  az 失敗: {result.stderr.strip()}")
        return []
    raw: list[dict] = json.loads(result.stdout)
    filtered = [
        r for r in raw
        if r.get("type", "").lower() not in EXCLUDE_TYPES
    ]
    logger.info(f"  取得 {len(raw)} 筆，排除 {len(raw) - len(filtered)} 筆網路子資源，剩 {len(filtered)} 筆")
    return filtered


async def process_subscription(
    sub: dict,
    snapshot_date: str,
    batch_size: int,
    dry_run: bool,
    lakebase_client,
    embedding_client,
    resource_group: str | None = None,
) -> dict:
    name, sid = sub["name"], sub["id"]
    rg_label = f" (rg={resource_group})" if resource_group else ""
    logger.info(f"[{name}]{rg_label} 開始處理")

    resources = await asyncio.to_thread(list_resources, sid, resource_group)
    if not resources:
        return {"subscription": name, "resources": 0, "snapshots": 0, "embeddings": 0}

    # 補上 subscriptionId（az resource list 的欄位名）
    for r in resources:
        if "subscriptionId" not in r:
            r["subscriptionId"] = sid

    snap_count = 0
    emb_count = 0

    if not dry_run:
        # 1. 寫入 tag_snapshots
        snap_count = await lakebase_client.upsert_tag_snapshots(resources, snapshot_date)
        logger.info(f"[{name}] tag_snapshots 寫入 {snap_count} 筆")

        # 2. 批次生成 embedding
        for i in range(0, len(resources), batch_size):
            batch = resources[i:i + batch_size]
            written = await lakebase_client.upsert_tag_embeddings(
                batch,
                snapshot_date,
                embedding_client.get_embeddings_batch,
            )
            emb_count += written
            logger.info(f"[{name}] embeddings {i + len(batch)}/{len(resources)}")
    else:
        snap_count = len(resources)
        emb_count = len(resources)
        logger.info(f"[{name}] dry-run，實際不寫入")

    return {
        "subscription": name,
        "subscription_id": sid,
        "resources": len(resources),
        "snapshots": snap_count,
        "embeddings": emb_count,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()), help="快照日期 YYYY-MM-DD")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--subscription", default=None, help="只處理指定 subscription ID（忽略 SUBSCRIPTIONS 列表）")
    parser.add_argument("--rg", default=None, help="只處理指定 resource group（需搭配 --subscription）")
    args = parser.parse_args()

    logger.info(f"快照日期：{args.date}，batch-size：{args.batch_size}，dry-run：{args.dry_run}")

    import os
    os.chdir("D:/azure_code/azure-cost-management")
    sys.path.insert(0, "src")

    from azure_cost_mcp.config import get_settings
    from azure_cost_mcp.lakebase import LakebaseClient
    from azure_cost_mcp.embedding import DatabricksEmbeddingClient

    settings = get_settings()
    lakebase_client = LakebaseClient(settings)
    embedding_client = DatabricksEmbeddingClient(settings)

    if not embedding_client.is_configured():
        logger.error("Embedding 未設定（DATABRICKS_EMBEDDING_URL / DATABRICKS_TOKEN）")
        return 1

    if not lakebase_client.is_configured():
        logger.error("Lakebase 未設定（LAKEBASE_ENABLED=false 或缺連線設定）")
        return 1

    if not args.dry_run:
        logger.info("初始化 Lakebase 連線...")
        await lakebase_client.init()
        logger.info("Lakebase 連線就緒")

    if args.subscription:
        subs_to_process = [{"id": args.subscription, "name": args.subscription}]
    else:
        subs_to_process = SUBSCRIPTIONS

    results = []
    for sub in subs_to_process:
        result = await process_subscription(
            sub, args.date, args.batch_size, args.dry_run,
            lakebase_client, embedding_client,
            resource_group=args.rg,
        )
        results.append(result)

    if not args.dry_run:
        await lakebase_client.close()

    print("\n=== 執行結果 ===")
    total_res = total_snap = total_emb = 0
    for r in results:
        print(f"  {r['subscription']}: {r['resources']} 資源，{r['snapshots']} snapshots，{r['embeddings']} embeddings")
        total_res += r["resources"]
        total_snap += r["snapshots"]
        total_emb += r["embeddings"]
    print(f"  合計: {total_res} 資源，{total_snap} snapshots，{total_emb} embeddings")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
