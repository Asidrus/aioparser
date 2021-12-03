import asyncio
import sys
import pathlib
sys.path.insert(-1, str(pathlib.Path(__file__).parent.resolve()))
from aioparser import aioparser
from network import Server
from config import IP, PORT


def genStr(language='en', register=True, numbers=True, length=20):
    import random
    rus = 'абвгдежзийклмнопростуфхцчшщыэюя'
    en = 'abcdefghijklmnopqrstuvwxyz'
    num = '0123456789'
    mass = ''
    if language == 'en':
        mass = mass + en
    elif language == 'ru':
        mass = mass + rus
    if register:
        mass = mass + mass.upper()
    if numbers:
        mass = mass + num
    mass = [sym for sym in mass]
    result = ''
    for i in range(length):
        result += random.choice(mass)
    return result


async def handler(**kwargs):
    print(kwargs)
    if kwargs['contentType'] == 'json':
        content = kwargs['content']
        parser = aioparser(content['site'], content['patterns'], content['adaptive'].lower() == 'true', parse=True, autosave=genStr())
        loop = asyncio.get_event_loop()
        loop.create_task(parser.run())
        asyncio.set_event_loop(loop)
        return {'content': {'data': parser.autosave}}


def main():
    server = Server('localhost', 9087, handler=handler)
    loop = asyncio.get_event_loop()
    loop.create_task(server.runSever())
    asyncio.run(server.runSever())


async def handler2(**kwargs):
    print(kwargs)


def main2():
    from network import Client
    data = {'site': 'https://pentaschool.ru', 'patterns': ["витковский"], 'adaptive': 'False'}
    client = Client(IP, PORT, handler=handler2)
    asyncio.run(client.send(content=data))


if __name__ == '__main__':
    # if sys.argv[1] == '1':
    #     main()
    # else:
    #     main2()
    main()