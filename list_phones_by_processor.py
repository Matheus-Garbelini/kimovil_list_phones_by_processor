import asyncio
import httpx
from bs4 import BeautifulSoup
import json
import sys
import copy

# ------------------- Definitions -------------------
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

# ------------------- Functions -------------------
def filter_response(html, attr_filter, attr_filter_value, child_level=0, attr_to_add=None):
    soup = BeautifulSoup(html, 'html.parser')
    result = {} if attr_to_add else []
    for tag in soup.find_all(attrs={attr_filter: attr_filter_value}):
        # Go down child_level
        current = tag
        for _ in range(child_level):
            if current.contents:
                current = current.contents[0]
            else:
                break
        text = current.get_text(strip=True)
        if attr_to_add:
            val = tag.get(attr_to_add)
            result[text] = val
        else:
            result.append(text)
    return result

async def fill_proc_pages(client, proc_list, proc_name, start_page, band_filter, processors_list):
    # Configure correct URL suffix
    band_str = ''
    if band_filter is not None and len(band_filter) > 0:
        band_str = ',' + band_filter
    suffix = band_str + '?xhr=1'
    if start_page > 0:
        new_idx = start_page + 1
        suffix = band_str + f',page.{new_idx}?xhr=1'
    elif len(band_str) > 0:
        print(f'\n=============== "{proc_name}" Band:"{band_filter}" ===============')
    else:
        print(f'\n=============== "{proc_name}" ===============')
    url = f'https://www.kimovil.com/en/compare-smartphones/f_dpg+id.{processors_list[proc_name]}{suffix}'
    print(url)
    while True:
        res = await client.get(url)
        if res.status_code == 429:
            print(f'Too many requests, trying again in {FETCH_RETRY_MS / 1000} seconds', file=sys.stderr)
            await asyncio.sleep(FETCH_RETRY_MS / 1000)
            continue
        break
    res_json = res.json()
    if res_json.get('page_results', 0) == 0:
        print('   ---> OK')
        return
    if proc_list[proc_name][band_filter] is None:
        proc_list[proc_name][band_filter] = {}
    proc_list[proc_name][band_filter][start_page] = res_json['content']
    print(f'   ---> Fetched Page {start_page + 1}')
    next_page_url = res_json.get('next_page_url')
    if next_page_url:
        try:
            new_page_idx = int(next_page_url.split('.')[-1]) - 1
            await asyncio.sleep(FETCH_DELAY_MS / 1000)
            await fill_proc_pages(client, proc_list, proc_name, new_page_idx, band_filter, processors_list)
        except Exception:
            pass

async def fill_all_proc_pages(client, proc_query_list, band_query_list, processors_list):
    for proc_name, proc_pages in proc_query_list.items():
        for band_filter in proc_pages.keys():
            await fill_proc_pages(client, proc_query_list, proc_name, 0, band_filter, processors_list)
            await asyncio.sleep(FETCH_DELAY_MS / 1000)

def get_proc_phone_models(proc_query_list):
    proc_models = {}
    for proc_name, proc_pages in proc_query_list.items():
        arr = []
        for bands in proc_pages.values():
            if bands is None:
                continue
            for page in bands.values():
                if page is None:
                    continue
                arr.extend(filter_response(page, 'class', 'device-name', 1))
        # Remove duplicates
        proc_models[proc_name] = list(dict.fromkeys(arr))
    return proc_models

def print_stats(phone_models_list):
    print('\n=============== Phone models per processor ===============')
    print(json.dumps(phone_models_list, indent=2))
    print('\n=============== Number of phone models per processor ===============')
    model_count_arr = {}
    total_models = 0
    for proc_name, proc_models in phone_models_list.items():
        model_count_arr[proc_name] = len(proc_models)
        total_models += len(proc_models)
    print(model_count_arr)
    print('\n=============== Summary ===============')
    print(f'\033[33mTotal number of models for all processors: \033[31m{total_models}\033[0m')

# ------------------- Main Routine -------------------
async def main():
    print('Fetching all processors models...')
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    async with httpx.AsyncClient(headers=headers) as client:
        res = await client.get('https://www.kimovil.com/en/compare-smartphones?xhr=1')
        if res.status_code == 429:
            print('Too many requests, try again later!', file=sys.stderr)
            sys.exit(1)
        if res.status_code != 200:
            print(f'Error: Received status code {res.status_code}', file=sys.stderr)
            print(res.text)
            sys.exit(1)
        try:
            res_json = res.json()
        except Exception as e:
            print(f'Error decoding JSON: {e}', file=sys.stderr)
            print(res.text)
            sys.exit(1)
        # Create maps of processors name to kimovil id
        processors_list = filter_response(res_json['filters'], 'data-for', 'f_dpg+id', 0, 'value')
        print(f'[OK] Fetched processors IDs: {len(processors_list)}')
        print(processors_query_list)
        # Initialize band list dictionary
        band_query_dict = {band: None for band in bands_query_list}
        # Initialize proc_pages dictionary
        proc_query_list = {}
        for proc in processors_query_list:
            if proc not in processors_list:
                print(f'{proc} Not found in the IDs list, please double-check processor name!', file=sys.stderr)
                sys.exit(1)
            proc_query_list[proc] = copy.deepcopy(band_query_dict)
        await fill_all_proc_pages(client, proc_query_list, band_query_dict, processors_list)
        phone_models_list = get_proc_phone_models(proc_query_list)
        print_stats(phone_models_list)
    sys.exit(0)

if __name__ == '__main__':
    asyncio.run(main())