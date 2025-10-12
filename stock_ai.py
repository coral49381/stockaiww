import os
import re
import time
import requests
import pandas as pd
import akshare as ak
import streamlit as st
import numpy as np
from datetime import datetime, timedelta

# 获取当前时间
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 代理配置 - 初始设置为None
PROXY_SETTINGS = None

# 全局请求设置
REQUEST_TIMEOUT = 45  # 增加超时时间
MAX_RETRIES = 3
RETRY_DELAY = 2

# 直接在这里设置您的API密钥
DEEPSEEK_API_KEY = "sk-e9e5e5b7565b4f809de1c8d53c22fa1b"

# 带代理和重试机制的请求函数
def robust_request(url, method='get', params=None, json=None, headers=None):
    """带代理支持、超时设置和自动重试的HTTP请求函数"""
    proxies = PROXY_SETTINGS if PROXY_SETTINGS else None
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers=headers,
                proxies=proxies,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            error_msg = f"请求失败 (尝试 {attempt+1}/{MAX_RETRIES}): {str(e)}"
            st.error(error_msg)
            
            # 特定错误处理
            if "Read timed out" in str(e):
                st.warning("API响应超时，可能是网络问题或服务器繁忙")
            elif "ProxyError" in str(e) and PROXY_SETTINGS:
                st.error("代理连接失败！请检查代理设置或尝试禁用代理。")
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None
    return None

# 获取股票数据函数
def get_stock_data(stock_code, start_date, end_date):
    """使用AKShare获取股票数据"""
    try:
        stock_df = ak.stock_zh_a_hist(
            symbol=stock_code, 
            period="daily", 
            start_date=start_date, 
            end_date=end_date,
            adjust="qfq"
        )
        # 重命名列为英文
        stock_df = stock_df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume'
        })
        return stock_df
    except Exception as e:
        st.error(f"获取股票数据失败: {str(e)}")
        return None

# 获取板块资金流向
def get_sector_fund_flow():
    """获取行业板块资金流向"""
    try:
        # 新版本AKShare接口
        sector_df = ak.stock_sector_fund_flow_rank(indicator="今日")
        
        # 确保有"净额"列
        if "净额" not in sector_df.columns and "主力净流入-净额" in sector_df.columns:
            sector_df["净额"] = sector_df["主力净流入-净额"]
        
        if "净额" in sector_df.columns:
            sector_df = sector_df.sort_values("净额", ascending=False)
            return sector_df.head(10)
        else:
            st.error("板块资金流向数据中缺少'净额'列")
            return None
    except Exception as e:
        st.error(f"获取板块资金流向失败: {str(e)}")
        return None

# 获取龙头股信息
def get_leading_stocks():
    """获取各板块龙头股"""
    try:
        # 获取涨停股
        date_str = datetime.now().strftime("%Y%m%d")
        limit_up = ak.stock_zt_pool_em(date=date_str)
        
        # 使用正确的列名 "涨跌幅"
        if "涨跌幅" in limit_up.columns:
            limit_up = limit_up.sort_values("涨跌幅", ascending=False)
        elif "最新涨跌幅" in limit_up.columns:  # 兼容旧版本
            limit_up = limit_up.sort_values("最新涨跌幅", ascending=False)
        else:
            # 尝试找到涨跌幅列
            for col in limit_up.columns:
                if "涨" in col and "幅" in col:
                    limit_up = limit_up.sort_values(col, ascending=False)
                    break
            else:
                # 默认按第4列排序
                limit_up = limit_up.sort_values(limit_up.columns[3], ascending=False)
        
        return limit_up.head(10)
    except Exception as e:
        st.error(f"获取龙头股失败: {str(e)}")
        return None

