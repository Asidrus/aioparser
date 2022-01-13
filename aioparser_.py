import asyncio
import aiohttp
import os
import sys

sys.path.append('/home/kali/autotest/')
import json
from io import StringIO
from lxml import etree
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from config import *


def putInDict(url, link, dictionary):
    flag = False
    for _link in dictionary:
        if _link["url"] == url:
            flag = True
            if link["url"] not in _link["from"]:
                _link["from"].append(link["url"])
            break
    if not flag:
        dictionary.append({"url": url, "from": [link["url"]]})


def find_all(a_str, sub):
    start = 0
    while True:
        start = a_str.find(sub, start)
        if start == -1: return
        yield start
        start += len(sub)


headers = {
    "User-Agent": 'Mozilla/5.0 (Windows Phone 10.0; Android 4.2.1; Microsoft; Lumia 640 XL LTE) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Mobile Safari/537.36 Edge/12.10166'}


class aioparser:
    parser = None
    site = ''
    pattern = []
    links = {}
    result = {}
    fileNameLinks = ''
    fileNameResults = ''

    def __init__(self, site, adaptive=False,
                 forceParsing=False,
                 storagePath="",
                 pattern=None,
                 searcher=None,
                 fileNameResults='',
                 timeout: timedelta = timedelta(hours=23)):
        # берем главную страницу
        inds = [ind for ind in find_all(site, '/')]
        if len(inds) > 2:
            self.site = site[:[ind for ind in find_all(site, '/')][2]]
        else:
            self.site = site
        # находим домен
        start = [ind for ind in find_all(self.site, '/')][1] + 1
        end = [ind for ind in find_all(self.site, '.')][-1]
        domain = self.site[start:end] + "_adaptive" if adaptive else self.site[start:end]
        # имена файлам
        self.fileNameLinks = storagePath + domain + "_links.json"
        self.fileNameResults = storagePath + domain + "_results.json" if (fileNameResults == "") \
            else storagePath + fileNameResults + ".json"
        # инициализируем переменные
        self.refresh()
        # работаем с адаптивом? t/f
        self.headers = headers if adaptive else None
        # принудильно парсим даже если есть файл
        self.forceParsing = forceParsing
        # паттерны, которые будем искать
        self.pattern = pattern
        # функция поиска/фильтрации, которая передается из вне
        self.searcher = searcher

        self.parser = etree.HTMLParser()
        self.timeout = timeout
        self.isNew = lambda dt: (datetime.now() - dt) < self.timeout

    def __str__(self):
        return f"site='{self.site}', pattern='{self.pattern}'"

    def refresh(self):
        self.links = {"internal": [{"url": self.site, "from": []}], "external": [], "resources": [], "errors": []}
        self.result = {}
        if self.pattern is not None:
            for p in self.pattern:
                self.result[p] = []

    async def run(self):
        if not self.forceParsing:
            if os.path.exists(self.fileNameLinks):
                createdData = datetime.fromtimestamp(os.path.getmtime(self.fileNameLinks))
                if self.isNew(createdData):
                    self.links = self.readfile(self.fileNameLinks)
                else:
                    self.forceParsing = True
            else:
                self.forceParsing = True

        if self.forceParsing:
            self.refresh()
        await self.parsing()
        self.writeResults()

    def writeResults(self):
        self.writefile(self.fileNameLinks, self.links)
        if self.pattern or self.searcher:
            self.writefile(self.fileNameResults, self.result)

    def readfile(self, fname):
        with open(fname, "r") as read_file:
            return json.load(read_file)

    def writefile(self, fname, data):
        with open(fname, "w", encoding='utf-8') as write_file:
            json.dump(data, write_file, indent=4, ensure_ascii=False)
            print(f'сохранил файл в {fname}')

    def takeLink(self):
        yield from self.links['internal']

    async def parsing(self):
        async with aiohttp.ClientSession() as session:
            for link in self.takeLink():
            # for link in [{"url": "https://niidpo.ru/seminar/9584"}]:
                print(link["url"])
                try:
                    async with session.get(link["url"], headers=self.headers) as response:
                        header = response.headers["Content-Type"]
                        if "text/html" not in header:
                            continue
                        encoding = header[header.find("=") + 1:]
                        try:
                            html = await response.text(encoding, errors="ignore")
                        except Exception as e:
                            html = await response.text('windows-1251', errors="ignore")
                            print(f"Ошибка в кодировке {e} {link['url']} {response.headers['Content-Type']}")
                        html = html.lower()

                        if self.forceParsing:
                            # Собираем ссылки ссылки
                            try:
                                await self.getLinks(html, link)
                            except Exception as e:
                                print(f"Ошибка в парсинге {e} {link['url']}")
                                raise e

                        if self.pattern:
                            try:
                                await self.search(html, link)
                            except Exception as e:
                                print(f"Ошибка в поиске {e} {link['url']}")

                        if self.searcher:
                            try:
                                res = await self.searcher(html, link)

                                for key in res.keys():
                                    if key in self.result.keys():
                                        self.result[key].append(res[key])
                                    else:
                                        self.result[key] = [res[key]]
                                # if len(res.keys()):
                                #     print(self.result)
                            except Exception as e:
                                print(f"Error searcher for url = {link['url']} {e}")

                except Exception as e:
                    self.links['errors'].append({"url": link["url"], "error": str(e)})
                    print(e)

    async def getLinks(self, html, link):
        tree = etree.parse(StringIO(html), parser=self.parser)
        a_tags = tree.xpath("//a[@href]")
        for a in a_tags:
            url = a.get("href", "")
            if url in ("", "/", link["url"], link["url"] + "/", link["url"].replace(self.site, "")) or ("#" in url) or (
                    "?" in url):
                continue
            if url.startswith("/"):
                url = self.site + url
                putInDict(url, link, self.links['internal'])
            elif url.startswith("http"):
                putInDict(url, link, self.links['external'])
            else:
                putInDict(url, link, self.links['resources'])

    async def search(self, html, link):
        for p in self.pattern:
            if p.lower() in html:
                self.result[p].append(link["url"])
                # print({p: link["url"]})


