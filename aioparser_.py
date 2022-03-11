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
            self.saveAsHtml(self.fileNameResults, self.result)
            self.writefile(self.fileNameResults, self.result)

    def readfile(self, fname):
        with open(fname, "r") as read_file:
            return json.load(read_file)

    def writefile(self, fname, data):
        with open(fname, "w", encoding='utf-8') as write_file:
            json.dump(data, write_file, indent=4, ensure_ascii=False)
            print(f'сохранил файл в {fname}')

    def saveAsHtml(self, fname, data):
        html = """<html lang="ru">
                    <header>
                        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
                    </header>
                    <body>\n"""
        for key in data.keys():
            html = html + '<p>' + key + "</p><br>\n"
            for url in data[key]:
                html = html + f'<a href="{url}" target="_blank">{url}</a><br>\n'
        html = html + """</body>
                        </html>"""
        with open(fname.replace(".json", "") + ".html", 'w', encoding='utf-8') as file:
            file.write(html)

    def takeLink(self):
        yield from self.links['internal']

    async def parsing(self):
        async with aiohttp.ClientSession() as session:
            for link in self.takeLink():
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
                        # html = html.lower()

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
        for block in blocks[15:16]:
            text_block = soup.find(**block)
            if text_block is not None:
                text_block = str(text_block).replace(str(soup.find(name="noindex")), '')
                text = text + str(text_block).lower()
            else:
                print(f"{block} is not found")

        res = {}

        for p in pattern[0:3]:
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


def googleSheets():
    from oauth2client.service_account import ServiceAccountCredentials
    import httplib2
    import apiclient.discovery
    credentials = ServiceAccountCredentials.from_json_keyfile_name("/home/kali/python/Aioparser/stable-ring-316114-8acf36454762.json",
                                                                   ['https://www.googleapis.com/auth/spreadsheets',
                                                                    'https://www.googleapis.com/auth/drive'])
    httpAuth = credentials.authorize(httplib2.Http())
    service = apiclient.discovery.build('sheets', 'v4', http=httpAuth)
    ids = service.spreadsheets().values().get(spreadsheetId="1Vrrel1Z3TnH_1SlFqS4KXRAAEYouD7ldkqLpjY1gUP8",
                                              range=f"Продажи !A2:A564",
                                              majorDimension='COLUMNS').execute()["values"][0]
    return ids


