import os
import re
import time
import requests
import pandas as pd
import akshare as ak
import numpy as np
import streamlit as st
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

# 版本检查（部署时验证）
st.sidebar.write(f"akshare版本: {ak.__version__}")
st.sidebar.write(f"plotly版本: {go.__version__}")

# 兼容性处理器
def get_compatible_data(data_source, params, possible_columns):
    """处理AKShare接口兼容性问题"""
    try:
        df = data_source(**params)
        if df is None or df.empty:
            return pd.DataFrame()
        
        # 列名标准化处理
        for standard_name, possible_names in possible_columns.items():
            for name in possible_names:
                if name in df.columns:
                    df = df.rename(columns={name: standard_name})
                    break
        
        return df
    except Exception as e:
        st.error(f"数据获取失败: {str(e)}")
        return pd.DataFrame()

# 数据获取函数
def get_stock_data(stock_code, start_date, end_date):
    """获取股票历史数据"""
    column_map = {
        'date': ['日期', 'date', 'datetime'],
        'open': ['开盘', 'open'],
        'close': ['收盘', 'close'],
        'high': ['最高', 'high'],
        'low': ['最低', 'low'],
        'volume': ['成交量', 'volume', '成交股数']
    }
    
    return get_compatible_data(
        data_source=ak.stock_zh_a_hist,
        params={
            'symbol': stock_code,
            'period': "daily",
            'start_date': start_date,
            'end_date': end_date,
            'adjust': "qfq"
        },
        possible_columns=column_map
    )

def get_sector_fund_flow():
    """获取板块资金流向"""
    column_map = {
        '板块名称': ['板块名称', 'name', '行业', '板块'],
        '净额': ['主力净流入-净额', '净额', '主力净流入', '净流入'],
        '涨跌幅': ['涨跌幅', '涨幅', '最新涨跌幅', 'change']
    }
    
    df = get_compatible_data(
        data_source=ak.stock_sector_fund_flow_rank,
        params={'indicator': "今日"},
        possible_columns=column_map
    )
    
    if not df.empty:
        if '净额' in df.columns:
            df['净额'] = pd.to_numeric(df['净额'], errors='coerce') / 100000000  # 转换为亿
        return df.sort_values("净额", ascending=False).head(10)
    return df

def get_leading_stocks():
    """获取龙头股信息"""
    column_map = {
        '代码': ['代码', 'symbol', '股票代码'],
        '名称': ['名称', 'name', '股票名称'],
        '涨跌幅': ['涨跌幅', '涨幅', '最新涨跌幅', '涨跌', 'change'],
        '所属板块': ['所属板块', '板块', 'industry', '行业']
    }
    
    date_str = datetime.now().strftime("%Y%m%d")
    df = get_compatible_data(
        data_source=ak.stock_zt_pool_em,
        params={'date': date_str},
        possible_columns=column_map
    )
    
    if not df.empty:
        if '涨跌幅' in df.columns:
            df['涨跌幅'] = df['涨跌幅'].apply(lambda x: f"{float(str(x).replace('%', ''))}%" if '%' in str(x) else x)
        return df.head(10)
    return df

# 分析引擎
def technical_analysis(df):
    """技术指标分析"""
    if df is None or df.empty:
        return None
    
    try:
        # 计算移动平均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()
        return df.dropna()
    except Exception as e:
        st.error(f"技术分析失败: {str(e)}")
        return None

def stock_selection_engine(sector_data, leading_stocks):
    """智能选股引擎"""
    selected_stocks = []
    
    if sector_data is not None and not sector_data.empty and leading_stocks is not None:
        # 获取资金流入前三板块
        top_sectors = sector_data.head(3)
        
        sector_name_col = '板块名称'
        if sector_name_col not in top_sectors.columns:
            sector_name_col = top_sectors.columns[0]
        
        for _, row in top_sectors.iterrows():
            sector = row[sector_name_col]
            
            if '所属板块' in leading_stocks.columns:
                sector_stocks = leading_stocks[
                    leading_stocks['所属板块'].str.contains(sector, na=False)
                ]
                
                if not sector_stocks.empty:
                    code_col = '代码'
                    if code_col not in sector_stocks.columns:
                        code_col = sector_stocks.columns[0]
                    
                    selected_stocks.extend(sector_stocks[code_col].tolist())
    
    return list(set(selected_stocks))[:5]  # 去重并取前5只

def market_overview_analysis():
    """市场全景分析报告"""
    report = "## 📊 市场全景分析\n"
    
    # 板块资金流向
    with st.spinner("获取板块资金流向..."):
        sector_data = get_sector_fund_flow()
    
    if sector_data is not None and not sector_data.empty:
        report += "\n### 板块资金流向 (单位:亿元)\n"
        report += "| 板块 | 净流入 | 涨跌幅 |\n|------|--------|--------|\n"
        
        for _, row in sector_data.head(5).iterrows():
            sector_name = row['板块名称'] if '板块名称' in row else row.iloc[0]
            amount = row.get('净额', 0)
            change = row.get('涨跌幅', 'N/A')
            report += f"| {sector_name} | {amount:.2f} | {change} |\n"
    
    # 龙头股信息
    with st.spinner("获取龙头股信息..."):
        leading_stocks = get_leading_stocks()
    
    if leading_stocks is not None and not leading_stocks.empty:
        report += "\n###  今日龙头股\n"
        report += "| 代码 | 名称 | 涨跌幅 | 板块 |\n|------|------|--------|------|\n"
        
        for _, row in leading_stocks.head(5).iterrows():
            code = row['代码'] if '代码' in row else row.iloc[0]
            name = row['名称'] if '名称' in row else row.iloc[1]
            change = row['涨跌幅'] if '涨跌幅' in row else row.iloc[2]
            sector = row['所属板块'] if '所属板块' in row else row.iloc[3] if len(row) > 3 else "N/A"
            report += f"| {code} | {name} | {change} | {sector} |\n"
    
    # 选股推荐
    if sector_data is not None and leading_stocks is not None:
        selected_stocks = stock_selection_engine(sector_data, leading_stocks)
        if selected_stocks:
            report += "\n### 💡 智能选股推荐\n"
            report += "根据板块资金和龙头股表现，推荐关注以下股票：\n"
            report += ", ".join(selected_stocks)
    
    return report