async def searcher_example(html, link):
    if "/seminar" in link["url"]:
        soup = BeautifulSoup(html, "lxml")
        blocks = [
            # niidpo 0-4
            {'name': 'div', "attrs": {"class": "course-objective-inf"}},
            {'name': 'div', "attrs": {"class": "wher-work-unit bg-unit"}},
            {'name': 'div', "attrs": {"class": "excellence-list"}},
            {'name': 'div', "attrs": {"id": "block_content"}},
            # urgaps 4-12
            {'name': 'div', "attrs": {"class": "crs-features-box"}},
            {'name': 'div', "attrs": {"id": "crs-task-row"}},
            {'name': 'div', "attrs": {"id": "crs-get-consult-row"}},
            {'name': 'div', "attrs": {"id": "crs-vacancies-box"}},
            {'name': 'div', "attrs": {"id": "crs-whom-section"}},
            {'name': 'div', "attrs": {"id": "crs-learn-section"}},
            {'name': 'div', "attrs": {"id": "crs-work-section"}},
            {'name': 'div', "attrs": {"id": "block_content"}},
            # vgaps 12-13
            {'name': 'div', "attrs": {"id": "block_content_new"}},
            # adpo 13-14
            {'name': 'div', "attrs": {"id": "tab1"}},
            # dpomipk 14-15
            {'name': 'div', "attrs": {"id": "block_content"}},
            # edu.bakalavr-magistr 15-16
            {'name': 'div', "attrs": {"id": "block_content"}},
        ]
        pattern = ['бессрочн', 'библиоклуб', 'biblioclub', 'месяц']

        text = ''
        for block in blocks[4:12]:
            text_block = soup.find(**block)
            if text_block is not None:
                text = text + str(text_block).lower()
            else:
                print(f"{block} is not found")

        res = {}

        for p in pattern[:]:
            if p.lower() in text:
                print({p: link["url"]})
                res[p] = link["url"]
        return res

        # content_old = soup.find('div', attrs={"class": "course-objective-inf"})
        # block = soup.find('div', attrs={'class': 'wher-work-unit bg-unit'})
        # slick = soup.find('div', attrs={'class': 'crs-features-box'})
        # content_new = soup.find('div', attrs={'id': 'crsTab_1'})
        #
        # res = {}
        #
        # for p in pattern:
        #     if p.lower() in (str(content_old)+str(block)+str(slick)+str(content_new)).lower():
        #         print({p: link["url"]})
        #         res[p] = link["url"]
        return res
    else:
        return {}


if __name__ == '__main__':
    parser = aioparser('https://urgaps.ru/',
                       storagePath='/home/kali/autotest-results/',
                       forceParsing=True,
                       fileNameResults='urgaps',
                       searcher=searcher_example)
    asyncio.run(parser.run())