def googleSheetsWrite(data):
    from oauth2client.service_account import ServiceAccountCredentials
    import httplib2
    import apiclient.discovery
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "/home/kali/python/Aioparser/stable-ring-316114-8acf36454762.json",
        ['https://www.googleapis.com/auth/spreadsheets',
         'https://www.googleapis.com/auth/drive'])
    httpAuth = credentials.authorize(httplib2.Http())
    service = apiclient.discovery.build('sheets', 'v4', http=httpAuth)
    data = [['23500', '15700'], ['17400', '9100'], ['21600', '13824'], ['7676', '4860'], ['14500', '8700'], ['22700', '15045'], ['33000', '24750'], ['6900', '3680'], ['12700', '7900'], ['10700', '5434'], ['10700', '4333'], ['23700', '11307'], ['22356', '15876'], ['17100', '10300'], ['12500', '6000'], ['3200', '1461'], ['26900', '13900'], ['9200', '7800'], ['9660', '3780'], ['7200', '3920'], ['23500', '15300'], ['17900', '9500'], ['22800', '12665'], ['8200', '3570'], ['14700', '6700'], ['99000', '74250'], ['22800', '11900'], ['6900', '3600'], ['49100', '42100'], ['9200', '3746'], ['10700', '4186'], ['18500', '13500'], ['9100', '4480'], ['11700', '7900'], ['7676', '4860'], ['6900', '3266'], ['N/A', 'N/A'], ['6900', '2292'], ['10700', '5067'], ['23500', '15300'], ['46332', '37584'], ['17955', '6932'], ['10700', '5214'], ['12500', '6700'], ['10700', '4186'], ['23700', '10605'], ['10500', '8900'], ['17100', '8900'], ['10700', '3746'], ['23700', '14300'], ['17955', '7367'], ['9844', '3852'], ['24084', '17280'], ['6900', '2056'], ['6900', '2650'], ['21735', '13545'], ['20736', '15120'], ['21492', '15120'], ['9200', '4900'], ['49634', '38180'], ['12500', '6000'], ['N/A', 'N/A'], ['9200', '7360'], ['25200', '21366'], ['9200', '4039'], ['17100', '10260'], ['17100', '8254'], ['15600', '6400'], ['17100', '9400'], ['23760', '17279'], ['4000', '1755'], ['7464', '4680'], ['7500', '3500'], ['6900', '2056'], ['23700', '16900'], ['39500', '33150'], ['12700', '7900'], ['20055', '6630'], ['11700', '7600'], ['4500', '1755'], ['19100', '12100'], ['6900', '2292'], ['18297', '8832'], ['69000', '58650'], ['17100', '8700'], ['12500', '7500'], ['12500', '6000'], ['9200', '3746'], ['17100', '8700'], ['26985', '19641'], ['9200', '6400'], ['3424', '1563'], ['9200', '3280'], ['12500', '6700'], ['73000', '52500'], ['10700', '5434'], ['7383', '3064'], ['17100', '8900'], ['17000', '14450'], ['22800', '12495'], ['3200', '2100'], ['7100', '2056'], ['12500', '6700'], ['9200', '4300'], ['7100', '3900'], ['10700', '5827'], ['17100', '8900'], ['18795', '9762'], ['3200', '1755'], ['23700', '13632'], ['8345', '5400'], ['11445', '7508'], ['7100', '3800'], ['17100', '10300'], ['12500', '6000'], ['15600', '12480'], ['None', 'None'], ['24885', '9578'], ['4387', '1878'], ['26985', '18187'], ['12500', '6000'], ['6200', '4340'], ['12500', '6700'], ['7100', '2864'], ['15900', '8400'], ['17100', '8100'], ['17900', '7353'], ['3675', '1588'], ['10700', '3598'], ['98000', '83300'], ['6900', '2056'], ['10700', '8000'], ['3424', '1563'], ['7200', '2292'], ['24100', '12600'], ['10700', '4774'], ['27500', '18300'], ['3500', '1520'], ['30996', '22464'], ['9200', '2864'], ['15000', '10800'], ['5700', '2065'], ['6900', '3100'], ['3200', '1900'], ['9200', '2645'], ['10900', '9800'], ['6900', '5500'], ['31500', '26585'], ['25359', '12680'], ['18100', '9000'], ['29355', '19570'], ['18500', '12700'], ['17100', '8100'], ['9900', '4500'], ['16380', '12042'], ['7200', '3370'], ['26985', '18892'], ['9200', '7360'], ['17100', '8217'], ['17100', '10300'], ['4100', '3300'], ['12500', '6400'], ['22800', '9900'], ['9200', '3120'], ['None', 'None'], ['17100', '8100'], ['9844', '3064'], ['6900', '3024'], ['28635', '19636'], ['29295', '20895'], ['3200', '1719'], ['6900', '2056'], ['12500', '6700'], ['15855', '10863'], ['9200', '6900'], ['25700', '12100'], ['24855', '10840'], ['25900', '15100'], ['17100', '8100'], ['3900', '3780'], ['19656', '14039'], ['3200', '1319'], ['3900', '2500'], ['4300', '3440'], ['72000', '61200'], ['61000', '49500'], ['49900', '36424'], ['10700', '4333'], ['3424', '1563'], ['10098', '5940'], ['17100', '10300'], ['4500', '1755'], ['29600', '23700'], ['58000', '40600'], ['12500', '6700'], ['12500', '6700'], ['7400', '3990'], ['15600', '14500'], ['7200', '2644'], ['25700', '11925'], ['N/A', 'N/A'], ['8200', '6560'], ['6900', '2056'], ['17100', '8779'], ['16380', '7844'], ['27216', '19440'], ['26985', '18671'], ['9800', '4700'], ['8500', '6800'], ['17400', '9100'], ['5900', '3700'], ['10700', '8000'], ['9200', '4333'], ['15100', '9900'], ['8200', '3305'], ['9200', '6440'], ['9200', '5500'], ['3500', '1719'], ['12500', '6700'], ['58200', '43200'], ['9200', '6900'], ['19100', '13370'], ['15855', '10863'], ['15600', '8300'], ['6900', '3990'], ['6900', '2056'], ['17100', '8900'], ['6900', '5200'], ['26985', '20848'], ['2730', '2065'], ['12500', '6400'], ['6480', '4428'], ['7200', '2900'], ['18795', '11850'], ['6900', '3400'], ['12500', '6000'], ['9200', '6400'], ['12500', '6700'], ['6200', '3410'], ['12500', '6700'], ['23700', '15100'], ['11700', '5900'], ['8800', '5700'], ['87000', '69600'], ['11700', '6900'], ['41895', '31364'], ['4387', '1878'], ['17100', '7500'], ['23700', '12900'], ['17100', '8900'], ['25900', '14300'], ['6588', '4752'], ['4000', '1719'], ['15600', '12500'], ['9200', '7820'], ['21900', '14500'], ['3900', '2590'], ['24855', '10249'], ['9200', '5500'], ['25359', '3536'], ['4000', '1120'], ['7900', '5900'], ['17100', '7900'], ['9200', '4900'], ['17000', '12750'], ['4500', '1755'], ['7200', '3000'], ['3200', '1719'], ['12500', '6700'], ['6900', '2056'], ['7100', '2056'], ['85000', '68000'], ['6900', '2864'], ['12500', '6000'], ['35340', '26180'], ['12500', '6400'], ['7100', '4300'], ['3200', '2065'], ['17955', '14061'], ['6500', '2380'], ['9200', '6900'], ['3200', '1461'], ['17100', '8900'], ['17100', '8100'], ['17100', '8900'], ['7100', '2056'], ['39900', '29900'], ['3500', '1512'], ['16380', '7607'], ['18795', '8292'], ['6900', '3200'], ['3200', '1755'], ['10114', '5244'], ['26985', '16239'], ['None', 'None'], ['6900', '4830'], ['3200', '1461'], ['7200', '2938'], ['7200', '3400'], ['39100', '29700'], ['16380', '5614'], ['4988', '3563'], ['12500', '6700'], ['12500', '6700'], ['17100', '9400'], ['6900', '2205'], ['None', 'None'], ['None', 'None'], ['17955', '7957'], ['17100', '7565'], ['12500', '6700'], ['17100', '8900'], ['22785', '17605'], ['None', 'None'], ['36960', '29657'], ['7500', '2975'], ['17955', '11961'], ['44900', '36100'], ['17400', '10100'], ['15600', '6000'], ['9200', '6440'], ['N/A', 'N/A'], ['4500', '1902'], ['23100', '10700'], ['17100', '8100'], ['6000', '3200'], ['6500', '3920'], ['None', 'None'], ['18795', '10937'], ['22785', '14813'], ['11700', '5900'], ['6900', '3100'], ['9200', '5500'], ['26985', '15356'], ['24045', '17787'], ['4000', '1755'], ['7200', '2292'], ['9200', '2994'], ['7900', '6300'], ['3500', '1512'], ['7100', '2056'], ['89000', '71200'], ['17100', '8100'], ['7900', '4500'], ['9200', '3305'], ['9200', '8300'], ['4000', '2100'], ['5000', '2196'], ['7100', '2056'], ['7500', '4400'], ['22260', '16424'], ['18795', '6651'], ['6900', '2380'], ['18297', '5721'], ['15700', '8100'], ['9200', '5980'], ['9200', '2056'], ['17100', '8254'], ['24885', '12591'], ['17955', '7454'], ['24885', '14001'], ['17100', '8900'], ['25900', '14300'], ['23100', '10700'], ['23100', '12100'], ['N/A', 'N/A'], ['4350', '2872'], ['15600', '13300'], ['3500', '1840'], ['3500', '2800'], ['N/A', 'N/A'], ['6900', '3024'], ['3500', '1512'], ['28455', '20895'], ['25900', '17400'], ['10700', '7490'], ['21900', '14900'], ['27900', '17100'], ['4100', '2065'], ['3200', '2065'], ['18795', '11048'], ['N/A', 'N/A'], ['3200', '1021'], ['9200', '3058'], ['3200', '1461'], ['3200', '1461'], ['12500', '6700'], ['18795', '9372'], ['15600', '6400'], ['N/A', 'N/A'], ['15600', '6000'], ['7200', '3033'], ['9900', '6334'], ['6696', '5184'], ['12500', '6700'], ['32000', '25600'], ['17100', '10300'], ['23700', '14300'], ['12500', '6000'], ['None', 'None'], ['4000', '2500'], ['None', 'None'], ['9200', '6900'], ['26985', '11697'], ['N/A', 'N/A'], ['9200', '3110'], ['7100', '3300'], ['18795', '6844'], ['18795', '7615'], ['17955', '13058'], ['24885', '9578'], ['13900', '8100'], ['17100', '7500'], ['6900', '2205'], ['7500', '3700'], ['14700', '12300'], ['11600', '5900'], ['23100', '10700'], ['17100', '8900'], ['25900', '14300'], ['12500', '6000'], ['25900', '15100'], ['7100', '3400'], ['7500', '3990'], ['None', 'None'], ['30000', '25100'], ['6900', '5200'], ['6900', '2678'], ['17955', '7624'], ['3900', '2590'], ['18795', '10613'], ['24885', '17565'], ['15600', '7335'], ['36960', '29657'], ['6900', '2380'], ['None', 'None'], ['6900', '2093'], ['22995', '15645'], ['7200', '2696'], ['17900', '16767'], ['26985', '17565'], ['6900', '2205'], ['7100', '2056'], ['18795', '11048'], ['6900', '3080'], ['N/A', 'N/A'], ['7200', '4700'], ['N/A', 'N/A'], ['8100', '3900'], ['20055', '13716'], ['10500', '5500'], ['10500', '5500'], ['8800', '3990'], ['9200', '2864'], ['9900', '6334'], ['23700', '14300'], ['None', 'None'], ['6900', '2419'], ['12500', '6700'], ['7400', '3990'], ['4000', '2065'], ['3200', '1461'], ['9200', '2864'], ['None', 'None'], ['6900', '2696'], ['6900', '3370'], ['6900', '2678'], ['24885', '9578'], ['9200', '3120'], ['3500', '1512'], ['13900', '9300'], ['12500', '6700'], ['9200', '2409'], ['3200', '1719'], ['10700', '6960'], ['9200', '4234'], ['6900', '2594'], ['17100', '5347'], ['12500', '5100'], ['12500', '6000'], ['12500', '6000'], ['17100', '8100'], ['12500', '5000'], ['15855', '10863'], ['3500', '1512'], ['6900', '3024'], ['None', 'None'], ['17100', '8100'], ['22859', '12926'], ['6900', '2678'], ['17955', '12042'], ['20000', '16650'], ['3500', '1719'], ['7200', '2900'], ['3200', '1719'], ['None', 'None'], ['7200', '2205'], ['3200', '1461'], ['3200', '1461'], ['6900', '1986'], ['N/A', 'N/A'], ['7200', '4500'], ['16380', '11820'], ['26985', '15356'], ['6900', '2592'], ['6900', '1836'], ['6900', '2262'], ['6900', '1856'], ['5700', '2176'], ['None', 'None'], ['15600', '6000'], ['None', 'None'], ['3500', '1512'], ['3200', '1719'], ['None', 'None'], ['7950', '5300'], ['6900', '3450'], ['23700', '15200'], ['23700', '15200'], ['17900', '9400'], ['12500', '6700'], ['N/A', 'N/A'], ['7100', '3500'], ['12500', '6700'], ['64680', '39900'], ['6900', '3200'], ['7200', '2864'], ['7200', '5760'], ['8200', '6560'], ['7200', '2056'], ['6900', '2864'], ['3500', '1512'], ['6900', '2594'], ['9200', '3387'], ['None', 'None'], ['6900', '2696'], ['None', 'None'], ['6900', '2594'], ['None', 'None'], ['None', 'None'], ['18795', '11349'], ['15600', '7200'], ['None', 'None'], ['N/A', 'N/A'], ['4100', '2065'], ['9200', '2545'], ['3200', '2065'], ['35385', '12994'], ['12050', '5100'], ['12500', '5100'], ['12500', '6000'], ['12500', '5000'], ['12500', '5000'], ['25900', '15900'], ['12500', '5100'], ['12500', '5000'], ['12500', '5000'], ['N/A', 'N/A'], ['N/A', 'N/A'], ['N/A', 'N/A'], ['N/A', 'N/A'], ['N/A', 'N/A'], ['4000', '3600']]
    print(len(data))
    res = service.spreadsheets().values().update(spreadsheetId="1Vrrel1Z3TnH_1SlFqS4KXRAAEYouD7ldkqLpjY1gUP8",
                                                range=f"Продажи !F2:G564",
                                                valueInputOption="USER_ENTERED",
                                                body={"values": data}).execute()
    print(res)

