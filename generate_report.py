#!/usr/bin/env python3
"""
每日足球赛事盘口分析 — 云端版
GitHub Actions 定时运行，生成 HTML 报告并发布到 GitHub Pages。
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
import requests

# ─── 配置 ───────────────────────────────────────────────
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

TARGET_LEAGUES = {
    "韩K联": "k-league",
    "日J1": "j1-league",
    "日J2": "j2-league",
    "澳超": "a-league",
    "英超": "premier-league",
    "西甲": "la-liga",
    "德甲": "bundesliga",
    "意甲": "serie-a",
    "法甲": "ligue-1",
    "德乙": "2-bundesliga",
    "荷乙": "eerste-divisie",
    "意乙": "serie-b",
    "美职联MLS": "mls",
    "墨超": "liga-mx",
    "巴甲": "brasileirao",
    "阿甲": "primera-division",
}

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "docs")
TOMORROW = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

# ─── HTML 模板 ───────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>足球赛事盘口分析 — {date}</title>
<style>
  :root {{
    --bg: #0f1117; --card-bg: #1a1d27; --border: #2a2d37;
    --text: #e0e0e0; --text-secondary: #999;
    --accent: #4a90d9; --red: #e74c3c; --green: #27ae60;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.7; padding: 20px;
  }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  .header {{
    text-align: center; padding: 40px 20px 30px;
    border-bottom: 1px solid var(--border); margin-bottom: 30px;
  }}
  .header h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 8px; }}
  .header .date {{ color: var(--accent); font-size: 16px; }}
  .header .meta {{ color: var(--text-secondary); font-size: 13px; margin-top: 12px; }}
  .league-section {{ margin-bottom: 40px; }}
  .league-title {{
    font-size: 20px; font-weight: 700; padding: 10px 16px;
    border-left: 4px solid var(--accent); background: var(--card-bg);
    border-radius: 4px; margin-bottom: 16px;
  }}
  .match-card {{
    background: var(--card-bg); border-radius: 8px; padding: 20px;
    margin-bottom: 16px; border: 1px solid var(--border);
  }}
  .match-header {{
    font-size: 18px; font-weight: 600; margin-bottom: 12px;
    padding-bottom: 12px; border-bottom: 1px solid var(--border);
  }}
  .match-header .time {{ color: var(--accent); font-size: 14px; margin-left: 8px; }}
  .info-row {{
    display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;
  }}
  .tag {{
    background: #252836; padding: 4px 10px; border-radius: 4px;
    font-size: 12px; color: var(--text-secondary);
  }}
  .analysis-block {{ margin-bottom: 12px; }}
  .analysis-block .label {{
    font-weight: 600; color: var(--accent); font-size: 14px;
    display: inline-block; margin-right: 6px;
  }}
  .analysis-block .content {{ color: #ccc; font-size: 14px; }}
  .up {{ color: var(--red); font-weight: 600; }}
  .down {{ color: var(--green); font-weight: 600; }}
  .odds-table {{
    width: 100%; border-collapse: collapse; margin: 12px 0;
    font-size: 13px;
  }}
  .odds-table th {{
    background: #252836; padding: 8px 12px; text-align: left;
    font-weight: 500; color: var(--text-secondary);
  }}
  .odds-table td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); }}
  .no-match {{
    padding: 12px 16px; color: var(--text-secondary);
    background: var(--card-bg); border-radius: 4px;
  }}
  .footer {{
    text-align: center; padding: 30px 20px; color: var(--text-secondary);
    font-size: 12px; border-top: 1px solid var(--border); margin-top: 20px;
  }}
  .disclaimer {{
    background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
    padding: 16px; margin: 20px 0; font-size: 12px; color: #888;
  }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>⚽ 足球赛事盘口分析</h1>
  <div class="date">{date}（{weekday}）</div>
  <div class="meta">数据更新：{update_time} | 联赛：{league_count}个 | 比赛：{match_count}场</div>
</div>
<div class="disclaimer">
  ⚠️ 本报告由 AI 自动生成，仅供信息参考，不构成任何投注建议。
  盘口数据来自公开来源，可能与实际盘口存在偏差。投注有风险，决策需谨慎。
</div>
{content}
<div class="footer">
  <p>每日自动更新 · {gen_time} 生成 · Powered by GitHub Actions</p>
</div>
</div>
</body>
</html>"""


