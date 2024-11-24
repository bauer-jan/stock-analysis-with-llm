from dataclasses import dataclass

from aws_lambda_powertools import Logger
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute, NumberAttribute, BooleanAttribute
import os
import json

logger = Logger()

REGION = os.getenv("REGION", "eu-central-1")
TABLE_NAME_STOCK_ANALYTICS = os.getenv("TABLE_NAME_STOCK_ANALYTICS", "StockAnalytics")
TABLE_NAME_PORTFOLIO = os.getenv("TABLE_NAME_PORTFOLIO", "Portfolio")
TABLE_NAME_REALIZED_GAINS  = os.getenv("TABLE_NAME_REALIZED_GAINS", "RealizedGains")

class StockAnalysis(Model):
    class Meta:
        table_name = TABLE_NAME_STOCK_ANALYTICS
        region = REGION

    stock = UnicodeAttribute(hash_key=True)
    date = UnicodeAttribute(range_key=True)
    close = NumberAttribute()
    name = UnicodeAttribute(null=True)
    rank = NumberAttribute(null=True)
    stock_news = UnicodeAttribute(null=True)
    investment_decision = UnicodeAttribute(null=True)
    explanation = UnicodeAttribute(null=True)
    industry = UnicodeAttribute(null=True)


class Portfolio(Model):
    class Meta:
        table_name = TABLE_NAME_PORTFOLIO
        region = REGION

    stock = UnicodeAttribute(hash_key=True)
    date = UnicodeAttribute(range_key=True)
    name = UnicodeAttribute()
    number_of_shares_to_buy = NumberAttribute()
    sell_date = UnicodeAttribute(null=True)
    performance =  NumberAttribute(null=True)
    current_value = NumberAttribute(null=True)
    buy_date_value = NumberAttribute(null=True)
    current_price = NumberAttribute(null=True)
    buy_date_closing_price = NumberAttribute(null=True)

class RealizedGains(Model):
    class Meta:
        table_name = TABLE_NAME_REALIZED_GAINS
        region = REGION

    key = UnicodeAttribute(hash_key=True)
    date = UnicodeAttribute(range_key=True)
    total_sell_value = NumberAttribute()
    total_buy_value = NumberAttribute()
    performance = NumberAttribute(null=True)

@dataclass()
class DatabaseService:

    def save_stock_analytics(self, objects):
        for obj in objects:
            try:
                item = StockAnalysis(stock=obj["symbol"],
                                     date=obj["date"],
                                     close=obj["previousClose"],
                                     rank=obj.get('rank', 999),
                                     stock_news=obj.get("StockNews", "None"),
                                     investment_decision=obj.get("investment_decision", "None"),
                                     explanation=obj.get("explanation", 'No explanation found'),
                                     industry=obj["industry"],
                                     name=obj.get('name'))
                item.save()
            except Exception as e:
                logger.info(f'Error while saving, obj : {obj}, error: {e}')

    def save_portfolio(self, objects, date):
        for obj in objects:
            try:
                item = Portfolio(stock=obj["symbol"],
                                 date=date,
                                 name=obj["name"],
                                 number_of_shares_to_buy=obj["number_of_shares_to_buy"])
                item.save()
            except Exception as e:
                logger.info(f'Error while saving, obj : {obj}, error: {e}')

    def mark_sold_stocks_in_portfolio(self, objects):
        for obj in objects:
            try:
                item = Portfolio(stock=obj["stock"],
                                 date=obj["buy_date"],
                                 name=obj["stock"],
                                 number_of_shares_to_buy=obj["number_of_shares"],
                                 sell_date = obj["sell_date"],
                                 performance= obj["performance"],
                                 current_value= obj["current_value"],
                                 buy_date_value= obj["buy_date_value"],
                                 current_price= obj["current_price"],
                                 buy_date_closing_price= obj["buy_date_closing_price"])
                item.save()
            except Exception as e:
                logger.info(f'Error while saving, obj : {obj}, error: {e}')
    def save_realized_gains(self, total_sell_value, total_buy_value, date, gains):
        try:
            item = RealizedGains(key="realizedGains",
                                 date=date,
                                 total_sell_value=round(total_sell_value, 2),
                                 total_buy_value=round(total_buy_value, 2),
                                 performance=gains)
            item.save()
        except Exception as e:
            logger.info(f'Error while saving, realized gains, error: {e}')

    def get_realized_gains(self):
        return [json.loads(item.to_json()) for item in self.scan(RealizedGains)]

    def get_analyst_data(self, stocks, date):
        item_keys = [(stock['symbol'], date) for stock in stocks]
        return [json.loads(item.to_json()) for item in StockAnalysis.batch_get(item_keys)]

    def get_portfolio_data(self):
        return [json.loads(item.to_json()) for item in self.scan(Portfolio)]

    def scan(self, model_class):
        rows = model_class.scan()
        return rows

    def delete_portfolio(self):
        portfolio = self.scan(Portfolio)
        with Portfolio.batch_write() as batch:
            for r in portfolio:
                batch.delete(r)
