import os
import json
import pathlib
import shutil
import statistics
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests


# =================== 配置 ===================
API_URL = "https://api.aring.cc/awakening-of-war-soul-ol/api/commerce/list"
DATA_FILE = "price_history.txt"
SITE_DIR = pathlib.Path("site")
TEMPLATE_FILE = pathlib.Path("app/templates/index.html")

CST = ZoneInfo("Asia/Shanghai")

COMMERCE_MAP = {
    1: "地精金库",
    2: "史莱姆保护协会",
    3: "传说武库",
    4: "明钻商户",
    5: "魔龙教会",
}

HEADERS = {
    "Host": "api.aring.cc",
    "Origin": "https://aring.cc",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_2_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/134.0.6998.33 Mobile/15E148 Safari/604.1",
    "Accept-Language": "zh-CN,zh-Hans;q=0.9",
    "Referer": "https://aring.cc/",
    "token": os.getenv("ARING_TOKEN", ""),  # 从 Secrets 注入
}

# =================== 时间工具 ===================
def now_cst():
    return datetime.now(CST)
SLOTS = [
    (10, 14, "10:00"),  # 10:00-13:59
    (14, 18, "14:00"),  # 14:00-17:59
    (18, 22, "18:00"),  # 18:00-21:59
    (22, 24, "22:00"),  # 22:00-23:59
]

def get_slot(now=None):
    """
    返回 (slot_date_str, slot_label)
    22:00-09:59 归到 22:00 档；00:00-09:59 归到【前一天】22:00 档。
    """
    if now is None:
        now = now_cst()
    h = now.hour
    # 凌晨 00:00-09:59 -> 前一天 22:00 档
    if h < 10:
        slot_date = (now - timedelta(days=1)).date()
        return slot_date.strftime("%Y/%m/%d"), "22:00"
    # 白天段按表匹配
    for start_h, end_h, label in SLOTS:
        if start_h <= h < end_h:
            return now.date().strftime("%Y/%m/%d"), label
    # 理论到不了这里，兜底到当日 22:00
    return now.date().strftime("%Y/%m/%d"), "22:00"

# =================== 历史数据读写 ===================
def try_fetch_history_from_pages():
    """
    运行开始前，尝试从上一次发布的 Pages 拉回历史数据，以便连续累计。
    在 Actions 中以环境变量传入：
      HISTORY_URL=https://<user>.github.io/<repo>/price_history.txt
    """
    history_url = os.getenv("HISTORY_URL")
    if not history_url:
        return
    try:
        r = requests.get(history_url, timeout=10)
        if r.status_code == 200 and r.text.strip():
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                f.write(r.text)
            print("✅ 已从 Pages 取回历史文件")
        else:
            print(f"ℹ️ 未从 Pages 获取到历史（status={r.status_code}）")
    except Exception as e:
        print(f"⚠️ 拉取历史失败：{e}")

def load_historical_data():
    """读取历史 price_history.txt，返回 {cid: [prices...]}"""
    hist = {cid: [] for cid in COMMERCE_MAP.keys()}
    if not os.path.exists(DATA_FILE):
        return hist
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    if not lines:
        return hist

    header = lines[0].split()
    expected_header = ["日期", "时间"] + [COMMERCE_MAP[cid] for cid in sorted(COMMERCE_MAP.keys())]
    if header != expected_header:
        print("⚠️ 表头不匹配，忽略历史。")
        return hist

    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2 + len(COMMERCE_MAP):
            continue
        for idx, cid in enumerate(sorted(COMMERCE_MAP.keys()), start=2):
            try:
                price = float(parts[idx])
                hist[cid].append(price)
            except Exception:
                pass
    return hist

