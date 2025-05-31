import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re # Import the regular expression module

# 🔍 1. Get NSE listed stocks
def get_nse_stock_list():
    """
    Fetches the list of NSE listed stock symbols from the NSE India archives.
    Returns:
        list: A list of stock symbols.
    """
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    try:
        df = pd.read_csv(url)
        # Ensure symbols are stripped of whitespace and converted to uppercase
        return [s.strip().upper() for s in df['SYMBOL'].tolist()]
    except Exception as e:
        print(f"⚠️ Unable to fetch NSE stock list: {e}")
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
        response = requests.get(url, headers=headers, timeout=10) # Added timeout
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(response.text, "html.parser")
        news = []
        # Look for news items, adjusting selector if needed based on MoneyControl's current structure
        # Common selectors might be 'li.clearfix', 'div.each_news', 'h2.bsns_news_heading' etc.
        # This example assumes 'li' with class 'clearfix' contains the headline text.
        for item in soup.find_all('li', class_='clearfix'):
            headline_tag = item.find('h2') # Often the headline is within an h2 or a tag
            if headline_tag:
                headline = headline_tag.get_text(strip=True)
                # Keywords indicating positive news
                if any(word in headline.lower() for word in ["order", "profit", "acquisition", "launch", "contract", "gains", "rises", "boost", "expands"]):
                    news.append(headline)
        return news
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error fetching news from MoneyControl: {e}")
        return []
    except Exception as e:
        print(f"⚠️ An unexpected error occurred while parsing news: {e}")
        return []

# 🏷️ 3. Match symbols from NSE stock list with news
def extract_symbols_from_news(news_list, all_symbols):
    """
    Extracts stock symbols from news headlines using a more flexible normalization approach.
    This version normalizes both headlines and symbols by removing non-alphanumeric characters
    and then performs a substring match.
    Args:
        news_list (list): A list of news headlines.
        all_symbols (list): A list of all known stock symbols.
    Returns:
        list: A list of unique matched stock symbols.
    """
    matched = []
    # Sort symbols by length in descending order to prioritize matching longer, more specific symbols first
    all_symbols_sorted = sorted(all_symbols, key=len, reverse=True)

    print("--- Debugging Symbol Matching ---")
    print(f"Total NSE symbols loaded: {len(all_symbols_sorted)}")
    # Print a sample of symbols to confirm their format
    print(f"Sample NSE symbols (first 5): {all_symbols_sorted[:5]}...")

    for headline_idx, headline in enumerate(news_list):
        lower_headline = headline.lower()
        print(f"\n[{headline_idx + 1}/{len(news_list)}] Checking headline: '{headline}'")

        # Normalize the headline: remove all non-alphanumeric characters
        # This converts "Sun Pharma" to "sunpharma", "Dr Reddy's" to "drreddys", "M&M" to "mm"
        normalized_headline = re.sub(r'[^a-z0-9]', '', lower_headline)
        print(f"  Normalized headline: '{normalized_headline}'")

        found_match_for_headline = False
        for symbol_idx, symbol in enumerate(all_symbols_sorted):
            lower_symbol = symbol.lower()
            
            # Normalize the symbol: remove all non-alphanumeric characters
            # This converts "SUNPHARMA" to "sunpharma", "DRREDDY" to "drreddy", "M&M" to "mm"
            normalized_symbol = re.sub(r'[^a-z0-9]', '', lower_symbol)

            if not normalized_symbol: # Skip if normalized symbol is empty (e.g., if original symbol was just '&')
                # print(f"    Skipping symbol '{symbol}' as its normalized form is empty.") # Too verbose
                continue

            # Perform a simple substring check between the normalized headline and symbol
            # This is more forgiving for variations in news text vs. official symbols
            if normalized_symbol in normalized_headline:
                print(f"📰 News matched: '{headline}' → {symbol} (Normalized: '{normalized_symbol}' found in '{normalized_headline}')")
                matched.append(symbol)
                found_match_for_headline = True
                break # Found a match for this headline, move to the next headline
            # else:
            #     # Uncomment for extremely verbose debugging, shows every non-match
            #     print(f"    No match: '{normalized_symbol}' not in '{normalized_headline}' for symbol '{symbol}'")

        if not found_match_for_headline:
            print(f"  No stock symbol matched for this headline.")

    print("--- End Debugging Symbol Matching ---")
    return list(set(matched))

