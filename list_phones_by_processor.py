import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import sys

FETCH_DELAY_MS = 100
FETCH_RETRY_MS = 5000

bands_query_list = [
    'fe_bands-nr-b78-3500',
    'fe_bands-nr-b41-2500'
]

processors_query_list = [
    'Qualcomm Snapdragon 865',
    'Qualcomm Snapdragon 865+',
    'Qualcomm Snapdragon 870',
    'Qualcomm Snapdragon 888',
    'Qualcomm Snapdragon 888+',
    'Qualcomm Snapdragon 8 Gen1',
    'Qualcomm Snapdragon 8+ Gen 1',
    'Qualcomm Snapdragon 4 Gen1',
    'Qualcomm Snapdragon 480',
    'Qualcomm Snapdragon 690 5G',
    'Qualcomm Snapdragon 695 5G',
    'Qualcomm Snapdragon 750G',
    'Qualcomm Snapdragon 765',
    'Qualcomm Snapdragon 778G',
    'Qualcomm Snapdragon 780G',
    'Qualcomm Snapdragon 855',
    'Qualcomm Snapdragon 855+',
    'Qualcomm Snapdragon 860',
    'Qualcomm Snapdragon 870',
    'Qualcomm Snapdragon 4 Gen2',
    'Qualcomm Snapdragon 8 Gen2',
    'Apple A14',
    'Apple A15',
    'Dimensity 700',
    'Dimensity 800',
    'Dimensity 900',
    'Dimensity 810',
    'Dimensity 820',
    'Dimensity 930',
    'Dimensity 1050',
    'Dimensity 1100',
    'Dimensity 1200'
]

def filter_response(html, attr_filter, attr_filter_value, child_level=0, attr_to_add=None):
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    for tag in soup.find_all(attrs={attr_filter: attr_filter_value}):
        # Go down child_level
        t = tag
        for _ in range(child_level):
            if t and t.contents:
                t = t.contents[0]
            else:
                t = None
                break
        if t:
            if attr_to_add:
                results.append((t.get_text(strip=True), t.get(attr_to_add)))
            else:
                results.append(t.get_text(strip=True))
    return results

async def fetch_with_retry(session, url, retry_delay=FETCH_RETRY_MS, max_retries=5):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://www.kimovil.com/en/compare-smartphones',
    }
    for attempt in range(max_retries):
        async with session.get(url, headers=headers) as resp:
            if resp.status == 429:
                print('Too many requests, trying again in {} seconds'.format(retry_delay // 1000))
                await asyncio.sleep(retry_delay / 1000)
                continue
            if resp.status == 403:
                print(f'403 Forbidden for {url}. Trying again in {retry_delay // 1000} seconds.')
                await asyncio.sleep(retry_delay / 1000)
                continue
            try:
                return await resp.json()
            except Exception as e:
                text = await resp.text()
                print(f'Error decoding JSON from {url}: {e}\nResponse text (truncated): {text[:500]}')
                return None
    print('Failed to fetch after retries:', url)
    return None

async def fill_proc_pages(session, proc_list, proc_name, start_page, band_filter, processors_list):
    band_str = ''
    if band_filter:
        band_str = ',' + band_filter
    if start_page > 0:
        suffix = f"{band_str},page.{start_page+1}?xhr=1"
    else:
        suffix = f"{band_str}?xhr=1"
        if band_str:
            print(f'\n=============== "{proc_name}" Band:"{band_filter}" ===============')
        else:
            print(f'\n=============== "{proc_name}" ===============')
    url = f'https://www.kimovil.com/en/compare-smartphones/f_dpg+id.{processors_list[proc_name]}{suffix}'
    print(url)
    res_json = await fetch_with_retry(session, url)
    if not res_json:
        print('   ---> Failed')
        return
    if res_json.get('page_results', 0) == 0:
        print('   ---> OK')
        return
    if proc_list[proc_name][band_filter].get(start_page) is None:
        proc_list[proc_name][band_filter][start_page] = res_json['content']
    print(f'   ---> Fetched Page {start_page+1}')
    next_page_url = res_json.get('next_page_url')
    if next_page_url:
        try:
            new_page_idx = int(next_page_url.split('.')[-1]) - 1
        except Exception:
            return
        await asyncio.sleep(FETCH_DELAY_MS / 1000)
        await fill_proc_pages(session, proc_list, proc_name, new_page_idx, band_filter, processors_list)
    else:
        print('   ---> OK')

async def fill_all_proc_pages(session, proc_query_list, band_query_list, processors_list):
    for proc_name, proc_pages in proc_query_list.items():
        for band_filter in proc_pages.keys():
            await fill_proc_pages(session, proc_query_list, proc_name, 0, band_filter, processors_list)
            await asyncio.sleep(FETCH_DELAY_MS / 1000)

def get_proc_phone_models(proc_query_list):
    proc_models = {}
    for proc_name, proc_pages in proc_query_list.items():
        arr = []
        for band_pages in proc_pages.values():
            for page_html in band_pages.values():
                if not page_html:
                    continue
                arr.extend(filter_response(page_html, 'class', 'device-name', 1))
        # Remove duplicates
        proc_models[proc_name] = list(dict.fromkeys(arr))
    return proc_models

def print_stats(phone_models_list):
    print('\n=============== Phone models per processor ===============')
    print(json.dumps(phone_models_list, indent=2, ensure_ascii=False))
    print('\n=============== Number of phone models per processor ===============')
    model_count_arr = {}
    total_models = 0
    for proc_name, proc_models in phone_models_list.items():
        model_count_arr[proc_name] = len(proc_models)
        total_models += len(proc_models)
    print(json.dumps(model_count_arr, indent=2, ensure_ascii=False))
    print('\n=============== Summary ===============')
    print(f'Total number of models for all processors: {total_models}')

async def main():
    print('Fetching all processors models...')
    async with aiohttp.ClientSession() as session:
        res = await fetch_with_retry(session, 'https://www.kimovil.com/en/compare-smartphones?xhr=1')
        if not res:
            print('Too many requests, try again later!')
            sys.exit(1)
        processors_list = dict(filter_response(res['filters'], 'data-for', 'f_dpg+id', 0, 'value'))
        print(f'[OK] Fetched processors IDs: {len(processors_list)}')
        print(json.dumps(processors_query_list, indent=2))
        band_query_list = {band: {} for band in bands_query_list}
        proc_query_list = {}
        for proc in processors_query_list:
            if proc not in processors_list:
                print(f'{proc} Not found in the IDs list, please double-check processor name!')
                sys.exit(1)
            proc_query_list[proc] = {band: {} for band in bands_query_list}
        await fill_all_proc_pages(session, proc_query_list, band_query_list, processors_list)
        phone_models_list = get_proc_phone_models(proc_query_list)
        print_stats(phone_models_list)

if __name__ == '__main__':
    asyncio.run(main())