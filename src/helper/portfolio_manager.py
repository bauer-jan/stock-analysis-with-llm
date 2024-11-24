from helper.helper import HelperService
import yaml
import pandas as pd
import configparser
from dateutil import parser
import pandas as pd
from aws_lambda_powertools import Logger

logger = Logger()

config = configparser.ConfigParser()
config.read('config.ini')

helper: HelperService = HelperService(config)

class PortfolioManager:
    def __init__(self):
        with open('schema/prompts.yaml', 'r') as file:
            self.prompts = yaml.safe_load(file)

    def manage_portfolio(self, finance_api, database):
        date = finance_api.today.strftime('%Y-%m-%d')
        try:
            portfolio_data = database.get_portfolio_data()
            portfolio_data_without_sold_stocks = []
            for stock in portfolio_data:
                if 'sell_date' not in stock:
                    portfolio_data_without_sold_stocks.append(stock)
            performance = self._get_portfolio_performance(portfolio_data_without_sold_stocks, finance_api)
            positions_to_sell = self._update_portfolio_and_realize_gains(database, finance_api, date, performance)
            database.mark_sold_stocks_in_portfolio(positions_to_sell)
        except Exception as e:
            logger.info(f"Error during portfolio performance calculation, {e}")

        logger.info(f'Start portfolio manager {date}')

        stocks = helper.get_stocks(finance_api)
        logger.info(f'{len(stocks)} stocks found')

        market_sentiment = ''
        try:
            market_sentiment += helper.invoke_agent(self.prompts['agent_web_search_portfolio_manger']['prompt'].
                                             replace("<term>", "US")) + "; "
            market_sentiment += helper.invoke_agent(self.prompts['agent_web_search_portfolio_manger']['prompt'].
                                             replace("<term>", "EU")) + "; "
            market_sentiment += helper.invoke_agent(self.prompts['agent_web_search_portfolio_manger']['prompt'].
                                             replace("<term>", "China"))
        except Exception as e:
            logger.info(f'Error getting market sentiment, error: {e}')

        stock_analysis = database.get_analyst_data(stocks=stocks, date=date)
        logger.info(f'{len(stock_analysis)} stocks analysis found from today {date}')
        for stock in stock_analysis:
            try:
                del stock['stock_news']
            except:
                continue

        content = self.prompts['portfolio_manager_user']['prompt'].replace("<data>", str({"general_market_sentiment":
                                                                                              market_sentiment,
                                                                                          "stocks":
                                                                                              stock_analysis}))
        system_prompt = self.prompts['portfolio_manager_system']['prompt']
        response = helper.invoke_model([{
            "role": "user",
            "content": content
        }], system_prompt)

        logger.info(f'Response: {response}')
        database.save_portfolio(response, date)
        logger.info(f'Finished portfolio manager')

    def _get_portfolio_performance(self, portfolio, finance_api):
        portfolio = pd.DataFrame(portfolio)
        total_sum_invested, spy_total_sum_invested = 0, 0
        portfolio_value, spy_portfolio_value = 0, 0
        spy_data, spy_ticker = finance_api.get_history('SPY')
        portfolio_data = []

        for index, row in portfolio.iterrows():
            try:
                stock = row['stock']
                data, ticker = finance_api.get_history(stock)

                buy_date = parser.parse(row['date'] + ' 00:00:00-04:00')
                number_of_shares = row['number_of_shares_to_buy']

                buy_date_closing_price = data.loc[[buy_date]]['Close'].values[0]
                buy_date_value = buy_date_closing_price * number_of_shares
                current_price = ticker.info['currentPrice']
                current_value = current_price * number_of_shares
                performance = round(current_value / buy_date_value, 3)
                total_sum_invested += buy_date_value
                portfolio_value += current_value

                # SPY
                buy_date_spy_price = spy_data.loc[[buy_date]]['Close'].values[0]
                spy_number_of_shares = buy_date_value / buy_date_spy_price
                current_spy_price = spy_ticker.info['open']
                spy_by_date_value = buy_date_spy_price * spy_number_of_shares
                spy_current_value = current_spy_price * spy_number_of_shares
                spy_performance = round(spy_current_value / spy_by_date_value, 3)
                spy_total_sum_invested += round(spy_by_date_value, 2)
                spy_portfolio_value += spy_current_value

                stock_json = {
                    "stock": stock,
                    "buy_date": row['date'],
                    "number_of_shares": number_of_shares,
                    "buy_date_closing_price": buy_date_closing_price,
                    "buy_date_value": buy_date_value,
                    "current_price": current_price,
                    "current_value": current_value,
                    "performance": ((current_value / buy_date_value) - 1) * 100

                }
                portfolio_data.append(stock_json)
            except Exception as e:
                logger.info(e)
                continue
        gain_percentage = ((portfolio_value / total_sum_invested) - 1) * 100
        spy_gain_percentage = ((spy_portfolio_value / spy_total_sum_invested) - 1) * 100

        logger.info(f"Portfolio Gain Percentage: {gain_percentage:.2f}%, SP500 Gain compared: {spy_gain_percentage:.2f}%")
        return pd.DataFrame(portfolio_data)

    def _update_portfolio_and_realize_gains(self, database, finance_api, date, performance):
        portfolio_data = database.get_portfolio_data()
        portfolio_data_without_sold_stocks = self._filter_portfolio_data_without_sold_stocks(portfolio_data)
        portfolio_stocks = self._get_portfolio_stocks(portfolio_data_without_sold_stocks)
        stocks = helper.get_stocks(finance_api)
        analyst_data = database.get_analyst_data(stocks=stocks, date=date)
        sell_stocks = self._get_sell_stocks(portfolio_stocks, analyst_data)
        positions_to_sell, performance_of_stocks_to_sell, total_buy_value, total_sell_value = self._get_positions_and_performance_of_stocks_to_sell(
            portfolio_data_without_sold_stocks, sell_stocks, performance, date)
        gains = self._calculate_gains(total_buy_value, total_sell_value)
        database.save_realized_gains(total_sell_value, total_buy_value, date, gains)
        self._log_performance(gains)
        overall_performance = self._calculate_overall_performance(database.get_realized_gains())
        self._log_overall_performance(overall_performance)
        return performance_of_stocks_to_sell

    def _filter_portfolio_data_without_sold_stocks(self, portfolio_data):
        return [stock for stock in portfolio_data if 'sell_date' not in stock]

    def _get_portfolio_stocks(self, portfolio_data):
        return list(dict.fromkeys([stock['stock'] for stock in portfolio_data]))

    def _get_sell_stocks(self, portfolio_stocks, analyst_data):
        sell_stocks = []
        for recommendation in analyst_data:
            if recommendation['stock'] in portfolio_stocks and recommendation['investment_decision'] != "BUY":
                sell_stocks.append(recommendation['stock'])
        return sell_stocks

    def _get_positions_and_performance_of_stocks_to_sell(self, portfolio_data, sell_stocks, performance, date):
        positions_to_sell = []
        performance_of_stocks_to_sell = []
        total_buy_value = 0
        total_sell_value = 0
        for position in portfolio_data:
            for sell_stock in sell_stocks:
                if sell_stock == position['stock']:
                    positions_to_sell.append(position)
                    for _, row in performance[performance["stock"] == position['stock']].iterrows():
                        performance_of_stocks_to_sell.append(
                            self._create_performance_dict(row, date=date))
                        total_buy_value += row['buy_date_value']
                        total_sell_value += row['current_value']
        return positions_to_sell, performance_of_stocks_to_sell, total_buy_value, total_sell_value

    def _create_performance_dict(self, row, date):
        return {
            "buy_date": row['buy_date'],
            "number_of_shares": row['number_of_shares'],
            "buy_date_closing_price": row['buy_date_closing_price'],
            "current_price": row['current_price'],
            "buy_date_value": row['buy_date_value'],
            "current_value": row['current_value'],
            "performance": row['performance'],
            "stock": row['stock'],
            'sell_date': date
        }

    def _calculate_gains(self, total_buy_value, total_sell_value):
        try:
            return round((total_sell_value / total_buy_value - 1) * 100, 2)
        except:
            return 0

    def _log_performance(self, gains):
        logger.info(f'Performance of realized gains: {gains}')

    def _calculate_overall_performance(self, old_realized_gains):
        all_total_sell_value = sum(gain['total_sell_value'] for gain in old_realized_gains)
        all_total_buy_value = sum(gain['total_buy_value'] for gain in old_realized_gains)
        if all_total_sell_value == 0 and all_total_buy_value == 0:
            return 0
        return round(((all_total_sell_value / all_total_buy_value) - 1) * 100, 2)

    def _log_overall_performance(self, overall_performance):
        logger.info(f'Overall performance of realized gains: {overall_performance}')
