import os
import re
import time
import requests
import pandas as pd
import akshare as ak
import streamlit as st
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go

# 获取当前时间
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 代理配置
PROXY_SETTINGS = None

# 全局请求设置
REQUEST_TIMEOUT = 45
MAX_RETRIES = 3
RETRY_DELAY = 2

# 设置您的API密钥
DEEPSEEK_API_KEY = "sk-e9e5e5b7565b4f809de1c8d53c22fa1b"

# 带代理和重试机制的请求函数
def robust_request(url, method='get', params=None, json=None, headers=None):
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
    try:
        stock_df = ak.stock_zh_a_hist(
            symbol=stock_code, 
            period="daily", 
            start_date=start_date, 
            end_date=end_date,
            adjust="qfq"
        )
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
    try:
        sector_df = ak.stock_sector_fund_flow_rank(indicator="今日")
        
        # 列名兼容处理
        amount_column = '主力净流入-净额'
        if amount_column in sector_df.columns:
            sector_df = sector_df.rename(columns={amount_column: '净额'})
            return sector_df.sort_values("净额", ascending=False).head(10)
        else:
            # 尝试备用列名
            for col in sector_df.columns:
                if "净流入" in col or "净额" in col:
                    return sector_df.sort_values(col, ascending=False).head(10)
            return None
    except Exception as e:
        st.error(f"获取板块资金流向失败: {str(e)}")
        return None

# 获取龙头股信息
def get_leading_stocks():
    try:
        date_str = datetime.now().strftime("%Y%m%d")
        limit_up = ak.stock_zt_pool_em(date=date_str)
        
        # 列名兼容处理
        change_column = None
        for col in ['涨跌幅', '涨幅', '最新涨跌幅', '涨跌']:
            if col in limit_up.columns:
                change_column = col
                break
        
        if change_column:
            return limit_up.sort_values(change_column, ascending=False).head(10)
        else:
            return limit_up.head(10)
    except Exception as e:
        st.error(f"获取龙头股失败: {str(e)}")
        return None

# 选股引擎
def stock_selection_engine(sector_data, leading_stocks):
    """选股引擎：结合板块资金和龙头股表现"""
    selected_stocks = []
    
    if sector_data is not None and not sector_data.empty:
        # 获取资金流入前三板块
        top_sectors = sector_data.head(3)
        
        # 尝试获取板块名称列
        sector_name_col = None
        for col in ['板块名称', 'name', '行业', '板块']:
            if col in sector_data.columns:
                sector_name_col = col
                break
        
        if sector_name_col:
            for sector in top_sectors[sector_name_col]:
                # 在龙头股中筛选该板块股票
                if '所属板块' in leading_stocks.columns:
                    sector_stocks = leading_stocks[leading_stocks['所属板块'].str.contains(sector, na=False)]
                    if not sector_stocks.empty:
                        # 尝试获取股票代码列
                        code_col = None
                        for col in ['代码', '股票代码', 'symbol']:
                            if col in sector_stocks.columns:
                                code_col = col
                                break
                        
                        if code_col:
                            selected_stocks.extend(sector_stocks[code_col].tolist())
    
    # 去重并限制数量
    return list(set(selected_stocks))[:5]

# 多股分析函数
def analyze_multiple_stocks(stock_list):
    """批量分析多只股票"""
    results = []
    for stock_code in stock_list:
        with st.spinner(f"分析 {stock_code} 中..."):
            stock_data = get_stock_data(
                stock_code,
                (datetime.now() - timedelta(days=180)).strftime("%Y%m%d"),
                datetime.now().strftime("%Y%m%d")
            )
            
            if stock_data is not None and not stock_data.empty:
                analysis_data = enhanced_analyze_stock(stock_data.copy())
                sector_data = st.session_state.get('sector_data', None)
                leading_stocks = st.session_state.get('leading_stocks', None)
                
                if analysis_data is not None:
                    trade_recommendation = generate_trade_recommendation(
                        analysis_data, sector_data, leading_stocks
                    )
                    results.append({
                        'code': stock_code,
                        'recommendation': trade_recommendation,
                        'last_close': analysis_data.iloc[-1]['close'] if analysis_data is not None else 0
                    })
    
    # 按推荐强度排序
    return sorted(results, key=lambda x: (
        0 if "强烈买入" in x['recommendation'] else 
        1 if "谨慎买入" in x['recommendation'] else 
        2 if "持有观望" in x['recommendation'] else 3
    ))