# 🔧 સમાધાન 3: Symbol અસ્તિત્વ ચકાસો yfinance માં પહેલાં
def is_valid_symbol(symbol):
    """
    Checks if a stock symbol is valid and has market data available via yfinance.
    Args:
        symbol (str): The stock symbol to check (e.g., "RELIANCE").
    Returns:
        bool: True if the symbol is valid and has market price info, False otherwise.
    """
    try:
        # Attempt to get basic info for the symbol
        info = yf.Ticker(f"{symbol}.NS").info
        # A common indicator of a valid, active stock is the presence of 'regularMarketPrice'
        # or 'marketCap'. We use 'regularMarketPrice' as it's often present for active trading.
        return 'regularMarketPrice' in info and info['regularMarketPrice'] is not None
    except Exception as e:
        # This can catch issues like invalid symbols that yfinance cannot resolve
        # print(f"DEBUG: is_valid_symbol check failed for {symbol}: {e}") # For debugging
        return False

# 📈 4. Get stock return % using yfinance
def get_stock_performance(symbol):
    """
    Retrieves the percentage change in stock price for the last two days using yfinance.
    Args:
        symbol (str): The stock symbol (e.g., "RELIANCE").
    Returns:
        float or None: The percentage change, rounded to 2 decimal places, or None if data is unavailable.
    """
    try:
        stock = yf.Ticker(f"{symbol}.NS")
        # Fetch historical data for 2 days to get yesterday's and today's closing prices
        hist = stock.history(period="2d")

        # 🔧 સમાધાન 2: yfinance ચેck કરો symbol supported છે કે નહિ
        # Check if the historical data is empty or does not have enough entries
        if hist.empty or len(hist) < 2:
            print(f"⚠️ No sufficient historical data for {symbol}.NS — might be delisted, invalid, or recent listing.")
            return None

        yesterday_close = hist['Close'].iloc[-2]
        today_close = hist['Close'].iloc[-1]

        if yesterday_close == 0: # Avoid division by zero
            print(f"⚠️ Yesterday's closing price for {symbol}.NS was 0, cannot calculate change.")
            return None

        change_percent = ((today_close - yesterday_close) / yesterday_close) * 100
        return round(change_percent, 2)
    except Exception as e:
        print(f"⚠️ Error fetching performance for {symbol}.NS: {e}")
        return None

# 🧠 5. Full analysis runner
def run_analysis():
    """
    Orchestrates the entire stock analysis process:
    1. Fetches NSE stock list.
    2. Fetches positive news.
    3. Matches symbols from news.
    4. Validates and retrieves stock performance for matched symbols.
    5. Filters and prints stocks with >5% return.
    """
    print("📥 Fetching NSE symbols...")
    all_symbols = get_nse_stock_list()
    if not all_symbols:
        print("❌ Could not fetch NSE symbols. Exiting analysis.")
        return
    print(f"✅ Loaded {len(all_symbols)} symbols")

    print("\n🔄 Fetching latest positive news...")
    news = get_positive_news()
    if not news:
        print("❌ Could not fetch positive news. Exiting analysis.")
        return
    print(f"📌 Found {len(news)} positive news items")
    print(f"Sample positive news (first 3): {news[:3]}...") # Add this line to see the news

    print("\n🔍 Matching symbols from news...")
    matched_symbols = extract_symbols_from_news(news, all_symbols)
    if not matched_symbols:
        print("💡 No potential stocks found from news.")
        return
    print(f"💡 Potential stocks from news: {matched_symbols}")

    print("\n📊 Analyzing price changes...")
    result = []
    for symbol in matched_symbols:
        # Validate symbol before attempting to get its performance
        if not is_valid_symbol(symbol):
            print(f"Skipping {symbol}: Not a valid or active yfinance symbol.")
            continue

        change = get_stock_performance(symbol)
        if change is not None:
            result.append((symbol, change))

    result_df = pd.DataFrame(result, columns=["Stock", "Change %"])
    # Filter for stocks with a positive change greater than 5%
    filtered = result_df[result_df["Change %"] > 5].sort_values(by="Change %", ascending=False)

    print("\n🔥 Stocks with >5% return today (may indicate next-day rally):")
    if filtered.empty:
        print("❌ No stocks found with >5% return today.")
    else:
        print(filtered.to_string(index=False))

# ▶️ Run app
if __name__ == "__main__":
    run_analysis()