def save_data_row(current_date, time_slot, commerce_data):
    """将当前价格追加到历史文件"""
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            header = "日期 时间 " + " ".join(COMMERCE_MAP[cid] for cid in sorted(COMMERCE_MAP.keys()))
            f.write(header + "\n")

    last_line = None
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        if len(lines) > 1:
            last_line = lines[-1].strip()

    if last_line:
        parts = last_line.split()
        if len(parts) >= 2:
            last_date, last_time = parts[0], parts[1]
            if last_date == current_date and last_time == time_slot:
                print(f"⚠️ {current_date} {time_slot} 已存在，跳过保存")
                return

    row = [current_date, time_slot] + [str(commerce_data.get(cid, 0)) for cid in sorted(COMMERCE_MAP.keys())]
    with open(DATA_FILE, "a", encoding="utf-8") as f:
        f.write(" ".join(row) + "\n")
    print("✅ 已追加到 price_history.txt")

# =================== 分析逻辑（来自你原脚本，略有整理） ===================
def calculate_trend_analysis(prices):
    if len(prices) < 3:
        return {
            'short_trend': '数据不足', 'mid_trend': '数据不足',
            'trend_strength': 0, 'trend_description': '数据不足',
            'short_slope': 0, 'mid_slope': 0, 'prices': prices
        }

    recent_3 = prices[-3:]
    short_trend_slope = (recent_3[-1] - recent_3[0]) / 2 if len(recent_3) == 3 else 0

    mid_window = min(7, len(prices))
    recent_mid = prices[-mid_window:]
    mid_trend_slope = (recent_mid[-1] - recent_mid[0]) / (len(recent_mid) - 1) if len(recent_mid) >= 2 else 0

    price_range = max(prices) - min(prices)
    if price_range > 0:
        short_strength = abs(short_trend_slope) / price_range * 100
        mid_strength = abs(mid_trend_slope) / price_range * 100
    else:
        short_strength = mid_strength = 0

    def get_trend_direction(slope, strength):
        if strength < 0.5: return "横盘"
        return "强势上升" if slope > 0 and strength > 2 else \
               "温和上升" if slope > 0 else \
               "强势下降" if slope < 0 and strength > 2 else "温和下降"

    short_direction = get_trend_direction(short_trend_slope, short_strength)
    mid_direction = get_trend_direction(mid_trend_slope, mid_strength)

    if short_direction == mid_direction:
        trend_desc = f"{mid_direction}，趋势稳定"
    elif "上升" in mid_direction and "上升" in short_direction:
        trend_desc = f"{mid_direction}，短期加速" if short_strength > mid_strength else f"{mid_direction}，短期减速"
    elif "下降" in mid_direction and "下降" in short_direction:
        trend_desc = f"{mid_direction}，短期加速" if short_strength > mid_strength else f"{mid_direction}，短期减速"
    elif ("上升" in mid_direction and "下降" in short_direction) or ("下降" in mid_direction and "上升" in short_direction):
        trend_desc = f"{mid_direction}，短期反转"
    else:
        trend_desc = f"中期{mid_direction}，短期{short_direction}"

    return {
        'short_trend': short_direction, 'mid_trend': mid_direction,
        'trend_strength': (short_strength + mid_strength) / 2,
        'trend_description': trend_desc, 'short_slope': short_trend_slope,
        'mid_slope': mid_trend_slope, 'prices': prices
    }

def calculate_price_analysis(current_price, historical_prices):
    if not historical_prices:
        return {'avg': current_price,'min': current_price,'max': current_price,
                'from_min_points': 0,'from_min_percent': 0,'from_max_points': 0,'from_max_percent': 0,
                'percentile': 50,'sample_size': 0}
    all_prices = historical_prices + [current_price]
    avg_price = statistics.mean(all_prices)
    min_price = min(all_prices); max_price = max(all_prices)
    from_min_points = current_price - min_price
    from_max_points = current_price - max_price
    price_range = max_price - min_price
    if price_range > 0:
        from_min_percent = (from_min_points / price_range) * 100
        from_max_percent = (from_max_points / price_range) * 100
    else:
        from_min_percent = from_max_percent = 0
    lower_count = sum(1 for p in all_prices if p < current_price)
    percentile = (lower_count / len(all_prices)) * 100
    return {
        'avg': avg_price,'min': min_price,'max': max_price,
        'from_min_points': from_min_points,'from_min_percent': from_min_percent,
        'from_max_points': from_max_points,'from_max_percent': from_max_percent,
        'percentile': percentile,'sample_size': len(historical_prices)
    }

