import os
from dotenv import load_dotenv
load_dotenv()

PROJECT_NAME = os.getenv('PROJECT')
STORAGE_PATH = os.getenv('STORAGE')
IP = os.getenv('IP')
PORT = os.getenv('PORT')

# aioparser_results = '/aioparser-results/'
# aioparser_IP = 'localhost'
# aioparser_PORT = 9087