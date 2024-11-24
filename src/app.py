import warnings
import configparser
import os
from aws_lambda_powertools import Logger
from helper.stock_analyst import StockAnalyst
from helper.finance_api import FinanceService
from helper.database import DatabaseService
from helper.portfolio_manager import PortfolioManager

# Suppress FutureWarnings
warnings.simplefilter(action='ignore', category=FutureWarning)

logger: Logger = Logger(service="app")

config = configparser.ConfigParser()
config.read('config.ini')

stock_analyst: StockAnalyst = StockAnalyst()
portfolio_manager: PortfolioManager = PortfolioManager()
finance_api: FinanceService = FinanceService(config)
database: DatabaseService = DatabaseService()

ROLE = os.getenv("ROLE", "PORTFOLIO_MANAGER")


def main() -> None:
    """
    Main function to execute stock analysis and portfolio management.
    """

    if ROLE == 'STOCK_ANALYST':
        stock_analyst.stock_analysis(finance_api, database)
    elif ROLE == 'PORTFOLIO_MANAGER':
        portfolio_manager.manage_portfolio(finance_api, database)
    else:
        raise ValueError(f'ROLE {ROLE} not found')


if __name__ == "__main__":
    main()
