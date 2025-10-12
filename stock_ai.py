import pandas as pd
import akshare as ak
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import json
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import talib
import time

# DeepSeek API配置 - 使用您提供的密钥
DEEPSEEK_API_KEY = "sk-e9e5e5b7565b4f809deb7565b4f809de1c8d53c22fa1b"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# 初始化session state
def init_session_state():
    if 'sector_data' not in st.session_state:
        st.session_state.sector_data = pd.DataFrame()
    if 'leading_stocks' not in st.session_state:
        st.session_state.leading_stocks = pd.DataFrame()
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'market_sentiment' not in st.session_state:
        st.session_state.market_sentiment = "中性"
    if 'hot_sectors' not in st.session_state:
        st.session_state.hot_sectors = []
    if 'sector_rotation' not in st.session_state:
        st.session_state.sector_rotation = pd.DataFrame()
    if 'last_update' not in st.session_state:
        st.session_state.last_update = datetime.now() - timedelta(hours=1)

# DeepSeek API交互
def deepseek_chat(prompt, context=""):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 构建市场上下文
    market_context = f"""
    ## 当前市场状态
    - 时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    - 市场情绪: {st.session_state.market_sentiment}
    - 热点板块: {", ".join(st.session_state.hot_sectors[:3]) if st.session_state.hot_sectors else "暂无"}
    - 自选股: {", ".join(st.session_state.watchlist) if st.session_state.watchlist else "无"}
    """
    
    messages = [
        {"role": "system", "content": "你是一位专业的A股量化分析师，擅长技术分析、板块轮动预测和短线交易策略。"},
        {"role": "user", "content": f"{market_context}\n\n{context}\n\n用户问题: {prompt}"}
    ]
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        return f"⚠️ 智能分析请求失败: {str(e)}\n请稍后再试或检查API密钥"

# 增强型数据获取
def get_stock_data(stock_code, start_date, end_date):
    try:
        df = ak.stock_zh_a_hist(
            symbol=stock_code, 
            period="daily", 
            start_date=start_date, 
            end_date=end_date, 
            adjust="qfq"
        )
        
        if not df.empty:
            # 列名标准化
            col_map = {'日期': 'date', '开盘': 'open', '收盘': 'close', 
                      '最高': 'high', '最低': 'low', '成交量': 'volume', '成交额': 'amount'}
            df = df.rename(columns=col_map)
            df['date'] = pd.to_datetime(df['date'])
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# 板块资金流向
def get_sector_fund_flow(days=3):
    try:
        all_data = []
        today = datetime.now()
        
        for i in range(days):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            df = ak.stock_sector_fund_flow_rank(indicator=date_str)
            if not df.empty:
                df['日期'] = date_str
                all_data.append(df)
        
        if not all_data:
            return pd.DataFrame()
        
        full_df = pd.concat(all_data)
        # 列名标准化
        col_map = {'板块名称': 'sector', '主力净流入-净额': 'net_amount', '涨跌幅': 'change'}
        full_df = full_df.rename(columns=col_map)
        
        # 数据转换
        full_df['net_amount'] = pd.to_numeric(full_df['net_amount'], errors='coerce')
        full_df['change'] = full_df['change'].str.replace('%', '').astype(float)
        
        return full_df
    except:
        return pd.DataFrame()

# 龙头股获取
def get_leading_stocks():
    try:
        date_str = datetime.now().strftime("%Y%m%d")
        df = ak.stock_zt_pool_em(date=date_str)
        if not df.empty:
            # 列名标准化
            col_map = {'代码': 'symbol', '名称': 'name', '涨跌幅': 'change', 
                      '所属板块': 'sector', '连续涨停天数': 'limit_days', '成交额': 'amount'}
            df = df.rename(columns=col_map)
            
            # 数据转换
            df['change'] = df['change'].str.replace('%', '').astype(float)
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            return df.sort_values("change", ascending=False).head(20)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# 市场情绪分析
def analyze_market_sentiment(sector_data, leading_stocks):
    if sector_data.empty or leading_stocks.empty:
        return "中性", []
    
    # 板块资金分析
    sector_analysis = sector_data.groupby('sector')['net_amount'].sum().nlargest(5)
    hot_sectors = sector_analysis.index.tolist()
    
    # 龙头股分析
    leading_stocks['strength'] = leading_stocks['change'] * np.log1p(leading_stocks['amount'])
    top_stocks = leading_stocks.nlargest(10, 'strength')
    
    # 情绪判断
    total_inflow = sector_data['net_amount'].sum()
    avg_change = leading_stocks['change'].mean()
    
    if total_inflow > 1000000000 and avg_change > 5:
        sentiment = "🔥 极度乐观"
    elif total_inflow > 500000000 and avg_change > 3:
        sentiment = "📈 乐观"
    elif total_inflow < -500000000 and avg_change < -3:
        sentiment = "📉 谨慎"
    elif total_inflow < -1000000000 and avg_change < -5:
        sentiment = "⚠️ 极度悲观"
    else:
        sentiment = "➖ 中性"
    
    return sentiment, hot_sectors

