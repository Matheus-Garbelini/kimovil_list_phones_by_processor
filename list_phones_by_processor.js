// ------------------- Imports -------------------
import { Parser } from "htmlparser2";

// Definitions
const FETCH_DELAY_MS = 100
const FETCH_RETRY_MS = 5000

const bands_query_list = [
    'fe_bands-nr-b78-3500',
    'fe_bands-nr-b41-2500'
]

const processors_query_list = [
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

// ------------------- Functions -------------------

function FilterResponse(html, attr_filter, attr_filter_value, child_level = 0, attr_to_add = null) {
    const parser = new Parser({
        onparserinit(parser) {
            // Init vars
            parser.filter_result = false;
            if (attr_to_add != null)
                parser.filter_map = {};
            else
                parser.filter_map = [];
            parser.child_level = 0;
        },
        onopentag(name, attributes) {

            if (parser.child_level > 0) {
                parser.child_level -= 1;
                return;
            }

            if (attributes[attr_filter] != attr_filter_value) {
                parser.filter_result = false;
                return;
            }



            if (attr_to_add != null)
                parser.attr_to_add_val = attributes[attr_to_add];
            else
                parser.attr_to_add_val = null;

            parser.filter_result = true;
            parser.child_level = child_level;
        },
        ontext(text) {
            if (parser.filter_result == true && parser.child_level == 0) {
                if (parser.attr_to_add_val != null)
                    parser.filter_map[text] = parser.attr_to_add_val;
                else
                    parser.filter_map.push(text);
            }
        },
    });

    parser.write(html)
    parser.end();
    return parser.filter_map;
}

async function FillProcPages(proc_list, proc_name, start_page, band_filter) {
    // Configure correct URL suffix
    let band_str = '';
    if (band_filter != undefined && band_filter.length > 0) {
        band_str = ',' + band_filter;
    }

    let suffix = band_str + '?xhr=1';
    if (start_page > 0) {
        const new_idx = start_page + 1;
        suffix = band_str + ',page.' + new_idx + '?xhr=1';
    }
    else if (band_str.length > 0)
        console.log('\n=============== \"' + proc_name + '\" Band:\"' + band_filter + '\" ===============');
    else
        console.log('\n=============== \"' + proc_name + '\" ===============');

    // Start fetching pages
    console.log('https://www.kimovil.com/en/compare-smartphones/f_dpg+id.' + PROCESSORS_LIST[proc_name] + suffix)
    const res = await fetch('https://www.kimovil.com/en/compare-smartphones/f_dpg+id.' +
        PROCESSORS_LIST[proc_name] + suffix);

    // Check for errors
    if (res.status == 429) {
        console.error('Too many requests, trying again in ' + (FETCH_RETRY_MS / 1000) + ' seconds');
        await Bun.sleep(FETCH_RETRY_MS);
        await FillProcPages(proc_list, proc_name, start_page, band_filter);
        return;
    }

    const res_json = await res.json()

    if (res_json.page_results == 0) {
        console.log('   ---> OK');
        return;
    }

    proc_list[proc_name][band_filter][start_page] = res_json.content;
    console.log('   ---> Fetched Page ' + (start_page + 1));

    const new_page_idx = res_json.next_page_url.split('.').pop() - 1;
    await Bun.sleep(FETCH_DELAY_MS); // Sleep to avoid too many requests (429)
    await FillProcPages(proc_list, proc_name, new_page_idx, band_filter);
}

async function FillAllProcPages(proc_query_list, band_query_list) {
    for (let [proc_name, proc_pages] of Object.entries(proc_query_list)) {
        for (let [band_filter] of Object.entries(proc_pages)) {

            await FillProcPages(proc_query_list, proc_name, 0, band_filter);
            await Bun.sleep(FETCH_DELAY_MS); // Sleep to avoid too many requests (429)
        }
    }
}

function GetProcPhoneModels(proc_query_list) {
    let proc_models = {}
    for (const [proc_name, proc_pages] of Object.entries(proc_query_list)) {
        // Filter and concatenate array os phone models per processor
        let arr = [];
        for (const bands of Object.entries(proc_pages)) {
            for (const pages of bands) {
                for (const page of pages) {
                    if (page == undefined)
                        continue;
                    arr = arr.concat(FilterResponse(page, 'class', 'device-name', 1));
                }
            }
        }
        // Remove duplicated entries
        proc_models[proc_name] = arr.filter((item, index) => arr.indexOf(item) === index);
        // proc_models[proc_name] = arr;
    }
    return proc_models;
}

function PrintStats(phone_models_list) {

    console.log('\n=============== Phone models per processor ===============');
    console.log(JSON.stringify(phone_models_list, null, 2));

    console.log('\n=============== Number of phone models per processor ===============');
    let model_count_arr = {};
    let total_models = 0;
    for (const [proc_name, proc_models] of Object.entries(phone_models_list)) {
        model_count_arr[proc_name] = proc_models.length;
        total_models += proc_models.length;
    }

    console.log(model_count_arr);
    console.log('\n=============== Summary ===============');
    console.log('\x1b[33mTotal number of models for all processors: \x1b[31m' + total_models + '\x1b[0m');
}

// ------------------- Main Routine -------------------

// Fetch All Processor models
console.log('Fetching all processors models...')
const res = await fetch('https://www.kimovil.com/en/compare-smartphones?xhr=1');
if (res.status == 429) {
    console.error('Too many requests, try again later!');
    process.exit(1);
}

const res_json = await res.json();
// Create maps of processors name to kimovil id
const PROCESSORS_LIST = FilterResponse(res_json.filters, 'data-for', 'f_dpg+id', 0, 'value');

console.log('[OK] Fetched processors IDs: ' + Object.keys(PROCESSORS_LIST).length);

console.log(processors_query_list);

// Initialize band list dictionary
let band_query_list = {}
for (const band of bands_query_list)
    band_query_list[band] = [];

// Initialize proc_pages dictionary
let proc_query_list = {}
for (const proc of processors_query_list) {
    if (!(proc in PROCESSORS_LIST)) {
        console.error(proc + ' Not found in the IDs list, please double-check processor name!');
        process.exit(1);
    }

    proc_query_list[proc] = structuredClone(band_query_list);
}

await FillAllProcPages(proc_query_list, band_query_list);
const phone_models_list = GetProcPhoneModels(proc_query_list);
PrintStats(phone_models_list);

process.exit(0);