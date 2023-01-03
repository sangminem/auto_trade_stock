from zipfile import ZipFile
import requests
import xmltodict
from io import BytesIO
from dotenv import load_dotenv
import os
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
import datetime
import time
from bs4 import BeautifulSoup
import pandas as pd

load_dotenv()

crtfc_key = os.getenv('CRTFC_KEY')

user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.50 Safari/537.36'

options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('user-agent={0}'.format(user_agent))
browser = webdriver.Chrome(ChromeDriverManager().install(),options=options)

all_data = {}

# 기업 코드 ex) [{'corp_code': '00126380', 'corp_name': '삼성전자', 'stock_code': '005930', 'modify_date': '20220509'}]
def get_corp_code(name=None, match=None):
    global crtfc_key
    url = 'https://opendart.fss.or.kr/api/corpCode.xml'
    params = {'crtfc_key': crtfc_key}
    res = requests.get(url, params=params)
    zipfile_bytes = res.content
    zipfile_obj = ZipFile(BytesIO(zipfile_bytes))
    xmlfile_objs = {name: zipfile_obj.read(name) for name in zipfile_obj.namelist()}
    xml_str = xmlfile_objs['CORPCODE.xml'].decode('utf-8')
    data_dict = xmltodict.parse(xml_str).get('result', {}).get('list')
    result = []

    if match == True:
        for item in data_dict:
            if name == item['corp_name'] and item['stock_code'] is not None:
                result.append(item)
    elif match == False:
        for item in data_dict:
            if name in item['corp_name'] and item['stock_code'] is not None:
                result.append(item)
    else:
        for item in data_dict:
            if item['stock_code'] is not None:
                result.append(item)
    return result

# fs_div = CFS:연결재무제표, OFS:재무제표, sj_div = BS:재무상태표, IS:손익계산서
def get_corp_data_by_api(corp_code, bsns_year, reprt_code, fs_div='OFS', sj_div='IS', all_div=False):
    global crtfc_key
    url = 'https://opendart.fss.or.kr/api/fnlttMultiAcnt.json'
    params = {
        'crtfc_key': crtfc_key,
        'corp_code': corp_code,
        'bsns_year': bsns_year,
        'reprt_code': reprt_code
    }
    res = requests.get(url, params=params).json()
    result = []
    for item in res['list']:
        if all_div:
            result.append(item)
        elif item['fs_div'] == fs_div:
            if item['sj_div'] == sj_div:
                result.append(item)
    return result

def get_corp_data_by_web(corp_code):
    global browser
    if browser is None:
        browser = webdriver.Chrome(ChromeDriverManager().install(), options=webdriver.ChromeOptions())
    now = datetime.datetime.now()
    ymd_from = str(now.year-1) + str(now.month).rjust(2,'0') + str(now.day).rjust(2,'0')
    ymd_to = str(now.year) + str(now.month).rjust(2,'0') + str(now.day).rjust(2,'0')
    data = {
        "textCrpCik": corp_code,
        "startDate": ymd_from,
        "endDate": ymd_to,
        "publicType": "A001"
    }
    base_url = 'https://dart.fss.or.kr'
    res = requests.post(base_url + '/dsab007/detailSearch.ax', data)
    soup = BeautifulSoup(res.content, 'html.parser')
    a_tag = soup.select('.tL > a')
    if len(a_tag) > 0:
        url = base_url + a_tag[0].attrs['href']
        browser.get(url)
        browser.execute_script("document.querySelectorAll('#listTree a').forEach(function(item){if(item.textContent.indexOf('III. 재무에 관한 사항')>-1){item.click();}});")
        time.sleep(0.5)
        soup = BeautifulSoup(browser.page_source, 'html.parser')
        url = base_url + soup.select('#ifrm')[0].attrs['src']
        res = requests.get(url)
        print(url)
        soup = BeautifulSoup(res.content, 'html.parser')
        check_tags = soup.select('p, table')
        return check_tags
    else:
        return None

def get_index_data(data):
    result = []
    for i, tag in enumerate(data):
        if tag.text != '':
            result.append(
                {
                    'index': i,
                    'name': tag.name,
                    'data': tag
                }
            )
    return result

def get_tag_data(data, tag_name):
    result = []
    for tag in data:
        if tag['name'] == tag_name:
            result.append(tag)
    return result

def get_target_data(data, include_words):
    result = []
    for tag in data:
        for word in include_words:
            if word in tag['data'].text:
                result.append(tag)
                break
    return result

def get_df_data(tag):
    dfs = pd.read_html(str(tag['data']))
    df = dfs[0]
    return df

def get_ness_data(data, ness_words):
    result = data
    for word in ness_words:
        result = get_target_data(result, [word])
    return result

def get_custom_data(corp_code):
    row_name_list = ['매출액','당기순이익','영업이익','자본총계','부채총계']
    result = {
        '재무제표': {}
    }
    
    web_data = get_corp_data_by_web(corp_code)
    index_data = get_index_data(web_data)

    # 재무제표
    table_data = get_tag_data(index_data, 'table')
    fs_data = get_ness_data(table_data, row_name_list)

    # 단위
    ness_unit_words = ['단위:']
    ness_unit_data = get_ness_data(index_data, ness_unit_words)
    unit_words = ['백만원', '천원', '원', 'USD']
    unit_data = get_target_data(ness_unit_data, unit_words)
    
    units = []
    for i in range(len(fs_data)):
        for unit in unit_data:
            if i == 0:
                if unit['index'] <= fs_data[i]['index']:
                    print(unit['data'].select('td, p'))
            elif i < len(fs_data):
                if fs_data[i-1]['index'] < unit['index'] <= fs_data[i]['index']:
                    print(unit['data'].select('td, p'))

    # test_data = get_df_data(target_data[0])
    
def insert_data():
    global all_data, row_name_list
    # corp_list = get_corp_code()
    corp_list = [{'corp_code': '00956028', 'corp_name': '엑세스바이오', 'stock_code': '950130', 'modify_date': '20170630'}]
    for corp_info in corp_list:
        print(corp_info)
        get_custom_data(corp_info['corp_code'])

    #     custom_data = {}
    #     if web_data is not None:
    #         custom_data = get_custom_data(web_data)
    #     all_data[corp_info['corp_code']] = {
    #         'name': corp_info['corp_name'],
    #         'stock_code': corp_info['stock_code'],
    #         'data': custom_data
    #     }
    #     time.sleep(1)
    # print(all_data)

    # corp_data = get_corp_data_by_api(corp_info['corp_code'], '2019', '11011', all_div=False)
    # for data in corp_data:
    #     print(data)

insert_data()

# https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20220322000596
# https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20220316001424
# https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20220321001331
# https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20220308000798