# 板块轮动分析
def analyze_sector_rotation(sector_data):
    if sector_data.empty:
        return pd.DataFrame()
    
    # 计算板块资金变化
    pivot_df = sector_data.pivot_table(
        index='sector', 
        columns='日期', 
        values='net_amount', 
        aggfunc='sum'
    ).fillna(0)
    
    # 计算变化趋势
    if len(pivot_df.columns) > 1:
        pivot_df['trend'] = pivot_df.iloc[:, -1] - pivot_df.iloc[:, 0]
        pivot_df['momentum'] = pivot_df.iloc[:, -1] / pivot_df.iloc[:, 0].abs().replace(0, 1)
        pivot_df['score'] = pivot_df['trend'] * pivot_df['momentum']
    
    return pivot_df.sort_values('score', ascending=False) if 'score' in pivot_df.columns else pivot_df

# 增强型技术分析
def enhanced_technical_analysis(df):
    if df.empty:
        return df
    
    # 计算技术指标
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA60'] = df['close'].rolling(window=60).mean()
    
    # MACD
    df['MACD'], df['MACD_signal'], _ = talib.MACD(df['close'])
    
    # RSI
    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
    
    # Bollinger Bands
    df['upper_band'], df['middle_band'], df['lower_band'] = talib.BBANDS(df['close'], timeperiod=20)
    
    # 成交量指标
    df['VOL_MA5'] = df['volume'].rolling(window=5).mean()
    
    return df.dropna()

# 生成交易信号
def generate_trade_signals(df):
    if df.empty:
        return {}
    
    signals = {}
    latest = df.iloc[-1]
    
    # 趋势信号
    signals['trend'] = "上升" if latest['close'] > latest['MA20'] > latest['MA60'] else "下降"
    
    # MACD信号
    signals['macd'] = "金叉" if latest['MACD'] > latest['MACD_signal'] else "死叉"
    
    # RSI信号
    if latest['RSI'] > 70:
        signals['rsi'] = "超买"
    elif latest['RSI'] < 30:
        signals['rsi'] = "超卖"
    else:
        signals['rsi'] = "中性"
    
    # 布林带信号
    if latest['close'] > latest['upper_band']:
        signals['boll'] = "上轨突破"
    elif latest['close'] < latest['lower_band']:
        signals['boll'] = "下轨突破"
    else:
        signals['boll'] = "区间内"
    
    # 综合信号
    buy_signals = 0
    sell_signals = 0
    
    if signals['trend'] == "上升": buy_signals += 1
    if signals['macd'] == "金叉": buy_signals += 1
    if signals['rsi'] == "超卖": buy_signals += 1
    if signals['boll'] == "下轨突破": buy_signals += 1
    
    if signals['trend'] == "下降": sell_signals += 1
    if signals['macd'] == "死叉": sell_signals += 1
    if signals['rsi'] == "超买": sell_signals += 1
    if signals['boll'] == "上轨突破": sell_signals += 1
    
    if buy_signals >= 3:
        signals['recommendation'] = "强力买入"
    elif buy_signals >= 2:
        signals['recommendation'] = "买入"
    elif sell_signals >= 3:
        signals['recommendation'] = "卖出"
    elif sell_signals >= 2:
        signals['recommendation'] = "谨慎持有"
    else:
        signals['recommendation'] = "观望"
    
    signals['reason'] = f"趋势:{signals['trend']}, MACD:{signals['macd']}, RSI:{signals['rsi']}, 布林带:{signals['boll']}"
    
    return signals

# 获取市场数据
def refresh_market_data():
    with st.spinner("🔄 更新市场数据中..."):
        # 获取板块资金流向
        st.session_state.sector_data = get_sector_fund_flow(days=3)
        
        # 获取龙头股
        st.session_state.leading_stocks = get_leading_stocks()
        
        # 分析市场情绪
        if not st.session_state.sector_data.empty and not st.session_state.leading_stocks.empty:
            sentiment, hot_sectors = analyze_market_sentiment(
                st.session_state.sector_data, 
                st.session_state.leading_stocks
            )
            st.session_state.market_sentiment = sentiment
            st.session_state.hot_sectors = hot_sectors
        
        # 分析板块轮动
        if not st.session_state.sector_data.empty:
            st.session_state.sector_rotation = analyze_sector_rotation(st.session_state.sector_data)
        
        st.session_state.last_update = datetime.now()
        st.success("✅ 市场数据已更新!")