# 技术指标分析函数
def enhanced_analyze_stock(df):
    """增强版技术指标分析"""
    if df is None or df.empty:
        return None
    
    try:
        # 计算移动平均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()
        
        # 计算MACD
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp12 - exp26
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Histogram'] = df['MACD'] - df['Signal']
        
        # 计算RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).fillna(0).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 计算布林带
        df['MiddleBand'] = df['close'].rolling(window=20).mean()
        df['UpperBand'] = df['MiddleBand'] + 2 * df['close'].rolling(window=20).std()
        df['LowerBand'] = df['MiddleBand'] - 2 * df['close'].rolling(window=20).std()
        
        # 计算成交量变化
        df['VolumeChange'] = df['volume'].pct_change()
        
        # 确定趋势
        df['Trend'] = '中性'
        df.loc[(df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20']), 'Trend'] = '上升'
        df.loc[(df['MA5'] < df['MA10']) & (df['MA10'] < df['MA20']), 'Trend'] = '下降'
        
        # 标记关键点
        df['Breakout'] = df['close'] > df['UpperBand'].shift(1)
        df['Breakdown'] = df['close'] < df['LowerBand'].shift(1)
        
        # 标记金叉死叉
        df['GoldenCross'] = (df['MACD'] > df['Signal']) & (df['MACD'].shift(1) < df['Signal'].shift(1))
        df['DeathCross'] = (df['MACD'] < df['Signal']) & (df['MACD'].shift(1) > df['Signal'].shift(1))
        
        # 记录信号发生的日期
        df['BuySignalDate'] = None
        df['SellSignalDate'] = None
        df.loc[df['GoldenCross'], 'BuySignalDate'] = df['date']
        df.loc[df['DeathCross'], 'SellSignalDate'] = df['date']
        
        return df.tail(30)  # 返回最近30天数据
    except Exception as e:
        st.error(f"技术分析失败: {str(e)}")
        return None

# 生成详细技术报告
def generate_technical_report(analysis_data):
    """生成详细的技术分析报告"""
    if analysis_data is None or analysis_data.empty:
        return "无有效数据生成报告"
    
    last_row = analysis_data.iloc[-1]
    report = f"### 技术分析报告\n\n"
    report_date = last_row['date'].strftime('%Y-%m-%d')
    report += f"**最后交易日**: {report_date}\n\n"
    
    # 趋势判断
    report += f"**趋势分析**:\n"
    report += f"- 当前趋势: {last_row['Trend']}\n"
    report += f"- 5日线: {last_row['MA5']:.2f}, 10日线: {last_row['MA10']:.2f}, 20日线: {last_row['MA20']:.2f}\n"
    
    if last_row['Trend'] == '上升':
        report += "- 均线呈多头排列，短期趋势向好\n"
    elif last_row['Trend'] == '下降':
        report += "- 均线呈空头排列，短期趋势向淡\n"
    
    # MACD分析
    report += f"\n**MACD分析**:\n"
    report += f"- DIF值: {last_row['MACD']:.4f}, DEA值: {last_row['Signal']:.4f}\n"
    
    if last_row['GoldenCross']:
        report += f"- ✅ MACD金叉形成（{report_date}），买入信号\n"
    elif last_row['DeathCross']:
        report += f"- ⛔ MACD死叉形成（{report_date}），卖出信号\n"
    
    if last_row['Histogram'] > 0:
        report += "- MACD柱状线在0轴上方，多头力量占优\n"
    else:
        report += "- MACD柱状线在0轴下方，空头力量占优\n"
    
    # RSI分析
    report += f"\n**RSI分析**:\n"
    report += f"- RSI(14): {last_row['RSI']:.2f}\n"
    
    if last_row['RSI'] > 70:
        report += "- ⚠️ RSI进入超买区域，注意回调风险\n"
    elif last_row['RSI'] < 30:
        report += "- ✅ RSI进入超卖区域，可能有反弹机会\n"
    else:
        report += "- RSI处于合理区间\n"
    
    # 布林带分析
    report += f"\n**布林带分析**:\n"
    report += f"- 上轨: {last_row['UpperBand']:.2f}, 中轨: {last_row['MiddleBand']:.2f}, 下轨: {last_row['LowerBand']:.2f}\n"
    report += f"- 当前价格: {last_row['close']:.2f}\n"
    
    if last_row['close'] > last_row['UpperBand']:
        report += "- ⚠️ 价格突破上轨，警惕超买风险\n"
    elif last_row['close'] < last_row['LowerBand']:
        report += "- ✅ 价格跌破下轨，可能有超跌反弹机会\n"
    else:
        report += "- 价格在布林带通道内运行\n"
    
    # 成交量分析
    report += f"\n**成交量分析**:\n"
    report += f"- 今日成交量: {last_row['volume']:,}手\n"
    report += f"- 成交量变化: {last_row['VolumeChange']*100:.2f}%\n"
    
    if last_row['VolumeChange'] > 0.5:
        report += "- ✅ 成交量显著放大，可能有主力资金介入\n"
    elif last_row['VolumeChange'] < -0.3:
        report += "- ⚠️ 成交量明显萎缩，市场参与度降低\n"
    
    # 显示最近买卖信号
    buy_signals = analysis_data[analysis_data['BuySignalDate'].notnull()]
    sell_signals = analysis_data[analysis_data['SellSignalDate'].notnull()]
    
    if not buy_signals.empty:
        last_buy = buy_signals.iloc[-1]['date'].strftime('%Y-%m-%d')
        report += f"\n**最近买入信号**: {last_buy}\n"
    
    if not sell_signals.empty:
        last_sell = sell_signals.iloc[-1]['date'].strftime('%Y-%m-%d')
        report += f"**最近卖出信号**: {last_sell}\n"
    
    return report

# 生成买卖点建议
def generate_trade_recommendation(analysis_data, sector_data, leading_stocks):
    """生成买卖点建议"""
    if analysis_data is None or analysis_data.empty:
        return "无有效数据生成建议"
    
    last_row = analysis_data.iloc[-1]
    report_date = last_row['date'].strftime('%Y-%m-%d')
    recommendation = ""
    
    # 买点判断逻辑
    buy_signals = []
    
    # 1. 技术面信号
    if last_row['GoldenCross']:
        buy_signals.append(f"MACD金叉（{report_date}）")
    if last_row['RSI'] < 35:
        buy_signals.append(f"RSI超卖（{report_date}）")
    if last_row['close'] < last_row['LowerBand']:
        buy_signals.append(f"布林带下轨支撑（{report_date}）")
    if last_row['VolumeChange'] > 0.5 and last_row['close'] > last_row['open']:
        buy_signals.append(f"放量上涨（{report_date}）")
    
    # 2. 板块热点
    if sector_data is not None and not sector_data.empty:
        buy_signals.append("所属板块资金流入")
    
    # 3. 市场情绪 - 龙头股表现
    if leading_stocks is not None and not leading_stocks.empty:
        # 尝试获取涨跌幅列
        change_col = None
        for col in ['涨跌幅', '涨幅', '最新涨跌幅']:
            if col in leading_stocks.columns:
                change_col = col
                break
        
        if change_col:
            avg_change = leading_stocks[change_col].mean()
            if avg_change > 3:
                buy_signals.append("市场情绪高涨")
    
    # 卖点判断逻辑
    sell_signals = []
    
    # 1. 技术面信号
    if last_row['DeathCross']:
        sell_signals.append(f"MACD死叉（{report_date}）")
    if last_row['RSI'] > 70:
        sell_signals.append(f"RSI超买（{report_date}）")
    if last_row['close'] > last_row['UpperBand']:
        sell_signals.append(f"布林带上轨压力（{report_date}）")
    if last_row['VolumeChange'] > 0.5 and last_row['close'] < last_row['open']:
        sell_signals.append(f"放量下跌（{report_date}）")
    
    # 2. 板块资金流出
    if sector_data is None or sector_data.empty:
        sell_signals.append("所属板块资金流出")
    
    # 3. 急拉信号
    if (last_row['close'] - last_row['open']) / last_row['open'] > 0.07:
        sell_signals.append(f"单日急涨（{report_date}）")
    
    # 综合判断
    if buy_signals and not sell_signals:
        recommendation = "✅ **强烈买入**: " + ", ".join(buy_signals)
    elif buy_signals and sell_signals:
        recommendation = "⚠️ **谨慎买入**: " + ", ".join(buy_signals) + " | 风险因素: " + ", ".join(sell_signals)
    elif not buy_signals and sell_signals:
        recommendation = "⛔ **建议卖出**: " + ", ".join(sell_signals)
    else:
        recommendation = "➖ **持有观望**: 无明显买卖信号"
    
    return recommendation

# 高级AI分析函数
def advanced_ai_analysis(stock_data, sector_data, leading_stocks, user_query):
    """使用DeepSeek API进行高级分析"""
    api_url = "https://api.deepseek.com/v1/chat/completions"
    
    # 验证API密钥是否设置
    if not DEEPSEEK_API_KEY:
        return "错误：缺少DeepSeek API密钥"
    
    # 准备数据摘要
    data_summary = ""
    
    if stock_data is not None and not stock_data.empty:
        data_summary += f"### 股票技术数据摘要:\n{stock_data[['date', 'close', 'MA5', 'MA20', 'MACD', 'RSI']].tail(3).to_string()}\n\n"
    
    if sector_data is not None and not sector_data.empty:
        data_summary += f"### 板块资金流向:\n{sector_data.head(3).to_string()}\n\n"
    
    if leading_stocks is not None and not leading_stocks.empty:
        data_summary += f"### 龙头股表现:\n{leading_stocks.head(3).to_string()}\n\n"
    
    # 准备请求数据
    prompt = f"""
    你是一位顶尖的股票交易员和量化分析师，请根据以下市场数据和用户查询进行专业分析：
    
    {data_summary}
    
    用户查询: {user_query}
    
    请从以下几个维度进行分析：
    1. 技术面分析：结合MACD、RSI、均线系统、布林带等指标
    2. 资金面分析：板块资金流向、主力资金动向
    3. 市场情绪：涨停板数量、龙头股表现、题材热度
    4. 买卖点建议：根据"买在起涨点，卖在急拉时"的原则给出具体建议
    5. 风险提示：潜在风险因素和仓位管理建议
    
    请用专业但易懂的语言撰写报告，包含具体数据支持。
    """
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是顶尖的量化交易员，精通技术分析、资金流向分析和市场情绪把握，擅长捕捉板块轮动和龙头股机会。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.25,
        "max_tokens": 1500
    }
    
    try:
        response = robust_request(
            url=api_url, 
            method='post', 
            json=payload, 
            headers=headers
        )
        
        if response is not None and response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        elif response is not None:
            error_detail = response.text if hasattr(response, 'text') else str(response)
            return f"API返回错误: {response.status_code} - {error_detail[:200]}"
        else:
            return "API请求失败，请检查网络连接或代理设置"
    except Exception as e:
        return f"获取AI推荐失败: {str(e)}"

# Streamlit应用界面
def main():
    global PROXY_SETTINGS
    
    st.set_page_config(
        page_title="智能选股系统", 
        page_icon="📈", 
        layout="wide"
    )
    
    st.title("🚀 智能选股系统")
    st.caption(f"最后更新: {current_time} | 使用AKShare和DeepSeek API")
    
    # 初始化session state
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []
    
    if 'stock_data' not in st.session_state:
        st.session_state.stock_data = None
    
    # 显示API密钥状态
    if DEEPSEEK_API_KEY:
        st.sidebar.success("DeepSeek API密钥已设置")
    else:
        st.sidebar.error("DeepSeek API密钥未设置")
    
    # 侧边栏设置
    with st.sidebar:
        st.header("智能选股设置")
        
        # 代理设置选项
        st.subheader("网络设置")
        use_proxy = st.checkbox("启用代理", value=False)
        proxy_address = st.text_input("代理地址 (格式: http://ip:port)", "http://127.0.0.1:7890")
        
        if use_proxy:
            PROXY_SETTINGS = {
                'http': proxy_address,
                'https': proxy_address
            }
            st.info(f"当前代理设置: {PROXY_SETTINGS}")
        else:
            PROXY_SETTINGS = None
            st.info("不使用代理")
        
        st.markdown("### 常见代理端口")
        st.markdown("""
        - Clash: `7890`
        - V2Ray: `10809`
        - Shadowsocks: `1080`
        - Qv2ray: `8889`
        """)
        
        st.divider()
        
        # 市场数据获取
        st.subheader("市场数据")
        if st.button("获取板块资金流向"):
            with st.spinner("获取板块数据中..."):
                st.session_state.sector_data = get_sector_fund_flow()
        
        if st.button("获取龙头股信息"):
            with st.spinner("获取龙头股数据中..."):
                st.session_state.leading_stocks = get_leading_stocks()
        
        st.divider()
        
        # 自选股管理
        st.subheader("自选股管理")
        new_stock = st.text_input("添加股票代码", "000001")
        if st.button("添加到自选"):
            if new_stock and new_stock not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_stock)
                st.success(f"已添加 {new_stock} 到自选股")
        
        if st.session_state.watchlist:
            selected = st.selectbox("自选股列表", st.session_state.watchlist)
            if st.button("分析选中股票"):
                st.session_state.current_stock = selected
    
    # 主界面 - 对话区域
    st.subheader("智能选股助手")
    
    # 显示历史消息
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # 用户输入
    if prompt := st.chat_input("请输入股票代码或选股策略..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        stock_pattern = r'(\d{6})'
        matches = re.findall(stock_pattern, prompt)
        
        if matches:
            stock_code = matches[0]
            st.session_state.current_stock = stock_code
            response = f"已选择股票 {stock_code}，正在分析中..."
        elif "分析自选" in prompt:
            if st.session_state.watchlist:
                response = f"开始分析自选股：{', '.join(st.session_state.watchlist)}..."
            else:
                response = "自选股列表为空，请先添加股票"
        elif "板块" in prompt or "热点" in prompt:
            response = "正在分析当前板块热点和资金流向..."
        elif "龙头" in prompt:
            response = "正在分析当前市场龙头股表现..."
        else:
            response = "正在分析市场情况..."
        
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown(response)
            
            if hasattr(st.session_state, 'current_stock'):
                with st.spinner("获取股票数据中..."):
                    stock_data = get_stock_data(
                        st.session_state.current_stock,
                        (datetime.now() - timedelta(days=180)).strftime("%Y%m%d"),
                        datetime.now().strftime("%Y%m%d")
                    )
                
                if stock_data is not None and not stock_data.empty:
                    with st.spinner("技术分析中..."):
                        analysis_data = enhanced_analyze_stock(stock_data.copy())
                    
                    if analysis_data is not None:
                        sector_data = st.session_state.get('sector_data', None)
                        leading_stocks = st.session_state.get('leading_stocks', None)
                        
                        tech_report = generate_technical_report(analysis_data)
                        trade_recommendation = generate_trade_recommendation(analysis_data, sector_data, leading_stocks)
                        
                        with st.spinner("AI深度分析中..."):
                            ai_analysis = advanced_ai_analysis(
                                analysis_data, 
                                sector_data, 
                                leading_stocks, 
                                f"请分析股票{st.session_state.current_stock}的投资机会"
                            )
                        
                        # 绘制基础K线图
                        st.subheader(f"{st.session_state.current_stock} 价格走势")
                        st.line_chart(analysis_data.set_index('date')['close'])
                        
                        full_response = f"## {st.session_state.current_stock} 深度分析报告\n\n"
                        full_response += f"### 💡 买卖点建议\n{trade_recommendation}\n\n"
                        full_response += tech_report + "\n\n"
                        full_response += f"### 🤖 AI专业分析\n{ai_analysis}\n\n"
                        
                        message_placeholder.markdown(full_response)
                    else:
                        message_placeholder.error("技术分析失败")
                else:
                    message_placeholder.error("股票数据获取失败")
        
        st.session_state.messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()
