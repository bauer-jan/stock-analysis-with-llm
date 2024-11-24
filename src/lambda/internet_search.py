import json
import requests
from googlesearch import search
from bs4 import BeautifulSoup
from aws_lambda_powertools import Logger
import boto3
import random

logger: Logger = Logger(service="internet_search")
client = boto3.client('lambda')


def get_page_content(url):
    try:
        response = requests.get(url, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()

        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        cleaned_text = ';'.join(chunk for chunk in chunks if chunk)
        return cleaned_text
    except requests.RequestException as e:
        logger.info(f"Request error while fetching {url}: {e}")
    except Exception as e:
        logger.info(f"Error while processing content from {url}: {e}")
    return None


def search_google(query, num_results=10, sleep_interval=5):
    try:
        return [j for j in search(query, num_results=num_results, sleep_interval=sleep_interval)]
    except Exception as e:
        logger.info(f"Error during Google search: {e}")
        return []


def handle_search(event):
    input_text = event.get('inputText', '')

    urls_to_scrape = search_google(input_text)
    results = []

    for url in urls_to_scrape[:8]:
        logger.info(f"URL: {url}")
        content = get_page_content(url)
        if content:
            results.append(content)

    return {"results": ";".join(results)}


def lambda_handler(event, context):
    logger.info(f"Agent Event: {event}")

    response_code = 200
    if event.get('apiPath') == '/search':
        result = handle_search(event)
    else:
        response_code = 404
        result = {"error": "Unrecognized API path"}

    result_json = json.dumps(result)

    if len(result_json) > 22000:
        logger.info("Response too big, trimming to 22k chars")
        result_json = result_json[:22000]

    response_body = {
        'application/json': {
            'body': result_json
        }
    }

    action_response = {
        'actionGroup': event.get('actionGroup'),
        'apiPath': event.get('apiPath'),
        'httpMethod': event.get('httpMethod'),
        'httpStatusCode': response_code,
        'responseBody': response_body
    }

    api_response = {
        'messageVersion': '1.0',
        'response': action_response
    }

    logger.info(f"Response: {action_response}")

    if random.choice([1, 2]) == 1:
        logger.info("Updating lambda configuration for new execution environment")
        client.update_function_configuration(
            FunctionName='BedrockAgentInternetSearch',
            Timeout=random.choice(range(600, 700)),
            MemorySize=random.choice(range(4048, 5048)),
        )

    return api_response