# 市场全景分析报告
def generate_market_report():
    report = "## 🌐 市场全景分析报告\n\n"
    report += f"**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    # 市场情绪
    report += f"### 📊 市场情绪: {st.session_state.market_sentiment}\n\n"
    
    # 热点板块
    if st.session_state.hot_sectors:
        report += "###  🔥 热点板块\n"
        for sector in st.session_state.hot_sectors[:5]:
            report += f"- {sector}\n"
        report += "\n"
    
    # 板块轮动分析
    if not st.session_state.sector_rotation.empty:
        report += "###  🔄 板块轮动趋势\n"
        report += "| 板块 | 资金趋势 | 动量 | 轮动得分 |\n"
        report += "|------|----------|------|----------|\n"
        
        for idx, row in st.session_state.sector_rotation.head(5).iterrows():
            trend = row.get('trend', 0) / 100000000
            momentum = row.get('momentum', 0)
            score = row.get('score', 0) / 100000000
            
            report += f"| {idx} | {trend:.2f}亿 | {momentum:.2f} | {score:.2f} |\n"
    
    return report

# 智能对话界面
def chat_interface():
    st.sidebar.subheader("💬 智能投顾")
    
    # 显示聊天历史
    for message in st.session_state.chat_history:
        with st.sidebar.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # 用户输入
    user_input = st.sidebar.chat_input("输入股票问题...")
    
    if user_input:
        # 添加用户消息到历史
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        
        # 准备上下文
        context = f"""
        当前自选股: {", ".join(st.session_state.watchlist) if st.session_state.watchlist else "无"}
        热点板块: {", ".join(st.session_state.hot_sectors[:3]) if st.session_state.hot_sectors else "暂无"}
        市场情绪: {st.session_state.market_sentiment}
        """
        
        # 获取AI回复
        with st.spinner("🤔 思考中..."):
            ai_response = deepseek_chat(user_input, context)
        
        # 添加AI回复到历史
        st.session_state.chat_history.append({"role": "assistant", "content": ai_response})
        
        # 重新渲染聊天界面
        st.experimental_rerun()

