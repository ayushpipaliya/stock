import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# Set page config
st.set_page_config(
    page_title="📈 NSE Stock News Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-container {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .positive-change {
        color: #00ff00;
        font-weight: bold;
    }
    .negative-change {
        color: #ff0000;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'analysis_run' not in st.session_state:
    st.session_state.analysis_run = False
if 'results_data' not in st.session_state:
    st.session_state.results_data = None

# 🔍 1. Get NSE listed stocks
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_nse_stock_list():
    """
    Fetches the list of NSE listed stock symbols from the NSE India archives.
    Returns:
        list: A list of stock symbols.
    """
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    try:
        df = pd.read_csv(url)
        return [s.strip().upper() for s in df['SYMBOL'].tolist()]
    except Exception as e:
        st.error(f"⚠️ Unable to fetch NSE stock list: {e}")
        return []

# 📰 2. Get latest positive news from MoneyControl
def get_positive_news():
    """
    Fetches news headlines from MoneyControl and filters for positive keywords.
    Returns:
        list: A list of positive news headlines.
    """
    url = "https://www.moneycontrol.com/news/business/stocks/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        news = []
        
        for item in soup.find_all('li', class_='clearfix'):
            headline_tag = item.find('h2')
            if headline_tag:
                headline = headline_tag.get_text(strip=True)
                if any(word in headline.lower() for word in ["order", "profit", "acquisition", "launch", "contract", "gains", "rises", "boost", "expands"]):
                    news.append(headline)
        return news
    except requests.exceptions.RequestException as e:
        st.error(f"⚠️ Error fetching news from MoneyControl: {e}")
        return []
    except Exception as e:
        st.error(f"⚠️ An unexpected error occurred while parsing news: {e}")
        return []

# 🏷️ 3. Match symbols from NSE stock list with news
def extract_symbols_from_news(news_list, all_symbols, progress_bar=None):
    """
    Extracts stock symbols from news headlines using a more flexible normalization approach.
    """
    matched = []
    all_symbols_sorted = sorted(all_symbols, key=len, reverse=True)
    
    total_news = len(news_list)
    
    for headline_idx, headline in enumerate(news_list):
        if progress_bar:
            progress_bar.progress((headline_idx + 1) / total_news, 
                                text=f"Processing news {headline_idx + 1}/{total_news}")
        
        lower_headline = headline.lower()
        normalized_headline = re.sub(r'[^a-z0-9]', '', lower_headline)
        
        for symbol in all_symbols_sorted:
            lower_symbol = symbol.lower()
            normalized_symbol = re.sub(r'[^a-z0-9]', '', lower_symbol)
            
            if not normalized_symbol:
                continue
                
            if normalized_symbol in normalized_headline:
                matched.append(symbol)
                break
    
    return list(set(matched))

# 🔧 Symbol existence check
def is_valid_symbol(symbol):
    """
    Checks if a stock symbol is valid and has market data available via yfinance.
    """
    try:
        info = yf.Ticker(f"{symbol}.NS").info
        return 'regularMarketPrice' in info and info['regularMarketPrice'] is not None
    except Exception:
        return False

# 📈 4. Get stock return % using yfinance
def get_stock_performance(symbol):
    """
    Retrieves the percentage change in stock price for the last two days using yfinance.
    """
    try:
        stock = yf.Ticker(f"{symbol}.NS")
        hist = stock.history(period="2d")
        
        if hist.empty or len(hist) < 2:
            return None
            
        yesterday_close = hist['Close'].iloc[-2]
        today_close = hist['Close'].iloc[-1]
        
        if yesterday_close == 0:
            return None
            
        change_percent = ((today_close - yesterday_close) / yesterday_close) * 100
        return round(change_percent, 2)
    except Exception:
        return None

# 🧠 5. Full analysis runner
def run_analysis(min_return_threshold=5.0):
    """
    Orchestrates the entire stock analysis process.
    """
    results = {
        'symbols_loaded': 0,
        'news_found': 0,
        'matched_symbols': [],
        'performance_data': [],
        'filtered_stocks': pd.DataFrame(),
        'news_headlines': []
    }
    
    # Progress tracking
    progress_container = st.container()
    
    with progress_container:
        st.info("📥 Fetching NSE symbols...")
        all_symbols = get_nse_stock_list()
        if not all_symbols:
            st.error("❌ Could not fetch NSE symbols. Exiting analysis.")
            return results
        
        results['symbols_loaded'] = len(all_symbols)
        st.success(f"✅ Loaded {len(all_symbols)} symbols")
        
        st.info("🔄 Fetching latest positive news...")
        news = get_positive_news()
        if not news:
            st.error("❌ Could not fetch positive news. Exiting analysis.")
            return results
        
        results['news_found'] = len(news)
        results['news_headlines'] = news
        st.success(f"📌 Found {len(news)} positive news items")
        
        st.info("🔍 Matching symbols from news...")
        progress_bar = st.progress(0, text="Processing news...")
        matched_symbols = extract_symbols_from_news(news, all_symbols, progress_bar)
        progress_bar.empty()
        
        if not matched_symbols:
            st.warning("💡 No potential stocks found from news.")
            return results
        
        results['matched_symbols'] = matched_symbols
        st.success(f"💡 Found {len(matched_symbols)} potential stocks from news")
        
        st.info("📊 Analyzing price changes...")
        performance_progress = st.progress(0, text="Analyzing stock performance...")
        
        performance_data = []
        total_symbols = len(matched_symbols)
        
        for idx, symbol in enumerate(matched_symbols):
            performance_progress.progress((idx + 1) / total_symbols, 
                                        text=f"Analyzing {symbol} ({idx + 1}/{total_symbols})")
            
            if not is_valid_symbol(symbol):
                continue
                
            change = get_stock_performance(symbol)
            if change is not None:
                performance_data.append({'Stock': symbol, 'Change %': change})
        
        performance_progress.empty()
        
        if performance_data:
            result_df = pd.DataFrame(performance_data)
            filtered = result_df[result_df["Change %"] > min_return_threshold].sort_values(by="Change %", ascending=False)
            results['performance_data'] = performance_data
            results['filtered_stocks'] = filtered
    
    return results

# Streamlit App Layout
def main():
    # Header
    st.markdown('<h1 class="main-header">📈 NSE Stock News Analyzer</h1>', unsafe_allow_html=True)
    st.markdown("**Discover potential rally stocks based on positive news and price movements**")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        min_return = st.slider(
            "Minimum Return Threshold (%)",
            min_value=1.0,
            max_value=20.0,
            value=5.0,
            step=0.5,
            help="Filter stocks with returns greater than this percentage"
        )
        
        st.markdown("---")
        
        if st.button("🚀 Run Analysis", type="primary", use_container_width=True):
            st.session_state.analysis_run = True
            with st.spinner("Running comprehensive analysis..."):
                results = run_analysis(min_return)
                st.session_state.results_data = results
        
        if st.button("🔄 Clear Results", use_container_width=True):
            st.session_state.analysis_run = False
            st.session_state.results_data = None
            st.rerun()
    
    # Main content area
    if st.session_state.analysis_run and st.session_state.results_data:
        results = st.session_state.results_data
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📊 NSE Symbols Loaded", results['symbols_loaded'])
        
        with col2:
            st.metric("📰 Positive News Found", results['news_found'])
        
        with col3:
            st.metric("🎯 Symbols Matched", len(results['matched_symbols']))
        
        with col4:
            st.metric(f"🔥 Stocks >{min_return}% Return", len(results['filtered_stocks']))
        
        # Results section
        if not results['filtered_stocks'].empty:
            st.header("🔥 Top Performing Stocks")
            
            # Create tabs for different views
            tab1, tab2, tab3 = st.tabs(["📊 Results Table", "📈 Chart View", "📰 News Headlines"])
            
            with tab1:
                # Styled dataframe
                styled_df = results['filtered_stocks'].copy()
                styled_df['Change %'] = styled_df['Change %'].apply(lambda x: f"+{x}%" if x > 0 else f"{x}%")
                
                st.dataframe(
                    styled_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Stock": st.column_config.TextColumn("Stock Symbol", width="medium"),
                        "Change %": st.column_config.TextColumn("Price Change", width="medium")
                    }
                )
                
                # Download button
                csv = results['filtered_stocks'].to_csv(index=False)
                st.download_button(
                    label="📥 Download Results as CSV",
                    data=csv,
                    file_name=f"stock_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            with tab2:
                if len(results['filtered_stocks']) > 0:
                    fig = px.bar(
                        results['filtered_stocks'],
                        x='Stock',
                        y='Change %',
                        title='Stock Performance (% Change)',
                        color='Change %',
                        color_continuous_scale='RdYlGn'
                    )
                    fig.update_layout(
                        xaxis_title="Stock Symbol",
                        yaxis_title="Percentage Change (%)",
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            with tab3:
                st.subheader("📰 Positive News Headlines")
                for i, headline in enumerate(results['news_headlines'][:10], 1):
                    st.write(f"{i}. {headline}")
                
                if len(results['news_headlines']) > 10:
                    with st.expander(f"Show all {len(results['news_headlines'])} headlines"):
                        for i, headline in enumerate(results['news_headlines'][10:], 11):
                            st.write(f"{i}. {headline}")
        
        else:
            st.warning(f"❌ No stocks found with >{min_return}% return today.")
            
            # Show all performance data if available
            if results['performance_data']:
                st.subheader("📊 All Analyzed Stocks")
                all_performance_df = pd.DataFrame(results['performance_data'])
                all_performance_df = all_performance_df.sort_values(by="Change %", ascending=False)
                st.dataframe(all_performance_df, use_container_width=True, hide_index=True)
    
    else:
        # Welcome message
        st.info("👈 Click 'Run Analysis' in the sidebar to start discovering potential rally stocks!")
        
        # Feature highlights
        st.subheader("🚀 Features")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            **📊 Data Sources:**
            - NSE official stock listings
            - MoneyControl positive news
            - Yahoo Finance price data
            """)
        
        with col2:
            st.markdown("""
            **🔍 Analysis Process:**
            - Fetches latest positive news
            - Matches stock symbols from headlines
            - Calculates price performance
            - Filters high-performing stocks
            """)
        
        # Instructions
        st.subheader("📝 How to Use")
        st.markdown("""
        1. **Adjust Settings:** Use the sidebar to set minimum return threshold
        2. **Run Analysis:** Click the "Run Analysis" button
        3. **View Results:** Browse through the results in different tabs
        4. **Download Data:** Export results as CSV for further analysis
        """)

if __name__ == "__main__":
    main()
