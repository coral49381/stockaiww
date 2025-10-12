import streamlit as st
import pandas as pd
import akshare as ak
import requests
import json
import time
from datetime import datetime

# 设置页面标题和布局
st.set_page_config(
    page_title="A股智能选股系统",
    page_icon="📈",
    layout="wide"
)

# 设置DeepSeek API密钥（替换成你自己的密钥）
DEEPSEEK_API_KEY = "sk-a1f3b3b7c8ab486aa054f333bb4bd834"

# 初始化会话状态
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "您好！我是您的A股投资助手，请问今天需要分析哪些股票？"}
    ]

# 显示历史消息
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 获取股票数据函数
def get_stock_data(stock_code):
    """获取股票实时数据"""
    try:
        df = ak.stock_zh_a_spot_em()
        stock_data = df[df["代码"] == stock_code].iloc[0]
        return {
            "代码": stock_code,
            "名称": stock_data["名称"],
            "最新价": stock_data["最新价"],
            "涨跌幅": stock_data["涨跌幅"],
            "成交量": stock_data["成交量"],
            "换手率": stock_data["换手率"],
            "市盈率": stock_data["市盈率-动态"]
        }
    except:
        return None

def get_market_sentiment():
    """获取市场情绪数据"""
    try:
        # 获取涨跌家数
        df = ak.stock_zh_a_spot_em()
        rise_count = len(df[df['涨跌幅'] > 0])
        fall_count = len(df[df['涨跌幅'] < 0])
        
        # 获取热点板块
        sector_df = ak.stock_sector_spot_em()
        hot_sectors = sector_df.nlargest(5, '涨跌幅')['板块名称'].tolist()
        
        return {
            "上涨家数": rise_count,
            "下跌家数": fall_count,
            "热门板块": hot_sectors
        }
    except:
        return None

# 调用DeepSeek API函数
def get_ai_response(user_input):
    """调用DeepSeek API获取回复"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 构建对话上下文
    messages = [{"role": "system", "content": "你是一位专业的A股量化分析师，精通技术分析和基本面分析。"}]
    for msg in st.session_state.messages:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_input})
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"API错误: {response.status_code} - {response.text}"
    except Exception as e:
        return f"请求失败: {str(e)}"

# 智能选股功能
def select_stocks_by_strategy(strategy_description):
    """根据策略描述选股"""
    # 获取全市场股票
    all_stocks = ak.stock_info_a_code_name()['code'].tolist()
    
    # 由于全市场股票太多，这里只取前200只作为示例
    sample_stocks = all_stocks[:200]
    
    # 构建策略提示
    prompt = f"""
    你是一位量化交易专家，请根据以下策略从股票池中筛选符合要求的股票：
    
    【策略描述】
    {strategy_description}
    
    【股票池】（共{len(sample_stocks)}只股票）
    {sample_stocks}
    
    输出要求：
    1. 只需返回股票代码列表，例如：['600519', '000001']
    2. 不要包含任何解释性文字
    """
    
    # 获取AI筛选结果
    response = get_ai_response(prompt)
    
    # 尝试解析返回的股票代码列表
    try:
        # 尝试从字符串中提取股票代码
        import re
        codes = re.findall(r"\d{6}", response)
        return codes
    except:
        return []

# 主聊天界面
if user_input := st.chat_input("请输入您的指令..."):
    # 添加到聊天记录
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # 显示用户消息
    with st.chat_message("user"):
        st.markdown(user_input)
    
    # 处理不同类型指令
    if user_input.startswith("分析"):
        # 提取股票代码
        stock_code = user_input[2:].strip()
        if stock_code.isdigit() and len(stock_code)==6:
            with st.chat_message("assistant"):
                with st.spinner("分析中..."):
                    # 获取股票数据
                    stock_data = get_stock_data(stock_code)
                    
                    if stock_data:
                        # 构建分析请求
                        prompt = f"""
                        你是一位资深股票分析师，请根据以下股票信息进行分析：
                        
                        【股票信息】
                        代码：{stock_data['代码']}
                        名称：{stock_data['名称']}
                        最新价：{stock_data['最新价']}
                        涨跌幅：{stock_data['涨跌幅']}%
                        成交量：{stock_data['成交量']}手
                        换手率：{stock_data['换手率']}%
                        市盈率：{stock_data['市盈率']}
                        
                        请从技术面、资金面和市场情绪三方面分析，给出：
                        1. 短期走势预测
                        2. 操作建议（买入/持有/卖出）
                        3. 风险提示
                        """
                        analysis_result = get_ai_response(prompt)
                        st.markdown(analysis_result)
                        st.session_state.messages.append({"role": "assistant", "content": analysis_result})
                    else:
                        error_msg = f"无法获取股票{stock_code}的数据，请检查代码是否正确"
                        st.error(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        else:
            with st.chat_message("assistant"):
                error_msg = "请提供正确的股票代码，例如：分析600519"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
    
    elif user_input.startswith("选股"):
        strategy = user_input[2:].strip()
        if strategy:
            with st.chat_message("assistant"):
                st.markdown(f"正在根据策略『{strategy}』筛选股票...")
                with st.spinner("筛选中，请稍候..."):
                    selected_stocks = select_stocks_by_strategy(strategy)
                    
                    if selected_stocks:
                        # 获取股票详情
                        df = ak.stock_zh_a_spot_em()
                        result_df = df[df['代码'].isin(selected_stocks)][['代码','名称','最新价','涨跌幅','市盈率-动态']]
                        
                        # 显示结果表格
                        st.dataframe(result_df.style.highlight_max(axis=0, subset=['涨跌幅']))
                        
                        result_msg = f"根据策略『{strategy}』，筛选出{len(selected_stocks)}只股票"
                        st.session_state.messages.append({"role": "assistant", "content": result_msg})
                    else:
                        error_msg = "未筛选出符合条件的股票，请尝试调整策略"
                        st.error(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        else:
            with st.chat_message("assistant"):
                error_msg = "请提供选股策略，例如：选股PE<20且涨幅>5%"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
    
    elif "市场情绪" in user_input:
        with st.chat_message("assistant"):
            with st.spinner("获取市场情绪中..."):
                sentiment = get_market_sentiment()
                if sentiment:
                    msg = f"当前市场情绪：\n"
                    msg += f"- 上涨家数：{sentiment['上涨家数']}\n"
                    msg += f"- 下跌家数：{sentiment['下跌家数']}\n"
                    msg += f"- 热门板块：{', '.join(sentiment['热门板块'])}\n\n"
                    
                    # 添加简要分析
                    analysis_prompt = f"作为市场分析师，请根据以下数据提供简要市场情绪分析：\n{msg}"
                    analysis = get_ai_response(analysis_prompt)
                    msg += "【市场情绪分析】\n" + analysis
                    
                    st.markdown(msg)
                    st.session_state.messages.append({"role": "assistant", "content": msg})
                else:
                    error_msg = "获取市场情绪数据失败"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
    
    else:
        # 普通对话
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                ai_response = get_ai_response(user_input)
                st.markdown(ai_response)
                st.session_state.messages.append({"role": "assistant", "content": ai_response})