async def bitrix(ids):
    import re
    res = []
    for id in ids:
        print(id)
        try:
            int(id)
        except:
            res.append(["N/A", "N/A"])
            continue
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://vgaps.ru/seminar/{id}") as response:
                html = await response.text('windows-1251', errors="ignore")
                soup = BeautifulSoup(html, "lxml")
                fullPrice = soup.find('div', attrs={"class": "full-price"})
                fullPrice = "None" if fullPrice is None else "".join(re.findall("[0-9]*", fullPrice.text))
                actionPrice = soup.find('div', attrs={"class": "action-price"})
                actionPrice = "None" if actionPrice is None else "".join(re.findall("[0-9]*", actionPrice.text))
                res.append([fullPrice, actionPrice])
    print(res)


async def task1056723(html: str, link: dict):
    if 'news' not in link["url"]:
        res = {}
        text = html.lower()
        count1 = len([ind for ind in find_all(text, "пожарн")])
        count2 = len([ind for ind in find_all(text, "пожарно-техническому")])
        if count1 > count2:
            p = "пожарн"
            print({p: link["url"]})
            res[p] = link["url"]
        for p in ['птм']:
            if p.lower() in text:
                print({p: link["url"]})
                res[p] = link["url"]
        return res
    else:
        return {}

if __name__ == '__main__':
    parser = aioparser('https://urgaps.ru/',
                       storagePath='/home/kali/autotest-results/',
                       forceParsing=True,
                       fileNameResults='urgaps',
                       adaptive=False,
                       searcher=task1056723)
    asyncio.run(parser.run())
    # ids = googleSheets()
    # res = asyncio.run(bitrix(ids))
    # googleSheetsWrite(res)
    # googleSheetsWrite([["1","2"],["3","4"]])