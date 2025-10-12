import pandas as pd
import akshare as ak
import streamlit as st
import plotly.graph_objects as go
import plotly  # 添加这个导入
from datetime import datetime, timedelta

# 当前时间
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 版本检查（部署时验证）
st.sidebar.write(f"akshare版本: {ak.__version__}")
st.sidebar.write(f"plotly版本: {plotly.__version__}")  # 修复这里

# 兼容性数据获取
def get_compatible_data(data_source, params, possible_columns):
    try:
        df = data_source(**params)
        if df.empty:
            return pd.DataFrame()
        
        # 列名标准化
        for standard_name, possible_names in possible_columns.items():
            for name in possible_names:
                if name in df.columns:
                    df = df.rename(columns={name: standard_name})
                    break
        
        return df
    except Exception as e:
        st.error(f"数据获取失败: {str(e)}")
        return pd.DataFrame()

# 股票数据获取
def get_stock_data(stock_code, start_date, end_date):
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

# 板块资金流向
def get_sector_fund_flow():
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
            df['净额'] = pd.to_numeric(df['净额'], errors='coerce')
        if '涨跌幅' in df.columns:
            df['涨跌幅'] = pd.to_numeric(df['涨跌幅'].str.replace('%', ''), errors='coerce')
        return df.sort_values("净额", ascending=False).head(10)
    return df

# 龙头股获取
def get_leading_stocks():
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
            df['涨跌幅'] = pd.to_numeric(df['涨跌幅'].str.replace('%', ''), errors='coerce')
        return df.sort_values("涨跌幅", ascending=False).head(10)
    return df

# 选股引擎
def stock_selection_engine(sector_data, leading_stocks):
    selected_stocks = []
    
    if sector_data is not None and not sector_data.empty:
        top_sectors = sector_data.head(3)
        
        sector_name_col = '板块名称' if '板块名称' in sector_data.columns else sector_data.columns[0]
        
        for _, row in top_sectors.iterrows():
            sector = row[sector_name_col]
            
            if '所属板块' in leading_stocks.columns:
                sector_stocks = leading_stocks[leading_stocks['所属板块'].str.contains(sector, na=False)]
                if not sector_stocks.empty:
                    code_col = '代码' if '代码' in sector_stocks.columns else sector_stocks.columns[0]
                    selected_stocks.extend(sector_stocks[code_col].tolist())
    
    return list(set(selected_stocks))[:5]

# 技术分析
def enhanced_analyze_stock(df):
    if df is None or df.empty:
        return None
    
    try:
        # 计算移动平均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        return df.dropna()
    except Exception as e:
        st.error(f"技术分析失败: {str(e)}")
        return None

# 交易建议
def generate_trade_recommendation(stock_data):
    if stock_data is None or stock_data.empty:
        return "无有效数据"
    
    try:
        last_close = stock_data.iloc[-1]['close']
        ma5 = stock_data.iloc[-1]['MA5']
        ma20 = stock_data.iloc[-1]['MA20']
        
        # 基础技术分析
        if last_close > ma20 and last_close > ma5:
            return "买入: 股价在均线上方，趋势向上"
        elif last_close > ma20:
            return "谨慎买入: 股价在20日线上方"
        else:
            return "观望: 股价在20日线下方"
    except:
        return "无法生成建议"