# 技术指标分析函数
def enhanced_analyze_stock(df):
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
        
        # 标记金叉死叉
        df['GoldenCross'] = (df['MACD'] > df['Signal']) & (df['MACD'].shift(1) < df['Signal'].shift(1))
        df['DeathCross'] = (df['MACD'] < df['Signal']) & (df['MACD'].shift(1) > df['Signal'].shift(1))
        
        return df.dropna()
    except Exception as e:
        st.error(f"技术分析失败: {str(e)}")
        return None

# 市场全景分析
def market_overview_analysis():
    """生成市场全景报告"""
    report = "## 📊 市场全景分析\n\n"
    
    # 1. 板块资金分析
    with st.spinner("获取板块资金流向..."):
        sector_data = get_sector_fund_flow()
    
    if sector_data is not None and not sector_data.empty:
        report += "### 板块资金流向\n"
        report += "| 板块 | 净流入(亿) | 涨跌幅 |\n|------|------------|--------|\n"
        
        # 尝试获取列名
        amount_col = '净额'
        sector_name_col = '板块名称'
        change_col = '涨跌幅'
        
        # 如果没有找到列名，使用默认值
        if amount_col not in sector_data.columns:
            amount_col = sector_data.columns[1] if len(sector_data.columns) > 1 else 'unknown'
        if sector_name_col not in sector_data.columns:
            sector_name_col = sector_data.columns[0]
        if change_col not in sector_data.columns:
            change_col = sector_data.columns[2] if len(sector_data.columns) > 2 else 'unknown'
        
        for _, row in sector_data.head(5).iterrows():
            sector_name = row[sector_name_col]
            amount = row.get(amount_col, 0)
            change = row.get(change_col, "0%")
            
            # 金额转换为亿
            if isinstance(amount, (int, float)):
                amount = amount / 100000000
            
            report += f"| {sector_name} | {amount:.2f} | {change} |\n"
    
    # 2. 龙头股分析
    with st.spinner("获取龙头股信息..."):
        leading_stocks = get_leading_stocks()
    
    if leading_stocks is not None and not leading_stocks.empty:
        report += "\n###  今日龙头股\n"
        report += "| 股票 | 名称 | 涨跌幅 | 所属板块 |\n|------|------|--------|----------|\n"
        
        # 尝试获取列名
        code_col = '代码'
        name_col = '名称'
        change_col = '涨跌幅'
        sector_col = '所属板块'
        
        # 列名备选方案
        if code_col not in leading_stocks.columns:
            code_col = leading_stocks.columns[0]
        if name_col not in leading_stocks.columns:
            name_col = leading_stocks.columns[1] if len(leading_stocks.columns) > 1 else 'unknown'
        if change_col not in leading_stocks.columns:
            change_col = leading_stocks.columns[2] if len(leading_stocks.columns) > 2 else 'unknown'
        if sector_col not in leading_stocks.columns:
            sector_col = leading_stocks.columns[3] if len(leading_stocks.columns) > 3 else 'unknown'
        
        for _, row in leading_stocks.head(5).iterrows():
            code = row[code_col]
            name = row[name_col]
            change = row[change_col]
            sector = row[sector_col] if sector_col in row else ""
            
            report += f"| {code} | {name} | {change} | {sector} |\n"
    
    # 3. 选股建议
    if sector_data is not None and leading_stocks is not None:
        selected_stocks = stock_selection_engine(sector_data, leading_stocks)
        if selected_stocks:
            report += f"\n### 💡 智能选股推荐\n"
            report += f"根据板块资金和龙头股表现，推荐关注以下股票：\n"
            report += f"- {', '.join(selected_stocks)}\n"
            report += f"\n点击右侧按钮进行详细分析 →"
    
    return report

