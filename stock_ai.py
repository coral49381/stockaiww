import os
import sys
import time
import requests
import pandas as pd
import akshare as ak
import streamlit as st
from datetime import datetime, timedelta

# 获取当前时间
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S-%d %H:%M:%S")

# 代理配置
PROXY_SETTINGS = {
    'http': 'http://127.0.0.1:7890', 
    'https': 'http://127.0.0.1:7890'
}

# 全局请求设置
REQUEST_TIMEOUT = 25
MAX_RETRIES = 3
RETRY_DELAY = 1.5

# 带代理和重试机制的请求函数
def robust_request(url, method='get', params=None, json=None, headers=None):
    """带代理支持、超时设置和自动重试的HTTP请求函数"""
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.request(
                method=method,
                url=url,
               method,
                url=url,
                params=params,
                json=json,
                headers=headers,
                proxies=PROXY_SETTINGS,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
 )
            response.raise_for_status()
            return response
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            print.Timeout) as e:
            print(f"请求失败 (尝试 {attempt+1}/{MAX_RETRIES}): {str(e)}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                raise Exception(f"API请求失败: {str(e)}")
    return None

# 获取股票数据函数
def get_stock_data数据函数
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
            '成交量': 'volume',
            '成交额': 'amount',
            '振幅': 'amplitude',
            '涨跌幅': 'change_percent',
            '涨跌额': 'change_amount',
            '换手率': 'turnover_rate'
        })
        return stock_df
    except Exception as e:
        st.error(f"获取股票数据失败: {str(e)}")
        return None

# 技术指标分析函数
def analyze_stock指标分析函数
def analyze_stock(df):
    """计算技术指标"""
    if df is None or df.empty:
        return None
    
    # 计算移动平均线
    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()
    
    # 计算MACD
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Histogram'] = df['MACD'] - df['Signal']
    
    # 计算RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df.tail(30)  # 返回最近30天数据

# AI推荐函数
def get_ai_recommendation(analysis_data):
    """使用DeepSeek API获取AI推荐"""
    api_url = "https://api.deepseek.com/v1/chat/completions"
    api_key = st.secrets.get("sk-a1f3b3b7c8ab486aa054f333bb4bd834", os.getenv("sk-a1f3b3b7c8ab486aa054f333bb4bd834", ""))
    
    if not api_key:
        return "错误：缺少DeepSeek API密钥"
    
    # 准备请求数据
    prompt = f"""
    作为金融分析师，请根据以下股票技术指标数据提供专业分析：
    {analysis_data[['date', 'close', 'MA5', 'MA20', 'MACD', 'Signal', 'Histogram', 'RSI']].to_string()}
    
    请包含以下内容：
    1. 当前趋势分析（短期/中期）
    2. 关键指标解读（MACD, RSI）
    3. 买卖建议（买入/持有/卖出）
    4. 风险提示
    """
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是专业的金融分析师，擅长技术指标解读和股票推荐"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    try:
        response = robust_request(
            api_url, 
            method='post', 
            json=payload, 
            headers=headers
        )
        
        if response and response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"API返回错误: {response.text if response else '无响应'}"
    except Exception as e:
        return f"获取AI推荐失败: {str(e)}"

# Streamlit应用界面
def main():
    st.set_page_config(
        page_title="智能选股系统", 
        page_icon股系统", 
        page_icon="📈", 
        layout="wide"
    )
    
    st.title("🚀 智能选股系统")
    st.caption(f"最后更新: {current_time} | 使用AKShare和DeepSeek API")
    
    # 侧边栏设置
    with st.sidebar:
        st.header("设置")
        stock_code = st.text_input("股票代码", "000001")
        start_date = st.date_input("开始日期", datetime.now() - timedelta(days=180))
        end_date = st.date_input("结束日期", datetime.now())
        
        # 代理设置选项
        st.subheader("网络设置")
        use_proxy = st.checkbox("启用代理", value=True)
        proxy_address = st.text_input("代理地址", PROXY_SETTINGS['http'])
        
        # 更新代理设置
        global PROXY_SETTINGS
        if use_proxy:
            PROXY_SETTINGS = {
                'http': proxy_address,
                'https': proxy_address
            }
        else:
            PROXY_SETTINGS = {}
        
        st.info(f"当前代理设置: {PROXY_SETTINGS if use_proxy else '无'}")
    
    # 主界面
    if st.button("分析股票"):
        with st.spinner("获取数据中..."):
            stock_data = get_stock_data(
                stock_code, 
                start_date.strftime("%Y%m%d"), 
                end_date.strftime("%Y%m%d")
            )
        
        if stock_data is not None:
            st.success("数据获取成功!")
            
            # 显示原始数据
            st.subheader("股票历史数据")
            st.dataframe(stock_data.tail(10), height=300)
            
            # 技术分析
            st.subheader("技术分析")
            analysis_data = analyze_stock(stock_data.copy())
            
            if analysis_data is not None:
                # 显示技术指标数据
                st.dataframe(analysis_data[['date', 'close', 'MA5', 'MA20', 'MACD', 'RSI']].rename(columns={
                    'date': '日期',
                    'close': '收盘价',
                    'MA5': '5日均线',
                    'MA20': '20日均线'
                }))
                
                # 绘制价格和MA线
                st.line_chart(analysis_data.set_index('date')[['close', 'MA5', 'MA20']].rename(columns={
                    'close': '收盘价',
                    'MA5': '5日均线',
                    'MA20': '20日均线'
                }))
                
                # 显示MACD图表
                st.line_chart(analysis_data.set_index('date')[['MACD', 'Signal']].rename(columns={
                    'MACD': 'MACD线',
                    'Signal': '信号线'
                }))
                
                # AI推荐
                with st.spinner("AI分析中..."):
                   inner("AI分析中..."):
                    recommendation = get_ai_recommendation(analysis_data)
                
                st.subheader("AI推荐")
                st.markdown(f"**股票代码: {stock_code}**")
                st.markdown(recommendation)
            else:
                st.warning("技术分析失败")
        else:
            st.error("无法获取股票数据")

if __name__ == "__main__":
    main()
