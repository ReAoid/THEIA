"""
探索新版 CPI API 的 cid 和 indicatorIds

用法：
  cd server
  python tests/explore_cpi_api.py
"""

import json
import logging
import time
from datetime import datetime

import requests

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://data.stats.gov.cn/dg/website/publicrelease/web/external/stream/esData"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.stats.gov.cn/easyquery.htm?cn=A01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
ROOT_ID = "fc982599aa684be7969d7b90b1bd0e84"
DEFAULT_DA = [{"text": "全国", "value": "000000000000"}]


def do_request(cid: str, indicator_ids: list[str], dts: list[str]) -> dict:
    """发送 esData 请求并返回 JSON 响应。"""
    payload = {
        "cid": cid,
        "daCatalogId": "",
        "das": DEFAULT_DA,
        "dts": dts,
        "indicatorIds": indicator_ids,
        "rootId": ROOT_ID,
        "showType": "1",
    }
    logger.debug(f"请求 payload: {json.dumps(payload, ensure_ascii=False)}")

    session = requests.Session()
    session.headers.update(HEADERS)
    session.get("https://data.stats.gov.cn", timeout=15, verify=False)

    resp = session.post(BASE_URL, json=payload, timeout=30, verify=False)
    resp.raise_for_status()
    return resp.json()


def explore_cid(label: str, cid: str, indicator_ids: list[str], dts_list: list[str]):
    """
    探索一个 cid + indicatorIds 组合。

    先查最近一个月，提取 UUID → 指标名映射。
    再逐步扩大 dts 范围，看能查到多早的数据。
    """
    print(f"\n{'='*70}")
    print(f"探索: {label}")
    print(f"  cid: {cid}")
    print(f"  indicatorIds 数量: {len(indicator_ids)}")
    print(f"{'='*70}")

    # ── 第一步：查最近一个月，提取指标映射 ──
    print(f"\n▶ 第一步：查最近数据，解析指标名")
    now = datetime.now()
    recent_dts = [f"{now.year}{now.month:02d}MM"]
    try:
        raw = do_request(cid, indicator_ids, recent_dts)
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return

    if not raw.get("success"):
        print(f"  ❌ API 返回异常: {raw.get('message')}")
        return

    # 提取 UUID → 名称映射
    uuid_to_name = {}
    for period in raw.get("data", []):
        for val in period.get("values", []):
            uuid = val.get("_id", "")
            name = val.get("i_showname", val.get("_id", ""))
            du = val.get("du_name", "")
            if uuid and name:
                uuid_to_name[uuid] = {"name": name, "unit": du}

    print(f"  解析到 {len(uuid_to_name)} 个指标:")
    for uuid, info in uuid_to_name.items():
        print(f"    {uuid[:8]}... → {info['name']} ({info['unit']})")

    # ── 第二步：试不同时间范围，查历史深度 ──
    print(f"\n▶ 第二步：探测历史数据深度")
    test_ranges = [
        ("最近1年", f"{now.year-1}{now.month:02d}MM-{now.year}{now.month:02d}MM"),
        ("最近3年", f"{now.year-3}{now.month:02d}MM-{now.year}{now.month:02d}MM"),
        ("最近5年", f"{now.year-5}{now.month:02d}MM-{now.year}{now.month:02d}MM"),
        ("最近10年", f"{now.year-10}{now.month:02d}MM-{now.year}{now.month:02d}MM"),
    ]

    for range_label, dts_range in test_ranges:
        try:
            raw = do_request(cid, indicator_ids, [dts_range])
            if not raw.get("success"):
                print(f"  {range_label}: API 异常")
                continue

            data_list = raw.get("data", [])
            if not data_list:
                print(f"  {range_label}: 空数据")
                continue

            # 从返回的月份算实际日期范围
            codes = [p.get("code", "") for p in data_list if p.get("code")]
            if codes:
                dates = sorted(codes)
                print(f"  {range_label}: {dates[0]} ~ {dates[-1]} ({len(codes)} 个月, {sum(len(p.get('values',[]))) for p in data_list} 条)")
                # 简化
                total = sum(len(p.get("values", [])) for p in data_list)
                print(f"          共 {total} 条数据点")
            else:
                print(f"  {range_label}: 无有效月份代码")
        except Exception as e:
            print(f"  {range_label}: ❌ {e}")

    return uuid_to_name


# ═══════════════════════════════════════════════════════════
#  探索：从用户提供的三个请求出发
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 请求 1 & 2: cid = 809d2522b0fe4be89142650341b19083
    # 这里需要完整的 indicatorIds，用户只展示了前两个
    # 请从浏览器开发者工具 Network 面板复制完整列表粘贴到下面
    NEW_CID_1 = "809d2522b0fe4be89142650341b19083"
    NEW_IDS_1 = [
        # TODO: 替换为完整列表
        "4ae9047687934a6390984c21d6ddab96",
        "fce9ac527a74442ea0031eb6b37f52ad",
    ]

    # 请求 3: cid = 9d4eec43537742a7ab5d63db97fa2f51
    NEW_CID_2 = "9d4eec43537742a7ab5d63db97fa2f51"
    NEW_IDS_2 = [
        # TODO: 替换为完整列表
        "e5c318ffdbbc4d38898e52b52267eb25",
        "00f5d26484104d8b8cced5f1658890aa",
    ]

    print("=" * 70)
    print("CPI API 探索工具")
    print("=" * 70)
    print()
    print("请先打开浏览器，访问 data.stats.gov.cn")
    print("按 F12 → Network 面板 → 筛选 esData 请求")
    print("找到 cid=809d2522b0fe4be89142650341b19083 的请求")
    print("复制完整的 indicatorIds 数组粘贴到本脚本中")
    print()

    # 先用当前代码中的旧 CID 做对比
    OLD_CID = "5c7452825c7c4dcba391db5ca7f335c5"
    OLD_IDS = [
        "53180dfb9c14411ba4b762307c85920c",
        "42c2d9b5d1b749c4b68c2cbd2e3d4a42",
    ]

    explore_cid("旧 CID (当前代码)", OLD_CID, OLD_IDS,
                [f"{datetime.now().year-1}{datetime.now().month:02d}MM-"
                 f"{datetime.now().year}{datetime.now().month:02d}MM"])