# 高级AI分析函数
def advanced_ai_analysis(stock_data, sector_data, leading_stocks, user_query):
    api_url = "https://api.deepseek.com/v1/chat/completions"
    
    if not DEEPSEEK_API_KEY:
        return "错误：缺少DeepSeek API密钥"
    
    # 准备数据摘要
    data_summary = "" if stock_data is None else f"""
    股票技术数据:
    {stock_data[['date', 'close', 'MA5', 'MA20', 'MACD']].tail(3).to_string()}
    """
    
    if sector_data is not None:
        data_summary += f"""
        板块资金流向:
        {sector_data.head(3).to_string()}
        """
    
    if leading_stocks is not None:
        data_summary += f"""
        龙头股表现:
        {leading_stocks.head(3).to_string()}
        """
    
    # 准备请求数据
    prompt = f"""
    作为专业股票分析师，请基于以下市场数据和用户查询进行综合分析：
    
    {data_summary}
    
    用户查询: {user_query}
    
    请从以下维度全面分析：
    1. 宏观市场：当前市场趋势、资金流向、热点板块
    2. 技术分析：关键指标解读（MACD、均线系统）
    3. 资金动向：主力资金流向、北向资金动态
    4. 热点追踪：涨停板数量、龙头股表现
    5. 操作策略：具体买卖点建议和仓位管理
    
    要求：专业严谨但易于理解，给出明确结论。
    """
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是资深股票分析师，精通技术分析、资金流向和市场情绪把握。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    try:
        response = robust_request(
            url=api_url, 
            method='post', 
            json=payload, 
            headers=headers
        )
        
        if response and response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return "AI分析请求失败"
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
    st.caption(f"最后更新: {current_time} | 实时市场分析")
    
    # 初始化session state
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []
    
    if 'stock_data' not in st.session_state:
        st.session_state.stock_data = None
    
    # 侧边栏设置
    with st.sidebar:
        st.header("智能选股设置")
        
        # 代理设置
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
        
        st.divider()
        
        # 市场数据获取
        st.subheader("市场数据")
        if st.button("📊 刷新市场数据"):
            with st.spinner("获取最新市场数据中..."):
                st.session_state.sector_data = get_sector_fund_flow()
                st.session_state.leading_stocks = get_leading_stocks()
                st.success("市场数据已更新！")
        
        st.divider()
        
        # 自选股管理
        st.subheader("自选股管理")
        new_stock = st.text_input("添加股票代码", "000001")
        if st.button("➕ 添加到自选"):
            if new_stock and new_stock not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_stock)
                st.success(f"已添加 {new_stock} 到自选股")
        
        if st.session_state.watchlist:
            st.write("自选股列表:")
            for stock in st.session_state.watchlist:
                st.code(stock)
            
            if st.button("🔍 分析全部自选股"):
                st.session_state.multianalysis = True
                st.session_state.stocks_to_analyze = st.session_state.watchlist.copy()
    
    # 主界面
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # 市场全景分析
        if st.button("🌐 市场全景分析", use_container_width=True):
            market_report = market_overview_analysis()
            st.markdown(market_report)
            
            # 显示选股结果
            if 'sector_data' in st.session_state and 'leading_stocks' in st.session_state:
                selected_stocks = stock_selection_engine(
                    st.session_state.sector_data, 
                    st.session_state.leading_stocks
                )
                
                if selected_stocks:
                    st.subheader("📈 智能选股结果")
                    if st.button("分析推荐股票", type="primary"):
                        st.session_state.multianalysis = True
                        st.session_state.stocks_to_analyze = selected_stocks
        
        # 多股分析展示
        if hasattr(st.session_state, 'multianalysis') and st.session_state.multianalysis:
            if hasattr(st.session_state, 'stocks_to_analyze'):
                results = analyze_multiple_stocks(st.session_state.stocks_to_analyze)
                
                st.subheader("📊 多股分析结果")
                for stock in results:
                    with st.expander(f"{stock['code']} - {stock['recommendation'].split(':')[0]}"):
                        st.write(stock['recommendation'])
                        st.write(f"最新价: {stock['last_close']}")
                        
                        if st.button(f"详细分析 {stock['code']}"):
                            st.session_state.current_stock = stock['code']
                            st.session_state.multianalysis = False
                            st.experimental_rerun()
    
    with col2:
        st.subheader("实时市场状态")
        
        # 实时显示板块资金
        if 'sector_data' in st.session_state and st.session_state.sector_data is not None:
            st.write("**🔥 资金流入板块**")
            for i, row in st.session_state.sector_data.head(3).iterrows():
                sector_name = row.iloc[0]
                amount = row.get('净额', 0)
                if isinstance(amount, (int, float)):
                    amount = f"{amount/100000000:.2f}亿"
                st.info(f"{sector_name}: {amount}")
        
        # 实时显示龙头股
        if 'leading_stocks' in st.session_state and st.session_state.leading_stocks is not None:
            st.write("**🚀 今日龙头股**")
            for i, row in st.session_state.leading_stocks.head(3).iterrows():
                code = row.iloc[0]
                name = row.iloc[1] if len(row) > 1 else ""
                change = row.iloc[2] if len(row) > 2 else ""
                st.success(f"{code} {name}: {change}")
    
    # 聊天交互区域
    st.divider()
    st.subheader("💬 智能选股助手")
    
    # 显示历史消息
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # 用户输入处理
    if prompt := st.chat_input("请输入股票代码或分析指令..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        response = ""
        stock_pattern = r'(\d{6})'
        matches = re.findall(stock_pattern, prompt)
        
        if matches:
            stock_code = matches[0]
            st.session_state.current_stock = stock_code
            response = f"已选择股票 {stock_code}，正在分析中..."
        elif "选股" in prompt or "推荐" in prompt:
            # 执行选股逻辑
            with st.spinner("执行智能选股策略中..."):
                st.session_state.sector_data = get_sector_fund_flow()
                st.session_state.leading_stocks = get_leading_stocks()
                
                if st.session_state.sector_data is not None and st.session_state.leading_stocks is not None:
                    selected_stocks = stock_selection_engine(
                        st.session_state.sector_data, 
                        st.session_state.leading_stocks
                    )
                    
                    if selected_stocks:
                        response = f"智能选股结果: {', '.join(selected_stocks)}\n\n点击下方按钮进行详细分析"
                        st.session_state.multianalysis = True
                        st.session_state.stocks_to_analyze = selected_stocks
                    else:
                        response = "选股策略未找到合适股票"
                else:
                    response = "获取市场数据失败，无法选股"
        elif "行情" in prompt or "市场" in prompt:
            response = "正在生成市场全景分析..."
        else:
            response = "正在处理您的请求..."
        
        with st.chat_message("assistant"):
            st.markdown(response)
            
            # 如果有当前股票，进行分析
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
                        
                        trade_recommendation = generate_trade_recommendation(
                            analysis_data, sector_data, leading_stocks
                        )
                        
                        with st.spinner("AI深度分析中..."):
                            ai_analysis = advanced_ai_analysis(
                                analysis_data, 
                                sector_data, 
                                leading_stocks, 
                                f"请分析股票{st.session_state.current_stock}的投资机会"
                            )
                        
                        # 显示结果
                        full_response = f"## {st.session_state.current_stock} 深度分析\n\n"
                        full_response += f"###  💡 操作建议\n{trade_recommendation}\n\n"
                        full_response += f"###  🤖 AI专业分析\n{ai_analysis}\n\n"
                        
                        st.markdown(full_response)
        
        st.session_state.messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()
