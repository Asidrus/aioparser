import os
from dotenv import load_dotenv
load_dotenv()

PROJECT_NAME = os.getenv('PROJECT')
STORAGE_PATH = os.getenv('PROJECT') + PROJECT_NAME
IP = os.getenv('IP')
PORT = os.getenv('PORT')

# aioparser_results = '/aioparser-results/'
# aioparser_IP = 'localhost'
# aioparser_PORT = 9087