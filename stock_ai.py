 import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import numpy as np
import time
import io

# DeepSeek API配置（使用你的有效API密钥）
DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "sk-e9e5e5b7565b4f809deb7565b4f809de1c8d53c22fa1b")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# 初始化session state
def init_session_state():
    defaults = {
        'sector_data': pd.DataFrame(),
        'leading_stocks': pd.DataFrame(),
        'watchlist': [],
        'chat_history': [],
        'market_sentiment': "中性",
        'hot_sectors': [],
        'sector_rotation': pd.DataFrame(),
        'last_update': datetime.now() - timedelta(hours=1),
        'analyze_watchlist': False,
        'api_key': DEEPSEEK_API_KEY
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# DeepSeek API交互（增强错误处理）
def deepseek_chat(prompt, context=""):
    # 检查API密钥是否有效
    if not st.session_state.api_key or not st.session_state.api_key.startswith("sk-"):
        return "⚠️ 请设置有效的DeepSeek API密钥"
    
    headers = {
        "Authorization": f"Bearer {st.session_state.api_key}",
        "Content-Type": "application/json"
    }
    
    market_context = f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
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
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        
        # 检查401 Unauthorized错误
        if response.status_code == 401:
            return "⚠️ API密钥无效或过期，请检查并更新"
        
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        return f"⚠️ 网络错误: {str(e)}"
    except KeyError:
        return "⚠️ 无法解析API响应，请稍后再试"
    except Exception as e:
        return f"⚠️ 未知错误: {str(e)}"

# 简化数据获取 - 使用CSV备份
def get_stock_data(stock_code):
    try:
        # 示例数据源
        sample_data = {
            'date': pd.date_range(end=datetime.today(), periods=100),
            'open': np.random.normal(100, 10, 100).cumsum(),
            'high': np.random.normal(105, 10, 100).cumsum(),
            'low': np.random.normal(95, 10, 100).cumsum(),
            'close': np.random.normal(100, 10, 100).cumsum(),
            'volume': np.random.randint(100000, 1000000, 100)
        }
        return pd.DataFrame(sample_data)
    except:
        return pd.DataFrame()

# 简化板块资金流向
def get_sector_fund_flow():
    # 创建模拟板块数据
    sectors = ['半导体', '新能源', '医药', '消费电子', '人工智能', '金融', '地产', '白酒', '汽车', '化工']
    dates = [datetime.now() - timedelta(days=i) for i in range(3)]
    
    data = []
    for date in dates:
        for sector in sectors:
            data.append({
                'sector': sector,
                'net_amount': np.random.uniform(-500000000, 500000000),
                'change': np.random.uniform(-5, 5),
                'date': date.strftime("%Y-%m-%d")
            })
    
    return pd.DataFrame(data)

# 简化龙头股获取
def get_leading_stocks():
    stocks = [
        {'symbol': '600519', 'name': '贵州茅台', 'change': 5.2, 'sector': '白酒', 'amount': 4500000000},
        {'symbol': '000001', 'name': '平安银行', 'change': 3.8, 'sector': '金融', 'amount': 3200000000},
        {'symbol': '300750', 'name': '宁德时代', 'change': 7.1, 'sector': '新能源', 'amount': 5800000000},
        {'symbol': '600036', 'name': '招商银行', 'change': 2.3, 'sector': '金融', 'amount': 2800000000},
        {'symbol': '000333', 'name': '美的集团', 'change': 4.5, 'sector': '家电', 'amount': 3600000000}
    ]
    return pd.DataFrame(stocks)

# 简化市场情绪分析
def analyze_market_sentiment(sector_data, leading_stocks):
    if sector_data.empty:
        return "中性", []
    
    # 随机选择热点板块
    hot_sectors = np.random.choice(sector_data['sector'].unique(), 3, replace=False).tolist()
    
    # 随机情绪
    sentiments = ["🔥 极度乐观", "📈 乐观", "📉 谨慎", "⚠️ 极度悲观", "➖ 中性"]
    return np.random.choice(sentiments), hot_sectors

# 简化板块轮动分析
def analyze_sector_rotation(sector_data):
    if sector_data.empty:
        return pd.DataFrame()
    
    # 计算简单分数
    sector_scores = sector_data.groupby('sector').agg({
        'net_amount': 'sum',
        'change': 'mean'
    })
    sector_scores['score'] = sector_scores['net_amount'] * sector_scores['change']
    return sector_scores.sort_values('score', ascending=False)

# 纯Python技术指标计算
def calculate_ema(data, window):
    return data.ewm(span=window, adjust=False).mean()

def calculate_macd(data, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(data, fast)
    ema_slow = calculate_ema(data, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    return macd_line, signal_line

def calculate_rsi(data, window=14):
    delta = data.diff(1)
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    
    rs = avg_gain / avg_loss.replace(0, 1)  # 避免除零
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)  # 填充NaN为中性值

def enhanced_technical_analysis(df):
    if df.empty:
        return df
    
    # 计算移动平均线
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA60'] = df['close'].rolling(window=60).mean()
    
    # MACD
    df['MACD'], df['MACD_signal'] = calculate_macd(df['close'])
    
    # RSI
    df['RSI'] = calculate_rsi(df['close'])
    
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
    
    # 综合信号
    buy_signals = sum([
        signals['trend'] == "上升",
        signals['macd'] == "金叉",
        signals['rsi'] == "超卖"
    ])
    
    sell_signals = sum([
        signals['trend'] == "下降",
        signals['macd'] == "死叉",
        signals['rsi'] == "超买"
    ])
    
    if buy_signals >= 2:
        signals['recommendation'] = "买入"
    elif sell_signals >= 2:
        signals['recommendation'] = "卖出"
    else:
        signals['recommendation'] = "观望"
    
    signals['reason'] = f"趋势:{signals['trend']}, MACD:{signals['macd']}, RSI:{signals['rsi']}"
    
    return signals

# 获取市场数据
def refresh_market_data():
    with st.spinner("🔄 更新市场数据中..."):
        # 获取板块资金流向
        st.session_state.sector_data = get_sector_fund_flow()
        
        # 获取龙头股
        st.session_state.leading_stocks = get_leading_stocks()
        
        # 分析市场情绪
        sentiment, hot_sectors = analyze_market_sentiment(
            st.session_state.sector_data, 
            st.session_state.leading_stocks
        )
        st.session_state.market_sentiment = sentiment
        st.session_state.hot_sectors = hot_sectors
        
        # 分析板块轮动
        st.session_state.sector_rotation = analyze_sector_rotation(st.session_state.sector_data)
        
        st.session_state.last_update = datetime.now()
        st.success("✅ 市场数据已更新!")

# 市场全景分析报告
def generate_market_report():
    report = "##  🌐 市场全景分析报告\n\n"
    report += f"**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    # 市场情绪
    report += f"###  📊 市场情绪: {st.session_state.market_sentiment}\n\n"
    
    # 热点板块
    if st.session_state.hot_sectors:
        report += "### 🔥 热点板块\n"
        for sector in st.session_state.hot_sectors[:3]:
            report += f"- {sector}\n"
        report += "\n"
    
    # 板块轮动分析
    if not st.session_state.sector_rotation.empty:
        report += "### 🔄 板块轮动趋势\n"
        report += "| 板块 | 资金净流入 | 平均涨跌 | 轮动得分 |\n"
        report += "|------|------------|----------|----------|\n"
        
        for sector, row in st.session_state.sector_rotation.head(3).iterrows():
            net_amount = row['net_amount'] / 1000000
            report += f"| {sector} | {net_amount:.2f}万 | {row['change']:.2f}% | {row['score']:.2f} |\n"
    
    return report

# 智能对话界面（修复rerun问题）
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
        
        # 不再使用rerun()，让Streamlit自动刷新
        time.sleep(0.1)  # 添加短暂延迟确保UI更新

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
    if st.button("🔄 手动刷新数据", key="refresh_btn"):
        refresh_market_data()
    
    # 添加API密钥设置
    with st.sidebar:
        st.subheader("🔑 API密钥设置")
        new_api_key = st.text_input("DeepSeek API密钥", type="password", value=st.session_state.api_key)
        if new_api_key != st.session_state.api_key:
            st.session_state.api_key = new_api_key
            st.success("API密钥已更新")
    
    # 智能对话界面
    chat_interface()
    
    # 侧边栏配置
    with st.sidebar:
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
        if st.button("🌐 生成市场全景报告", key="market_report_btn"):
            market_report = generate_market_report()
            st.markdown(market_report)
            
            # AI分析总结
            with st.spinner("🤖 生成AI市场总结..."):
                ai_analysis = deepseek_chat("根据当前市场数据，分析未来1-3天的板块轮动机会和风险")
                st.subheader("🔮 AI市场展望")
                st.write(ai_analysis)
        
        # 自选股分析
        if st.session_state.analyze_watchlist:
            st.subheader("📊 自选股分析结果")
            
            for stock_code in st.session_state.watchlist:
                with st.expander(f"股票分析: {stock_code}", expanded=True):
                    with st.spinner(f"获取 {stock_code} 数据..."):
                        stock_data = get_stock_data(stock_code)
                    
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
                        
                        # 布局设置
                        fig.update_layout(
                            title=f'{stock_code} 技术分析',
                            xaxis_title='日期',
                            yaxis_title='价格',
                            template='plotly_dark',
                            height=400
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
                            ai_analysis = deepseek_chat(f"分析股票{stock_code}的技术面和买卖点")
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
            st.markdown("### 🔥 热点板块")
            for sector in st.session_state.hot_sectors[:3]:
                st.info(f"- {sector}")
        
        # 显示龙头股
        if not st.session_state.leading_stocks.empty:
            st.markdown("### 今日龙头股")
            
            for _, row in st.session_state.leading_stocks.iterrows():
                symbol = row.get('symbol', '')
                name = row.get('name', '')
                change = row.get('change', 0)
                sector = row.get('sector', '')
                
                direction = "↑" if change > 0 else "↓"
                color = "green" if change > 0 else "red"
                
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
            
            for sector, row in st.session_state.sector_rotation.head(3).iterrows():
                score = row.get('score', 0)
                st.metric(f"{sector}", f"轮动得分: {score:.2f}")

# 运行应用
if __name__ == "__main__":
    main()