def calculate_investment_advice(percentile, trend_analysis):
    if percentile <= 15: position_level = "极低位"
    elif percentile <= 35: position_level = "低位"
    elif percentile <= 65: position_level = "中位"
    elif percentile <= 85: position_level = "高位"
    else: position_level = "极高位"

    position_score = 10 - (percentile / 10)  # 0%-100% -> 10-0

    mid_trend = trend_analysis['mid_trend']
    short_trend = trend_analysis['short_trend']
    desc = trend_analysis['trend_description']

    if "强势上升" in mid_trend: direction = 2
    elif "温和上升" in mid_trend: direction = 1
    elif "横盘" in mid_trend: direction = 0
    elif "温和下降" in mid_trend: direction = -1
    else: direction = -2

    is_reversing_up = "反转" in desc and "上升" in short_trend and direction < 0
    is_reversing_down = "反转" in desc and "下降" in short_trend and direction > 0

    if percentile <= 15:
        if direction <= -1: trend_adj, reason = 5.0 + abs(direction)*2.0, "极低位深跌，强烈买入信号"
        elif direction >= 1: trend_adj, reason = 4.5 + direction*1.5, "极低位反弹，强烈买入"
        else: trend_adj, reason = 4.0, "极低位盘整，强烈买入"
    elif percentile <= 35:
        if direction <= -1: trend_adj, reason = 4.0 + abs(direction)*1.5, "低位深跌，抄底良机"
        elif direction >= 1: trend_adj, reason = 3.5 + direction*1.2, "低位反弹，趋势向好"
        else: trend_adj, reason = 3.0, "低位盘整，可逐步建仓"
    elif 65 < percentile < 85:
        if direction >= 1: trend_adj, reason = (2.5 if direction==2 else 2.8), "高位上涨，谨慎持有"
        elif direction <= -1:
            if "反转" in desc: trend_adj, reason = 1.5, "高位回落但出现反转信号，观望为主"
            else: trend_adj, reason = -1.0 - abs(direction)*0.5, "高位回落，建议减仓"
        else: trend_adj, reason = 1.8, "高位盘整，注意风险"
    elif percentile >= 85:
        if direction >= 1: trend_adj, reason = -4.0 - direction*1.0, "极高位追涨，风险极大"
        elif direction <= -1: trend_adj, reason = -2.0 - abs(direction)*0.8, "极高位回落，及时止盈"
        else: trend_adj, reason = -2.0, "极高位盘整，警惕回调"
    else:
        trend_adj = direction * 1.0
        reason = "中位上涨，可适量参与" if direction >= 1 else ("中位下跌，暂时观望" if direction <= -1 else "中位盘整，等待方向")

    if is_reversing_up:
        trend_adj += 2.0 if percentile <= 35 else (1.5 if percentile <= 65 else 1.0)
        reason = "低位止跌反弹，强烈买入" if percentile <= 35 else ("中位止跌反弹，可适量买入" if percentile <= 65 else "高位止跌反弹，谨慎持有，可适当加仓")
    elif is_reversing_down:
        trend_adj -= 2.0 if percentile >= 85 else (1.5 if percentile >= 65 else 0.5)
        reason = "极高位冲高回落，强烈卖出" if percentile >= 85 else ("高位冲高回落，建议减仓" if percentile >= 65 else "中低位冲高回落，暂时观望")

    final_score_internal = max(0, min(15, position_score + trend_adj))
    score_display = min(10, final_score_internal * 10 / 15)

    if score_display >= 8.5: advice, emoji, action = "💰💰💰强烈买入", "💰💰💰", "满仓买入"
    elif score_display >= 7.0: advice, emoji, action = "💰💰买入", "💰💰", "重仓买入"
    elif score_display >= 5.5: advice, emoji, action = "💰建议买入", "💰", "适量买入"
    elif score_display >= 4.5: advice, emoji, action = "👀观望等待", "👀", "暂时观望"
    elif score_display >= 3.0: advice, emoji, action = "⚠️谨慎持有", "⚠️", "谨慎持有，可适当加仓"
    elif score_display >= 2.0: advice, emoji, action = "💸建议卖出", "💸", "建议减仓"
    elif score_display >= 1.0: advice, emoji, action = "💸💸卖出", "💸💸", "重仓减仓"
    else: advice, emoji, action = "💸💸💸强烈卖出", "💸💸💸", "清仓离场"

    stars = "⭐" * max(1, min(5, round(score_display / 2)))
    prices = trend_analysis.get('prices', [])
    confidence = "低" if len(prices) < 5 else ("中" if len(prices) < 15 else "高")

    return {
        'advice': advice, 'advice_emoji': emoji, 'priority_score': score_display,
        'stars': stars, 'position_level': position_level, 'position_score': position_score,
        'trend_adjustment': trend_adj, 'trend_direction': direction, 'reason': reason,
        'action_desc': action, 'confidence': confidence
    }

