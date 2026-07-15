"""
=============================================================================
一次性脚本：从历史日志中解析 LLM 调用记录，写入 stats.json
=============================================================================
解析 data/logs/ 目录下的日志文件，提取 LLM 调用记录（provider/model/tokens/duration）。
运行方式：python utils/migrate_logs.py
=============================================================================
"""

import re
import sys
import io
from datetime import datetime
from pathlib import Path

# 修复 Windows GBK 输出问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import LOG_DIR
from utils.stats import STATS_FILE, _read_json, _write_json


def parse_log_line(line: str) -> dict | None:
    """
    解析一行 LLM 调用日志，提取结构化字段。

    日志格式示例：
    [2026-07-14 18:40:52] [INFO] [resume_optimizer] LLM调用 | ✓ provider=deepseek model=deepseek-chat prompt_len=2561 tokens=2832 duration=15172ms
    """
    if "LLM调用" not in line:
        return None

    result = {}

    # 提取时间戳
    ts_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
    if ts_match:
        result["timestamp"] = ts_match.group(1)

    # 提取成功/失败
    if "✓" in line:
        result["success"] = True
    elif "✗" in line:
        result["success"] = False
    else:
        result["success"] = True  # 默认成功

    # 提取 provider
    prov_match = re.search(r'provider=(\S+)', line)
    if prov_match:
        result["provider"] = prov_match.group(1)

    # 提取 model
    model_match = re.search(r'model=(\S+)', line)
    if model_match:
        result["model"] = model_match.group(1)

    # 提取 tokens
    token_match = re.search(r'tokens=(\d+)', line)
    if token_match:
        result["tokens"] = int(token_match.group(1))

    # 提取 duration
    dur_match = re.search(r'duration=(\d+)ms', line)
    if dur_match:
        result["duration_ms"] = int(dur_match.group(1))

    # 提取 error
    err_match = re.search(r'error=(.+?)(?:\n|$)', line)
    if err_match:
        result["error"] = err_match.group(1).strip()
        result["success"] = False

    return result


def main():
    """扫描所有日志文件，解析 LLM 调用记录并写入 stats.json"""
    log_files = sorted(LOG_DIR.glob("resume_optimizer_*.log"))
    if not log_files:
        print("❌ 未找到日志文件。")
        return

    print(f"📂 找到 {len(log_files)} 个日志文件：")
    for f in log_files:
        print(f"  - {f.name}")

    all_calls = []
    app_starts = 0

    for log_file in log_files:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                # 统计启动次数
                if "简历优化助手启动" in line:
                    app_starts += 1

                # 解析 LLM 调用
                call = parse_log_line(line)
                if call:
                    all_calls.append(call)

    print(f"\n📊 解析结果：")
    print(f"  - App 启动次数：{app_starts}")
    print(f"  - LLM 调用次数：{len(all_calls)}")

    if all_calls:
        # 按 provider 统计
        providers = {}
        total_tokens = 0
        total_duration = 0
        failed = 0
        for c in all_calls:
            p = c.get("provider", "unknown")
            providers[p] = providers.get(p, 0) + 1
            total_tokens += c.get("tokens", 0)
            total_duration += c.get("duration_ms", 0)
            if not c.get("success", True):
                failed += 1

        print(f"  - 总 Token 消耗：{total_tokens}")
        print(f"  - Provider 分布：{providers}")
        print(f"  - 失败次数：{failed}")
        print(f"  - 平均耗时：{total_duration // len(all_calls)}ms")

    # 写入 stats.json
    stats = _read_json(STATS_FILE)
    stats["llm_calls"] = all_calls
    stats["total_visits"] = stats.get("total_visits", 0) + app_starts

    # 从日志时间戳生成访问记录
    existing_visits = stats.get("visits", [])
    for log_file in log_files:
        # 从文件名提取日期
        name = log_file.stem  # e.g. resume_optimizer_20260714
        date_part = name.split("_")[-1]  # 20260714
        try:
            d = datetime.strptime(date_part, "%Y%m%d")
            # 为该日期的每次启动添加一条记录
            with open(log_file, "r", encoding="utf-8") as f:
                start_count = sum(1 for line in f if "简历优化助手启动" in line)
            for _ in range(start_count):
                existing_visits.append(d.strftime("%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass

    # 去重 + 排序
    existing_visits = sorted(set(existing_visits))
    if len(existing_visits) > 2000:
        existing_visits = existing_visits[-2000:]
    stats["visits"] = existing_visits

    _write_json(STATS_FILE, stats)
    print(f"\n✅ 已写入 {STATS_FILE}")
    print(f"  - 累计访问：{stats.get('total_visits', 0)}")
    print(f"  - LLM 调用记录：{len(all_calls)} 条")


if __name__ == "__main__":
    main()