# 市场全景分析
def market_overview_analysis():
    report = "##  📊 市场全景分析\n\n"
    
    with st.spinner("获取板块资金流向..."):
        sector_data = get_sector_fund_flow()
    
    if sector_data is not None and not sector_data.empty:
        report += "### 板块资金流向(单位:亿元)\n"
        report += "| 板块 | 净流入 | 涨跌幅 |\n|------|--------|--------|\n"
        
        sector_name_col = '板块名称' if '板块名称' in sector_data.columns else sector_data.columns[0]
        amount_col = '净额' if '净额' in sector_data.columns else sector_data.columns[1]
        
        for _, row in sector_data.head(5).iterrows():
            sector_name = row[sector_name_col]
            amount = row[amount_col] / 100000000  # 转换为亿
            change = row.get('涨跌幅', 'N/A')
            
            if isinstance(change, (int, float)):
                change = f"{change:.2f}%"
                
            report += f"| {sector_name} | {amount:.2f} | {change} |\n"
    
    with st.spinner("获取龙头股信息..."):
        leading_stocks = get_leading_stocks()
    
    if leading_stocks is not None and not leading_stocks.empty:
        report += "\n###  今日龙头股\n"
        report += "| 代码 | 名称 | 涨跌幅 |\n|------|------|--------|\n"
        
        code_col = '代码' if '代码' in leading_stocks.columns else leading_stocks.columns[0]
        name_col = '名称' if '名称' in leading_stocks.columns else leading_stocks.columns[1]
        change_col = '涨跌幅' if '涨跌幅' in leading_stocks.columns else leading_stocks.columns[2]
        
        for _, row in leading_stocks.head(5).iterrows():
            code = row[code_col]
            name = row[name_col]
            change = row[change_col]
            
            if isinstance(change, (int, float)):
                change = f"{change:.2f}%"
                
            report += f"| {code} | {name} | {change} |\n"
    
    if sector_data is not None and leading_stocks is not None:
        selected_stocks = stock_selection_engine(sector_data, leading_stocks)
        if selected_stocks:
            report += f"\n###  💡 智能选股推荐\n"
            report += f"推荐关注: {', '.join(selected_stocks)}\n"
    
    return report

