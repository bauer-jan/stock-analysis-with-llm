import yfinance as yf
from datetime import datetime, timedelta
from dateutil import parser
from pytickersymbols import PyTickerSymbols
from aws_lambda_powertools import Logger
import pandas as pd
import math
from collections import defaultdict

logger = Logger()
SP_500_WIKI_URL = 'https://en.m.wikipedia.org/wiki/List_of_S%26P_500_companies'


class FinanceService:
    """Class for fetching trading data from Yahoo Finance."""

    def __init__(self, config):
        self.config = config
        self.cache = {}
        self.cache_earnings_dates = {}

        self.today = datetime.today()
        self.symbols = self._get_symbols()
        self.industries, self.sectors = self._get_industries_and_sectors()

        logger.info(f'FinanceService initialized, {len(self.cache)} stocks found on Yahoo.')

    def get_symbols(self):
        return self.symbols

    def _get_symbols(self):
        logger.info(f"INDEX_SYMBOLS: {self.config['DEFAULT']['INDEX_SYMBOLS'].split(',')}")
        return self.list_stock_symbols(self.config['DEFAULT']['INDEX_SYMBOLS'].split(','))

    def get_industry_sector_data(self):
        return self.industries, self.sectors

    def get_history(self, symbol, days_to_subtract=365):
        if symbol in self.cache:
            return self.cache[symbol]

        start_date = (self.today - timedelta(days=days_to_subtract)).strftime('%Y-%m-%d')
        end_date = self.today.strftime('%Y-%m-%d')

        ticker = yf.Ticker(symbol)
        data = ticker.history(start=start_date, end=end_date, period="1d")

        self.cache[symbol] = data, ticker
        return self.cache[symbol]

    def get_earning(self, symbol):
        if symbol not in self.cache_earnings_dates:
            data, ticker = self.get_history(symbol)
            try:
                self.cache_earnings_dates[symbol] = ticker.earnings_dates
            except KeyError:
                self.cache_earnings_dates[symbol] = None
        return self.cache_earnings_dates[symbol]

    def get_info(self, ticker, parameter):
        try:
            return round(ticker.info[parameter], 2)
        except Exception:
            return None

    def get_quarterly_income_stmt(self, ticker, quarter, parameter):
        try:
            val = round(ticker.quarterly_income_stmt.loc[parameter].values[quarter], 2)
            return val if not math.isnan(val) else None
        except Exception:
            return None

    def list_stock_symbols(self, indexes):
        yahoo_symbols = []
        stock_data = PyTickerSymbols()

        # Collect symbols and names
        for index in indexes:
            stocks = stock_data.get_stocks_by_index(index)
            for st in stocks:
                symbols = [symbol['yahoo'] for symbol in st["symbols"] if
                           symbol['currency'] == 'USD' and '.F' not in symbol['yahoo']]
                if symbols:
                    yahoo_symbols.append({'symbol': symbols[0], 'name': st['name']})

        # Add additional symbols
        for symbol in self.config['DEFAULT']['SYMBOLS'].split(','):
            yahoo_symbols.append({'symbol': symbol, 'name': stock_data.get_stock_name_by_yahoo_symbol(symbol)})

        # Group symbols by name
        unique_symbols = defaultdict(list)
        for stock in yahoo_symbols:
            unique_symbols[stock['name']].append(stock['symbol'])

        # Get single symbol for each name
        single_symbols = {k: list(set(v))[0] for k, v in unique_symbols.items()}

        # Return formatted result
        result = [{"symbol": v, "index": False, "name": k} for k, v in single_symbols.items()]
        return result

    def list_wikipedia_sp500(self):
        sp500 = list(pd.read_html(SP_500_WIKI_URL, attrs={'id': 'constituents'}, index_col='Symbol')[0].index.values)
        return [{"symbol": symbol, "index": False} for symbol in sp500]

    def get_last_earning_date(self, last_earnings):
        low = 365
        closest_earning_dates = None
        for date in last_earnings:
            val = (parser.parse(str(date)).replace(tzinfo=None) - datetime.today()).days
            if -val < low:
                low = val
                closest_earning_dates = date
        return closest_earning_dates

    def _get_industries_and_sectors(self):
        industries = {}
        sector = {}

        for symbol in self.symbols:
            if symbol["index"]:
                continue

            data, ticker = self.get_history(symbol["symbol"])
            try:
                industry_key = ticker.info["industry"]
                sector_key = ticker.info["sector"]

                # Industry
                if industry_key and symbol["symbol"] and industry_key in industries:
                    industries[industry_key].append(symbol)
                else:
                    industries[industry_key] = [symbol]

                # Sector
                if sector_key and symbol["symbol"] and sector_key in sector:
                    sector[sector_key].append(symbol)
                else:
                    sector[sector_key] = [symbol]

            except Exception:
                continue

        return industries, sector

    def get_industry_or_sector_data(self, symbol, name, parameter="trailingPE"):
        data, ticker = self.get_history(symbol)

        if name not in ticker.info:
            return None

        if name == 'industry':
            industry_or_sector = self.industries
        elif name == 'sector':
            industry_or_sector = self.sectors
        else:
            logger.info(f'{name} not found in data')
            return None

        industry_or_sector_symbols = industry_or_sector[ticker.info[name]]
        parameter_data_points = []

        for sec_symbol in industry_or_sector_symbols:
            data, ticker = self.get_history(sec_symbol['symbol'])
            try:
                parameter_data_points.append(ticker.info[parameter])
            except KeyError:
                continue

        try:
            industry_avg = round(sum(parameter_data_points) / len(parameter_data_points), 2)
            return industry_avg if parameter_data_points else None
        except (ZeroDivisionError, TypeError):
            return None

    def get_industry_for_symbol(self, symbol):
        data, ticker = self.get_history(symbol)
        return self.industries[ticker.info["industry"]]