def format_change_value(change):
    if change > 0: return f"+{change:.2f}📈"
    if change < 0: return f"{change:.2f}📉"
    return "0.00"

def format_analysis_text(commerce_name, current_price, change_value, analysis, trend_analysis, investment_advice):
    if analysis['percentile'] >= 80: level = "🔴高位"
    elif analysis['percentile'] >= 60: level = "🟡中高"
    elif analysis['percentile'] >= 40: level = "🟢中位"
    elif analysis['percentile'] >= 20: level = "🔵中低"
    else: level = "⚫低位"

    change_str = format_change_value(change_value)
    s = []
    s.append(f"{commerce_name} {level}")
    s.append(f"📊当前价格：{current_price:.2f} (变动：{change_str})")
    s.append(f"📅历史均价：{analysis['avg']:.2f}")
    s.append(f"🎬价格区间：{analysis['min']:.2f} ~ {analysis['max']:.2f}")
    s.append(f"⬆️距最高：{analysis['from_max_points']:.2f}点 ({analysis['from_max_percent']:.1f}%)")
    s.append(f"⬇️距最低：{analysis['from_min_points']:+.2f}点 ({analysis['from_min_percent']:.1f}%)")
    s.append(f"🧮百分位：{analysis['percentile']:.1f}% (样本：{analysis['sample_size']})")
    s.append(f"📈趋势分析：{trend_analysis['trend_description']}")
    s.append(f"💵投资建议：{investment_advice['advice']}")
    s.append(f"💡操作建议：{investment_advice['action_desc']}")
    s.append(f"📝理由：{investment_advice['reason']}")
    s.append(f"🪙优先级：{investment_advice['stars']}")
    s.append(f"🧾评分：{investment_advice['priority_score']:.1f}/10")
    return "\n".join(s)

# =================== 图表数据与页面生成 ===================
def build_series_from_history():
    """读取 price_history.txt -> 图表数据 payload"""
    if not os.path.exists(DATA_FILE):
        return {"updated_at": now_cst().strftime("%Y-%m-%d %H:%M:%S"), "x": [], "series": []}

    times = []
    values_by_cid = {cid: [] for cid in sorted(COMMERCE_MAP.keys())}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    if len(lines) <= 1:
        return {"updated_at": now_cst().strftime("%Y-%m-%d %H:%M:%S"), "x": [], "series": []}

    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2 + len(COMMERCE_MAP):
            continue
        date_str, time_str = parts[0], parts[1]
        times.append(f"{date_str} {time_str}")
        for idx, cid in enumerate(sorted(COMMERCE_MAP.keys()), start=2):
            try:
                v = float(parts[idx])
            except Exception:
                v = None
            values_by_cid[cid].append(v)

    series = [{"id": cid, "name": COMMERCE_MAP[cid], "values": values_by_cid[cid]}
              for cid in sorted(COMMERCE_MAP.keys())]

    return {"updated_at": now_cst().strftime("%Y-%m-%d %H:%M:%S"), "x": times, "series": series}