# 主应用
def main():
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
        st.header("系统配置")
        
        # 版本信息
        st.write(f"AKShare版本: {ak.__version__}")
        st.write(f"Plotly版本: {plotly.__version__}")
        
        st.divider()
        
        # 市场数据
        if st.button("🔄 刷新市场数据", use_container_width=True):
            with st.spinner("获取最新数据中..."):
                st.session_state.sector_data = get_sector_fund_flow()
                st.session_state.leading_stocks = get_leading_stocks()
                st.success("数据已更新!")
        
        st.divider()
        
        # 自选股管理
        st.subheader("自选股管理")
        new_stock = st.text_input("添加股票代码", "000001")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 添加", use_container_width=True):
                if new_stock and new_stock not in st.session_state.watchlist:
                    st.session_state.watchlist.append(new_stock)
                    st.success(f"已添加 {new_stock}")
        with col2:
            if st.button("🗑️ 清空", use_container_width=True):
                st.session_state.watchlist = []
                st.success("自选股已清空")
        
        if st.session_state.watchlist:
            st.write("自选股列表:")
            for stock in st.session_state.watchlist:
                st.code(stock)
            
            if st.button("🔍 分析全部自选股", use_container_width=True):
                st.session_state.analyze_list = st.session_state.watchlist.copy()
                st.success("将分析所有自选股")
    
    # 主界面
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # 市场全景分析
        if st.button("🌐 市场全景分析", use_container_width=True):
            market_report = market_overview_analysis()
            st.markdown(market_report)
            
            if 'sector_data' in st.session_state and 'leading_stocks' in st.session_state:
                selected_stocks = stock_selection_engine(
                    st.session_state.sector_data, 
                    st.session_state.leading_stocks
                )
                
                if selected_stocks:
                    st.subheader("📈 智能选股结果")
                    st.success(f"推荐关注: {', '.join(selected_stocks)}")
                    if st.button("分析推荐股票", type="primary", use_container_width=True):
                        st.session_state.analyze_list = selected_stocks
                        st.success("将分析推荐股票")
        
        # 多股分析
        if hasattr(st.session_state, 'analyze_list') and st.session_state.analyze_list:
            results = []
            for stock_code in st.session_state.analyze_list:
                with st.spinner(f"分析 {stock_code} 中..."):
                    stock_data = get_stock_data(
                        stock_code,
                        (datetime.now() - timedelta(days=180)).strftime("%Y%m%d"),
                        datetime.now().strftime("%Y%m%d")
                    )
                    
                    if stock_data is not None and not stock_data.empty:
                        analysis_data = enhanced_analyze_stock(stock_data.copy())
                        if analysis_data is not None:
                            recommendation = generate_trade_recommendation(analysis_data)
                            results.append({
                                'code': stock_code,
                                'recommendation': recommendation,
                                'last_close': analysis_data.iloc[-1]['close']
                            })
            
            if results:
                st.subheader("📊 多股分析结果")
                for stock in results:
                    with st.expander(f"{stock['code']} - {stock['recommendation']}"):
                        st.write(f"最新价: {stock['last_close']}")
                        st.write(stock['recommendation'])
    
    with col2:
        st.subheader("实时市场")
        
        # 显示板块资金
        if st.session_state.sector_data is not None and not st.session_state.sector_data.empty:
            st.write("**🔥 资金流入板块**")
            sector_name_col = '板块名称' if '板块名称' in st.session_state.sector_data.columns else st.session_state.sector_data.columns[0]
            amount_col = '净额' if '净额' in st.session_state.sector_data.columns else st.session_state.sector_data.columns[1]
            
            for i, row in st.session_state.sector_data.head(3).iterrows():
                amount = row[amount_col] / 100000000
                st.info(f"{row[sector_name_col]}: {amount:.2f}亿")
        
        # 显示龙头股
        if st.session_state.leading_stocks is not None and not st.session_state.leading_stocks.empty:
            st.write("**🚀 今日龙头股**")
            code_col = '代码' if '代码' in st.session_state.leading_stocks.columns else st.session_state.leading_stocks.columns[0]
            name_col = '名称' if '名称' in st.session_state.leading_stocks.columns else st.session_state.leading_stocks.columns[1]
            change_col = '涨跌幅' if '涨跌幅' in st.session_state.leading_stocks.columns else st.session_state.leading_stocks.columns[2]
            
            for i, row in st.session_state.leading_stocks.head(3).iterrows():
                st.success(f"{row[code_col]} {row[name_col]}: {row[change_col]:.2f}%")
    
    # 股票分析区域
    st.divider()
    st.subheader("股票分析")
    
    stock_code = st.text_input("输入股票代码(6位数字)", "000001")
    if st.button("分析股票", type="primary", use_container_width=True):
        with st.spinner("获取数据中..."):
            stock_data = get_stock_data(
                stock_code,
                (datetime.now() - timedelta(days=180)).strftime("%Y%m%d"),
                datetime.now().strftime("%Y%m%d")
            )
        
        if stock_data is not None and not stock_data.empty:
            with st.spinner("技术分析中..."):
                analysis_data = enhanced_analyze_stock(stock_data.copy())
            
            if analysis_data is not None:
                # 显示价格图表
                st.subheader(f"{stock_code} 价格走势")
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=analysis_data['date'], 
                    y=analysis_data['close'], 
                    name='收盘价',
                    line=dict(color='blue', width=2)
                ))
                fig.add_trace(go.Scatter(
                    x=analysis_data['date'], 
                    y=analysis_data['MA5'], 
                    name='5日均线',
                    line=dict(color='orange', width=1)
                ))
                fig.add_trace(go.Scatter(
                    x=analysis_data['date'], 
                    y=analysis_data['MA20'], 
                    name='20日均线',
                    line=dict(color='green', width=1)
                ))
                fig.update_layout(
                    title=f'{stock_code} 价格走势',
                    xaxis_title='日期',
                    yaxis_title='价格',
                    template='plotly_white'
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # 显示交易建议
                st.subheader("操作建议")
                recommendation = generate_trade_recommendation(analysis_data)
                st.info(recommendation)
        else:
            st.warning("无法获取股票数据，请检查股票代码是否正确")

if __name__ == "__main__":
    main()