def call_llm(system_prompt: str, user_prompt: str) -> str:
    """调用 LLM API"""
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 环境变量未设置")

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 8192,
    }

    resp = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def build_analysis_prompt() -> str:
    """构建分析 prompt"""
    return f"""你是资深足球盘口分析师。请联网搜索核查 {TOMORROW} 的以下联赛所有比赛：

{chr(10).join(f'- {name}' for name in TARGET_LEAGUES)}

对每场比赛按以下格式输出 HTML（直接输出可嵌入的 HTML 片段，不要输出代码块标记）：

<div class="league-section">
<div class="league-title">【联赛名】</div>
（如果该联赛明日无比赛，输出：<div class="no-match">明日无赛事</div>）

每场比赛用：
<div class="match-card">
<div class="match-header">主队 vs 客队 <span class="time">开赛时间（北京时间）</span></div>

<div class="info-row">
<span class="tag">亚盘初盘：xxx</span>
<span class="tag">即时盘口：xxx</span>
</div>

<div class="analysis-block">
<span class="label">① 市场直觉与误区</span>
<div class="content">...</div>
</div>
<div class="analysis-block">
<span class="label">② 真强/虚强/真弱/假弱</span>
<div class="content">...</div>
</div>
<div class="analysis-block">
<span class="label">③ 阵容伤停体能战意主客</span>
<div class="content">...</div>
</div>
<div class="analysis-block">
<span class="label">④ 市场态度匹配度</span>
<div class="content">...</div>
</div>
<div class="analysis-block">
<span class="label">⑤ 正反最强证据</span>
<div class="content">...</div>
</div>
<div class="analysis-block">
<span class="label">⑥ 带条件倾向 + 失效条件</span>
<div class="content">...</div>
</div>
</div>

</div>

要求：
- 涨用 class="up" 红字，跌用 class="down" 绿字
- 严禁使用"稳赚、必胜、稳胆、包赢、内幕"
- 风格：强节奏拆盘型，开门见山、短句、少废话
- 至少交叉核实两处来源，注明更新时间
- 如某联赛无比赛，用 no-match 样式标注
- 只输出 HTML 片段，不要包含 markdown 代码块标记
- 信息更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}（首次抓取）"""


def count_matches(html_content: str) -> int:
    """统计比赛数量"""
    return html_content.count('class="match-card"')


def count_leagues(html_content: str) -> int:
    """统计联赛数量"""
    return html_content.count('class="league-title"')


def main():
    print(f"🚀 开始生成 {TOMORROW} 足球赛事分析报告...")

    system_prompt = """你是资深足球盘口分析师。你必须通过联网搜索获取真实数据，严禁编造。
每场比赛至少交叉核实两处来源。输出纯 HTML 片段（不含 markdown 标记）。"""

    user_prompt = build_analysis_prompt()

    print("📡 调用 LLM 生成报告...")
    try:
        analysis_html = call_llm(system_prompt, user_prompt)
    except Exception as e:
        print(f"❌ LLM 调用失败: {e}")
        # 生成一个错误页面
        analysis_html = f'<div class="no-match">⚠️ 报告生成失败: {e}<br>请检查 API 配���后重试。</div>'

    # 统计
    match_count = count_matches(analysis_html)
    league_count = count_leagues(analysis_html)

    # 构建完整 HTML
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[now.weekday()]

    # 清理 LLM 输出中可能的 markdown 标记
    analysis_html = analysis_html.strip()
    if analysis_html.startswith("```html"):
        analysis_html = analysis_html[7:]
    if analysis_html.startswith("```"):
        analysis_html = analysis_html[3:]
    if analysis_html.endswith("```"):
        analysis_html = analysis_html[:-3]
    analysis_html = analysis_html.strip()

    full_html = HTML_TEMPLATE.format(
        date=TOMORROW,
        weekday=weekday,
        update_time=now.strftime("%Y-%m-%d %H:%M"),
        league_count=league_count,
        match_count=match_count,
        content=analysis_html,
        gen_time=now.strftime("%Y-%m-%d %H:%M:%S"),
    )

    # 写入文件
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    # 同时保存一个带日期的副本
    archive_path = os.path.join(OUTPUT_DIR, f"report_{TOMORROW}.html")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    # 计算文件信息
    sha1 = hashlib.sha1(full_html.encode()).hexdigest()
    size_kb = len(full_html.encode()) / 1024

    print(f"✅ 报告已生成: {output_path}")
    print(f"   大小: {size_kb:.1f} KB | SHA1: {sha1}")
    print(f"   联赛: {league_count} | 比赛: {match_count}")
    print(f"   归档: {archive_path}")

    # 输出 GitHub Actions 需要的摘要
    if "GITHUB_STEP_SUMMARY" in os.environ:
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"## ⚽ 足球赛事盘口分析 — {TOMORROW}\n\n")
            f.write(f"- **联赛数**: {league_count}\n")
            f.write(f"- **比赛数**: {match_count}\n")
            f.write(f"- **文件大小**: {size_kb:.1f} KB\n")
            f.write(f"- **生成时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- **访问地址**: [查看报告](https://{os.environ.get('GITHUB_REPOSITORY_OWNER', 'USER')}.github.io/{os.environ.get('GITHUB_REPOSITORY_NAME', 'cloud-football')}/)\n")


if __name__ == "__main__":
    main()