# 主应用
def main():
    global PROXY_SETTINGS
    
    st.set_page_config(
        page_title="智能选股系统", 
        page_icon="📈", 
        layout="wide"
    )
    
    st.title("🚀 智能选股系统")
    st.caption(f"最后更新: {current_time}")
    
    # 初始化session state
    if 'sector_data' not in st.session_state:
        st.session_state.sector_data = None
    
    if 'leading_stocks' not in st.session_state:
        st.session_state.leading_stocks = None
    
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []
    
    # 侧边栏
    with st.sidebar:
        st.header("系统设置")
        
        # 代理设置
        st.subheader("网络配置")
        use_proxy = st.checkbox("启用代理", False)
        proxy_address = st.text_input("代理地址", "http://127.0.0.1:7890")
        
        PROXY_SETTINGS = {'http': proxy_address, 'https': proxy_address} if use_proxy else None
        
        # 市场数据刷新
        st.subheader("数据更新")
        if st.button("🔄 刷新市场数据", use_container_width=True):
            with st.spinner("更新中..."):
                st.session_state.sector_data = get_sector_fund_flow()
                st.session_state.leading_stocks = get_leading_stocks()
                st.success("数据已更新!")
        
        # 自选股管理
        st.subheader("自选股管理")
        new_stock = st.text_input("添加股票代码", "600519")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 添加", use_container_width=True):
                if new_stock and new_stock not in st.session_state.watchlist:
                    st.session_state.watchlist.append(new_stock)
                    st.success(f"已添加 {new_stock}")
        with col2:
            if st.button("🗑️ 清空", use_container_width=True):
                st.session_state.watchlist = []
                st.success("已清空")
        
        if st.session_state.watchlist:
            st.write("**自选股列表**")
            for stock in st.session_state.watchlist:
                st.code(stock)
    
    # 主界面
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # 市场全景分析
        if st.button("🌐 市场全景分析", use_container_width=True):
            report = market_overview_analysis()
            st.markdown(report)
            
            # 显示选股结果
            if st.session_state.sector_data is not None and st.session_state.leading_stocks is not None:
                selected_stocks = stock_selection_engine(
                    st.session_state.sector_data, 
                    st.session_state.leading_stocks
                )
                
                if selected_stocks:
                    st.subheader("📈 智能选股结果")
                    st.write("推荐关注: " + ", ".join(selected_stocks))
        
        # 股票技术分析
        stock_code = st.text_input("输入股票代码", "000001")
        if st.button("🔍 分析股票", use_container_width=True):
            with st.spinner("获取数据中..."):
                stock_data = get_stock_data(
                    stock_code,
                    (datetime.now() - timedelta(days=180)).strftime("%Y%m%d"),
                    datetime.now().strftime("%Y%m%d")
                )
            
            if stock_data is not None and not stock_data.empty:
                with st.spinner("技术分析中..."):
                    analysis_data = technical_analysis(stock_data.copy())
                
                if analysis_data is not None:
                    # 创建K线图
                    fig = go.Figure(data=[
                        go.Candlestick(
                            x=analysis_data['date'],
                            open=analysis_data['open'],
                            high=analysis_data['high'],
                            low=analysis_data['low'],
                            close=analysis_data['close'],
                            name='K线'
                        ),
                        go.Scatter(
                            x=analysis_data['date'],
                            y=analysis_data['MA5'],
                            line=dict(color='blue', width=1),
                            name='5日均线'
                        ),
                        go.Scatter(
                            x=analysis_data['date'],
                            y=analysis_data['MA20'],
                            line=dict(color='orange', width=1.5),
                            name='20日均线'
                        )
                    ])
                    
                    fig.update_layout(
                        title=f'{stock_code} 技术分析',
                        xaxis_title='日期',
                        yaxis_title='价格',
                        template='plotly_dark'
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 显示最新数据
                    st.subheader("最新行情")
                    st.dataframe(analysis_data[['date', 'close', 'MA5', 'MA20']].tail(10))
    
    with col2:
        st.subheader("📌 市场热点")
        
        # 实时板块资金
        if st.session_state.sector_data is not None and not st.session_state.sector_data.empty:
            st.write("**💰 资金流入板块**")
            for _, row in st.session_state.sector_data.head(3).iterrows():
                sector = row['板块名称'] if '板块名称' in row else row.iloc[0]
                amount = row.get('净额', 0)
                st.metric(sector, f"{amount:.2f}亿")
        
        # 实时龙头股
        if st.session_state.leading_stocks is not None and not st.session_state.leading_stocks.empty:
            st.write("**🚀 今日龙头股**")
            for _, row in st.session_state.leading_stocks.head(3).iterrows():
                code = row['代码'] if '代码' in row else row.iloc[0]
                name = row['名称'] if '名称' in row else row.iloc[1]
                change = row['涨跌幅'] if '涨跌幅' in row else row.iloc[2]
                st.metric(f"{code} {name}", change)

if __name__ == "__main__":
    main()