# 主应用
def main():
    st.set_page_config(
        page_title="DeepSeek智能选股系统", 
        page_icon="📈", 
        layout="wide"
    )
    
    # 初始化session state
    init_session_state()
    
    # 页面标题
    st.title("🚀 DeepSeek智能选股系统")
    st.caption(f"最后更新: {st.session_state.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 自动刷新数据（每10分钟或手动刷新）
    if (datetime.now() - st.session_state.last_update).seconds > 600:
        refresh_market_data()
    
    # 智能对话界面
    chat_interface()
    
    # 侧边栏配置
    with st.sidebar:
        st.divider()
        
        # 市场数据刷新
        if st.button("🔄 刷新市场数据", use_container_width=True):
            refresh_market_data()
        
        st.divider()
        
        # 自选股管理
        st.subheader("自选股管理")
        new_stock = st.text_input("添加股票代码(6位数字)", "600519")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 添加", use_container_width=True):
                if new_stock and new_stock not in st.session_state.watchlist:
                    st.session_state.watchlist.append(new_stock)
                    st.success(f"已添加 {new_stock}")
        with col2:
            if st.button("🗑️ 清空", use_container_width=True):
                st.session_state.watchlist = []
                st.success("已清空自选股")
        
        if st.session_state.watchlist:
            st.write("**自选股列表**")
            for stock in st.session_state.watchlist:
                st.code(stock)
            
            if st.button("🔍 分析全部自选股", use_container_width=True):
                st.session_state.analyze_watchlist = True
    
    # 主界面布局
    col1, col2 = st.columns([7, 3])
    
    with col1:
        # 市场全景分析
        if st.button("🌐 生成市场全景报告", use_container_width=True):
            market_report = generate_market_report()
            st.markdown(market_report)
            
            # AI分析总结
            with st.spinner("🤖 生成AI市场总结..."):
                prompt = "根据当前市场数据，分析未来1-3天的板块轮动机会和风险"
                ai_analysis = deepseek_chat(prompt)
                st.subheader("🔮 AI市场展望")
                st.write(ai_analysis)
        
        # 自选股分析
        if hasattr(st.session_state, 'analyze_watchlist') and st.session_state.analyze_watchlist:
            st.subheader("📊 自选股分析结果")
            
            for stock_code in st.session_state.watchlist:
                with st.expander(f"股票分析: {stock_code}", expanded=True):
                    with st.spinner(f"获取 {stock_code} 数据..."):
                        stock_data = get_stock_data(
                            stock_code,
                            (datetime.now() - timedelta(days=180)).strftime("%Y%m%d"),
                            datetime.now().strftime("%Y%m%d")
                        )
                    
                    if not stock_data.empty:
                        # 技术分析
                        with st.spinner("技术分析中..."):
                            analysis_data = enhanced_technical_analysis(stock_data.copy())
                            signals = generate_trade_signals(analysis_data)
                        
                        # 绘制价格图表
                        fig = go.Figure()
                        
                        # K线图
                        fig.add_trace(go.Candlestick(
                            x=analysis_data['date'],
                            open=analysis_data['open'],
                            high=analysis_data['high'],
                            low=analysis_data['low'],
                            close=analysis_data['close'],
                            name='K线'
                        ))
                        
                        # 移动平均线
                        fig.add_trace(go.Scatter(
                            x=analysis_data['date'], 
                            y=analysis_data['MA20'], 
                            name='20日均线',
                            line=dict(color='blue', width=1)
                        ))
                        
                        fig.add_trace(go.Scatter(
                            x=analysis_data['date'], 
                            y=analysis_data['MA60'], 
                            name='60日均线',
                            line=dict(color='green', width=1)
                        ))
                        
                        # 布林带
                        fig.add_trace(go.Scatter(
                            x=analysis_data['date'], 
                            y=analysis_data['upper_band'], 
                            name='上轨',
                            line=dict(color='gray', width=1, dash='dot')
                        ))
                        
                        fig.add_trace(go.Scatter(
                            x=analysis_data['date'], 
                            y=analysis_data['lower_band'], 
                            name='下轨',
                            line=dict(color='gray', width=1, dash='dot')
                        ))
                        
                        # 布局设置
                        fig.update_layout(
                            title=f'{stock_code} 技术分析',
                            xaxis_title='日期',
                            yaxis_title='价格',
                            template='plotly_dark',
                            height=500
                        )
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # 显示交易信号
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            st.metric("操作建议", signals['recommendation'])
                        with col2:
                            st.caption(f"理由: {signals['reason']}")
                        
                        # AI分析
                        with st.spinner("🤖 生成AI分析报告..."):
                            prompt = f"分析股票{stock_code}的技术面和买卖点，当前价格{analysis_data.iloc[-1]['close']}，给出具体操作建议"
                            ai_analysis = deepseek_chat(prompt)
                            st.subheader("💡 AI专业分析")
                            st.write(ai_analysis)
                    else:
                        st.warning(f"无法获取 {stock_code} 的数据")
            
            # 重置分析状态
            st.session_state.analyze_watchlist = False
    
    with col2:
        st.subheader("📌 实时市场")
        
        # 显示市场情绪
        st.markdown(f"### 市场情绪\n**{st.session_state.market_sentiment}**")
        
        # 显示热点板块
        if st.session_state.hot_sectors:
            st.markdown("###  🔥 热点板块")
            for sector in st.session_state.hot_sectors[:5]:
                st.info(f"- {sector}")
        
        # 显示龙头股
        if not st.session_state.leading_stocks.empty:
            st.markdown("###  今日龙头股")
            
            # 显示前5只龙头股
            for i, row in st.session_state.leading_stocks.head(5).iterrows():
                symbol = row.get('symbol', '')
                name = row.get('name', '')
                change = row.get('change', 0)
                sector = row.get('sector', '')
                
                direction = "↑" if change > 0 else "↓"
                color = "#00cc00" if change > 0 else "#ff0000"
                
                st.markdown(f"""
                <div style='border-left: 4px solid {color}; padding-left: 10px; margin-bottom: 10px;'>
                    <div style='font-weight: bold;'>{symbol} {name}</div>
                    <div>板块: {sector}</div>
                    <div style='color: {color};'>涨跌: {change:.2f}% {direction}</div>
                </div>
                """, unsafe_allow_html=True)
        
        # 板块轮动排名
        if not st.session_state.sector_rotation.empty:
            st.markdown("###  🔄 板块轮动排名")
            
            # 显示前5名板块
            for idx, row in st.session_state.sector_rotation.head(5).iterrows():
                score = row.get('score', 0) / 100000000
                st.metric(f"{idx}", f"轮动得分: {score:.2f}")

# 运行应用
if __name__ == "__main__":
    main()