def write_site_assets(chart_payload: dict, report_text: str):
    """
    生成站点：
      - site/data.json
      - site/index.html（含“最后更新”与“报告”）
      - site/price_history.txt（隐藏链接但保留文件）
    """
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    # data.json
    (SITE_DIR / "data.json").write_text(
        json.dumps(chart_payload, ensure_ascii=False),
        encoding="utf-8"
    )

    # 历史文件（便于后续拉取）
    if os.path.exists(DATA_FILE):
        shutil.copyfile(DATA_FILE, SITE_DIR / "price_history.txt")

    # index.html
    html = TEMPLATE_FILE.read_text(encoding="utf-8")
    html = html.replace("{{updated_at}}", chart_payload.get("updated_at", ""))
    html = html.replace("{{report}}", report_text or "")
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")

    print("✅ 已生成：site/index.html, site/data.json, site/price_history.txt")

# =================== 主流程 ===================
def run():
    if not HEADERS.get("token"):
        raise RuntimeError("缺少 ARING_TOKEN 环境变量，请在 GitHub Secrets 配置。")

    print("🚀 拉回历史 …")
    try_fetch_history_from_pages()

    print("🚀 拉取最新价格 …")
    r = requests.get(API_URL, headers=HEADERS, timeout=12)
    if r.status_code != 200:
        raise RuntimeError(f"请求失败：HTTP {r.status_code}")
    payload = r.json()
    if "data" not in payload or not isinstance(payload["data"], list):
        raise RuntimeError("返回数据格式异常")

    # 当前档位（北京时间）
    now = now_cst()
    current_date, time_slot = get_slot(now)  # ← 这里会处理 00:00-09:59 归前一天 22:00


    # 整理当期价格
    commerce_data = {}
    commerce_changes = {}
    for item in payload["data"]:
        cid = item.get("commerceId")
        if cid in COMMERCE_MAP:
            commerce_data[cid] = item.get("price", 0)
            commerce_changes[cid] = item.get("changeValue", 0)

    if not commerce_data:
        raise RuntimeError("未获取到有效的价格数据")

    # 载入历史，构建报告
    historical = load_historical_data()

    title = f"📊 {current_date} {time_slot} 价格监控报告\n{'='*40}\n"
    report_lines = [title]

    commerce_analysis = {}
    for cid in sorted(COMMERCE_MAP.keys()):
        if cid not in commerce_data:
            continue
        name = COMMERCE_MAP[cid]
        cur = commerce_data[cid]
        chg = commerce_changes.get(cid, 0.0)
        hist = historical.get(cid, [])

        pa = calculate_price_analysis(cur, hist)
        trend = calculate_trend_analysis(hist + [cur])
        adv = calculate_investment_advice(pa['percentile'], trend)

        block = format_analysis_text(name, cur, chg, pa, trend, adv)
        report_lines.append(block + "\n")

        commerce_analysis[cid] = {'name': name, 'priority_score': adv['priority_score']}

    # 排行
    report_lines.append(f"{'='*40}\n📈 投资优先级排行榜")
    for i, (cid, data) in enumerate(sorted(commerce_analysis.items(),
                                           key=lambda x: x[1]['priority_score'],
                                           reverse=True), 1):
        report_lines.append(f"{i}. {data['name']} ({data['priority_score']:.1f}分)")

    final_report = "\n".join(report_lines).strip()

    # 追加历史
    save_data_row(current_date, time_slot, commerce_data)

    # 生成图表数据 + 页面
    chart_payload = build_series_from_history()
    chart_payload["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")  # 用北京时间
    write_site_assets(chart_payload, report_text=final_report)

    print("🎉 完成")

if __name__ == "__main__":
    run()
