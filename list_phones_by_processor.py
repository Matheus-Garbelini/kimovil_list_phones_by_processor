#!/usr/bin/env python3
"""
Beautiful Python equivalent of list_phones_by_processor.js
Fetches phone data from kimovil.com based on specific processors/chipsets
"""

import argparse
import asyncio
import csv
import json
import os
import sys
import time
import yaml
from datetime import datetime
from typing import Dict, List, Optional, Union
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich import box
from rich.layout import Layout
from rich.live import Live

# Initialize Rich console
console = Console()

# Default configuration file
DEFAULT_CONFIG_FILE = 'config.yaml'

# Global progress tracking
progress_data = {
    'current_processor': '',
    'current_band': '',
    'pages_fetched': 0,
    'total_requests': 0,
    'rate_limited': 0,
    'errors': 0
}

# Global CSV filename for incremental saving
csv_filename = None


def load_config(config_file: str) -> Dict:
    """
    Load configuration from YAML file
    
    Args:
        config_file: Path to the YAML configuration file
        
    Returns:
        Dictionary containing configuration data
        
    Raises:
        SystemExit: If config file cannot be loaded or parsed
    """
    try:
        if not os.path.exists(config_file):
            console.print(f"❌ [bold red]Configuration file not found: {config_file}[/bold red]")
            console.print(f"💡 [yellow]Create a config file or use the default: {DEFAULT_CONFIG_FILE}[/yellow]")
            sys.exit(1)
        
        with open(config_file, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            
        # Validate required keys
        required_keys = ['bands', 'processors']
        for key in required_keys:
            if key not in config:
                console.print(f"❌ [bold red]Missing required configuration key: {key}[/bold red]")
                sys.exit(1)
        
        # Validate that lists are not empty
        if not config['bands']:
            console.print(f"❌ [bold red]bands cannot be empty[/bold red]")
            sys.exit(1)
            
        if not config['processors']:
            console.print(f"❌ [bold red]processors cannot be empty[/bold red]")
            sys.exit(1)
        
        return config
        
    except yaml.YAMLError as e:
        console.print(f"❌ [bold red]Invalid YAML syntax in {config_file}: {e}[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"❌ [bold red]Error loading configuration from {config_file}: {e}[/bold red]")
        sys.exit(1)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description='Fetch phone data from kimovil.com based on specific processors/chipsets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Use default config.yaml
  %(prog)s -c custom.yaml     # Use custom configuration file
  %(prog)s --config my.yaml   # Use custom configuration file (long form)
        """)
    
    parser.add_argument(
        '-c', '--config',
        default=DEFAULT_CONFIG_FILE,
        help=f'YAML configuration file (default: {DEFAULT_CONFIG_FILE})',
        metavar='FILE'
    )
    
    return parser.parse_args()


def print_header():
    """Print a beautiful header"""
    header_text = Text("📱 Kimovil Phone Data Fetcher", style="bold magenta")
    
    panel = Panel(
        Align.center(header_text),
        box=box.DOUBLE,
        border_style="bright_blue",
        padding=(1, 2)
    )
    console.print(panel)
    console.print()


def filter_response(html: str, attr_filter: str, attr_filter_value: str, 
                   child_level: int = 0, attr_to_add: Optional[str] = None) -> Union[List[str], Dict[str, str]]:
    """
    Filter HTML response to extract specific elements based on attributes
    
    Args:
        html: HTML content to parse
        attr_filter: Attribute name to filter by
        attr_filter_value: Value of the attribute to match
        child_level: Number of child levels to traverse
        attr_to_add: Additional attribute to extract as value
    
    Returns:
        List of text content or dictionary mapping text to attribute values
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    if attr_to_add is not None:
        filter_map = {}
    else:
        filter_map = []
    
    # Find all elements with the specified attribute and value
    elements = soup.find_all(attrs={attr_filter: attr_filter_value})
    
    for element in elements:
        target_element = element
        
        # Navigate to child level if specified
        for _ in range(child_level):
            if target_element.children:
                target_element = next(iter(target_element.children), target_element)
        
        # Extract text content
        text = target_element.get_text(strip=True) if hasattr(target_element, 'get_text') else str(target_element).strip()
        
        if text:
            if attr_to_add is not None:
                attr_value = element.get(attr_to_add, '')
                filter_map[text] = attr_value
            else:
                filter_map.append(text)
    
    return filter_map


async def fill_proc_pages(page: Page, proc_list: Dict, proc_name: str,
                         start_page: int, band_filter: str, processors_list: Dict[str, str],
                         progress: Progress, task_id: int, csv_filename: str = None,
                         fetch_delay_ms: int = 100, fetch_retry_ms: int = 5000) -> None:
    """
    Recursively fetch all pages for a specific processor and band filter, saving each page immediately
    
    Args:
        page: Playwright page for making requests
        proc_list: Dictionary to store fetched data
        proc_name: Name of the processor
        start_page: Starting page index
        band_filter: Band filter string
        processors_list: Mapping of processor names to IDs
        progress: Rich progress instance
        task_id: Progress task ID
        csv_filename: Path to CSV file for incremental saving
    """
    global progress_data
    
    # Configure correct URL suffix
    band_str = ''
    if band_filter and len(band_filter) > 0:
        band_str = ',' + band_filter

    suffix = band_str + '?xhr=1'
    if start_page > 0:
        new_idx = start_page + 1
        suffix = band_str + ',page.' + str(new_idx) + '?xhr=1'
    
    # Update progress data
    progress_data['current_processor'] = proc_name
    progress_data['current_band'] = band_filter
    
    # Start fetching pages
    url = f'https://www.kimovil.com/en/compare-smartphones/f_dpg+id.{processors_list[proc_name]}{suffix}'
    
    try:
        progress_data['total_requests'] += 1
        
        # Navigate to URL and get response
        response = await page.goto(url)
        
        # Check for errors
        if response.status == 429:
            progress_data['rate_limited'] += 1
            progress.update(task_id, description=f"⏳ Rate limited - waiting {fetch_retry_ms/1000:.0f}s...")
            await asyncio.sleep(fetch_retry_ms / 1000)
            await fill_proc_pages(page, proc_list, proc_name, start_page, band_filter, processors_list, progress, task_id, csv_filename, fetch_delay_ms, fetch_retry_ms)
            return
        
        if response.status != 200:
            progress_data['errors'] += 1
            progress.update(task_id, description=f"❌ HTTP {response.status}: {response.status_text}")
            return
        
        # Get JSON content from page
        content = await page.content()
        
        # Since we're making XHR requests, the response should be JSON
        # We need to extract the JSON from the page content
        try:
            json_content = await page.evaluate('() => document.body.textContent')
            res_json = json.loads(json_content)
        except (json.JSONDecodeError, ValueError):
            progress_data['errors'] += 1
            progress.update(task_id, description=f"❌ Invalid JSON response")
            return
        
        if res_json.get('page_results', 0) == 0:
            progress.update(task_id, description=f"✅ {proc_name} - {band_filter} completed")
            return
        
        # Store the page content
        proc_list[proc_name][band_filter][start_page] = res_json['content']
        progress_data['pages_fetched'] += 1
        
        # Process and save this page's data immediately to CSV
        if csv_filename and res_json['content']:
            page_models = filter_response(res_json['content'], 'class', 'device-name', 1)
            if page_models:
                records_added = append_processor_to_csv(csv_filename, proc_name, page_models)
                progress.update(task_id,
                              description=f"💾 {proc_name} P{start_page + 1}: {records_added} models saved")
        
        progress.update(task_id,
                      description=f"📄 {proc_name} - Page {start_page + 1}",
                      advance=1)
        
        # Extract next page index
        next_page_url = res_json.get('next_page_url', '')
        if next_page_url and '.' in next_page_url:
            new_page_idx = int(next_page_url.split('.')[-1]) - 1
            await asyncio.sleep(fetch_delay_ms / 1000)  # Sleep to avoid too many requests (429)
            await fill_proc_pages(page, proc_list, proc_name, new_page_idx, band_filter, processors_list, progress, task_id, csv_filename, fetch_delay_ms, fetch_retry_ms)
            
    except Exception as e:
        progress_data['errors'] += 1
        progress.update(task_id, description=f"❌ Error: {str(e)[:50]}...")
        return


async def fill_all_proc_pages(proc_query_list: Dict, band_query_list: Dict, processors_list: Dict[str, str],
                             csv_filename: str = None, fetch_delay_ms: int = 100, fetch_retry_ms: int = 5000) -> None:
    """
    Fill all processor pages with data from kimovil.com and save to CSV incrementally
    
    Args:
        proc_query_list: Dictionary of processors to query
        band_query_list: Dictionary of bands to query
        processors_list: Mapping of processor names to IDs
        csv_filename: Path to CSV file for incremental saving
    """
    total_tasks = len(proc_query_list) * len(band_query_list)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False
    ) as progress:
        
        main_task = progress.add_task("🚀 Fetching phone data...", total=total_tasks)
        
        async with async_playwright() as p:
            # Configure browser to use system Chrome, with fallback to Chromium
            try:
                # First try to use system Chrome
                browser = await p.chromium.launch(
                    headless=True,  # Set to False for debugging
                    channel="chrome",  # Use system Chrome instead of downloaded Chromium
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-extensions'
                    ]
                )
            except Exception as e:
                console.print(f"⚠️  [yellow]Could not launch system Chrome, falling back to Chromium: {e}[/yellow]")
                # Fallback to downloaded Chromium
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-extensions'
                    ]
                )
            
            # Create browser context with headers
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                extra_http_headers={
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Referer': 'https://www.kimovil.com/en/compare-smartphones',
                }
            )
            
            try:
                for proc_name, proc_pages in proc_query_list.items():
                    # Process each processor completely before moving to the next
                    processor_task = progress.add_task(f"🔧 {proc_name[:25]}...", total=len(proc_pages))
                    
                    for band_filter in proc_pages.keys():
                        task_desc = f"📱 {proc_name[:20]}... - {band_filter}"
                        task_id = progress.add_task(task_desc, total=None)
                        
                        # Create a new page for each request to avoid conflicts
                        page = await context.new_page()
                        
                        try:
                            await fill_proc_pages(page, proc_query_list, proc_name, 0, band_filter, processors_list, progress, task_id, csv_filename, fetch_delay_ms, fetch_retry_ms)
                        finally:
                            await page.close()
                        
                        progress.update(main_task, advance=1)
                        progress.update(processor_task, advance=1)
                        progress.remove_task(task_id)
                        
                        await asyncio.sleep(fetch_delay_ms / 1000)  # Sleep to avoid too many requests (429)
                    
                    # Data already saved per page, just complete the processor task
                    progress.update(processor_task, description=f"✅ Completed {proc_name[:25]}")
                    progress.remove_task(processor_task)
            
            finally:
                await context.close()
                await browser.close()


def process_and_save_processor_data(proc_name: str, proc_pages: Dict, csv_filename: str) -> List[str]:
    """
    Process a single processor's data (data already saved per page during fetching)
    
    Args:
        proc_name: Name of the processor
        proc_pages: Dictionary containing fetched page data for the processor
        csv_filename: Path to the CSV file (not used, data already saved)
    
    Returns:
        List of phone models for this processor
    """
    # Filter and concatenate array of phone models per processor
    arr = []
    for band_name, band_pages in proc_pages.items():
        for page_idx, page_content in band_pages.items():
            if page_content is None:
                continue
            models = filter_response(page_content, 'class', 'device-name', 1)
            arr.extend(models)
    
    # Remove duplicated entries (data already saved per page)
    proc_models = list(set(arr))
    
    return proc_models


def get_proc_phone_models(proc_query_list: Dict) -> Dict[str, List[str]]:
    """
    Extract phone models from the fetched processor data (data already saved during fetching)
    
    Args:
        proc_query_list: Dictionary containing fetched processor data
    
    Returns:
        Dictionary mapping processor names to lists of phone models
    """
    console.print("\n🔍 [bold blue]Extracting phone models from fetched data...[/bold blue]")
    
    proc_models = {}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True
    ) as progress:
        
        task = progress.add_task("Processing...", total=len(proc_query_list))
        
        for proc_name, proc_pages in proc_query_list.items():
            progress.update(task, description=f"📱 Processing {proc_name[:30]}...")
            
            # Just extract models without saving (already saved during fetching)
            arr = []
            for band_name, band_pages in proc_pages.items():
                for page_idx, page_content in band_pages.items():
                    if page_content is None:
                        continue
                    models = filter_response(page_content, 'class', 'device-name', 1)
                    arr.extend(models)
            
            # Remove duplicated entries
            proc_models[proc_name] = list(set(arr))
            progress.advance(task)
    
    return proc_models


def create_csv_file(filename: str = None) -> str:
    """
    Create a new CSV file with headers
    
    Args:
        filename: Optional filename for the CSV file
    
    Returns:
        The filename of the created CSV file
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"kimovil_phone_data_{timestamp}.csv"
    
    # Write CSV headers
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Processor', 'Brand', 'Model', 'Full_Name']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
    
    return filename


def append_processor_to_csv(filename: str, proc_name: str, proc_models: List[str]) -> int:
    """
    Append processor phone models data to existing CSV file
    
    Args:
        filename: Path to the CSV file
        proc_name: Name of the processor
        proc_models: List of phone models for this processor
    
    Returns:
        Number of records added
    """
    if not proc_models:
        return 0
    
    # Prepare data for CSV
    csv_data = []
    for model in sorted(set(proc_models)):  # Remove duplicates within this batch
        # Extract brand (first word) and model name
        parts = model.split(' ', 1)
        brand = parts[0] if parts else 'Unknown'
        model_name = parts[1] if len(parts) > 1 else model
        
        csv_data.append({
            'Processor': proc_name,
            'Brand': brand,
            'Model': model_name,
            'Full_Name': model
        })
    
    # Sort by brand, then by model
    csv_data.sort(key=lambda x: (x['Brand'], x['Model']))
    
    # Append to CSV file
    with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Processor', 'Brand', 'Model', 'Full_Name']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writerows(csv_data)
    
    return len(csv_data)


def export_to_csv(phone_models_list: Dict[str, List[str]], filename: str = None) -> str:
    """
    Export phone models data to CSV format (legacy function for compatibility)
    
    Args:
        phone_models_list: Dictionary mapping processor names to phone model lists
        filename: Optional filename for the CSV file
    
    Returns:
        The filename of the created CSV file
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"kimovil_phone_data_{timestamp}.csv"
    
    # Create new file with headers
    create_csv_file(filename)
    
    # Append all processor data
    for proc_name, proc_models in phone_models_list.items():
        append_processor_to_csv(filename, proc_name, proc_models)
    
    return filename


def print_beautiful_stats(phone_models_list: Dict[str, List[str]]) -> None:
    """
    Print beautiful statistics about the fetched phone models
    
    Args:
        phone_models_list: Dictionary mapping processor names to phone model lists
    """
    console.print("\n" + "="*80)
    console.print(Align.center("📊 [bold magenta]RESULTS SUMMARY[/bold magenta]"), style="bold")
    console.print("="*80)
    
    # Create summary table
    table = Table(title="📱 Phone Models by Processor", box=box.ROUNDED, title_style="bold cyan")
    table.add_column("🔧 Processor", style="cyan", no_wrap=True, width=30)
    table.add_column("📱 Models", justify="right", style="magenta", width=10)
    table.add_column("📋 Sample Models", style="green", width=35)
    
    total_models = 0
    for proc_name, proc_models in sorted(phone_models_list.items(), key=lambda x: len(x[1]), reverse=True):
        model_count = len(proc_models)
        total_models += model_count
        
        # Show first 3 models as sample
        sample_models = ", ".join(proc_models[:3])
        if len(proc_models) > 3:
            sample_models += f"... (+{len(proc_models)-3} more)"
        
        # Color code based on count
        if model_count > 50:
            count_style = "bold red"
        elif model_count > 20:
            count_style = "bold yellow"
        else:
            count_style = "bold green"
        
        table.add_row(
            proc_name,
            f"[{count_style}]{model_count}[/{count_style}]",
            sample_models[:35] + "..." if len(sample_models) > 35 else sample_models
        )
    
    console.print(table)
    
    # Print detailed stats
    console.print(f"\n📈 [bold green]STATISTICS[/bold green]")
    console.print(f"   • Total Processors: [bold cyan]{len(phone_models_list)}[/bold cyan]")
    console.print(f"   • Total Phone Models: [bold magenta]{total_models}[/bold magenta]")
    console.print(f"   • Average Models per Processor: [bold yellow]{total_models/len(phone_models_list):.1f}[/bold yellow]")
    
    # Print request statistics
    console.print(f"\n🌐 [bold blue]REQUEST STATISTICS[/bold blue]")
    console.print(f"   • Total Requests: [cyan]{progress_data['total_requests']}[/cyan]")
    console.print(f"   • Pages Fetched: [green]{progress_data['pages_fetched']}[/green]")
    console.print(f"   • Rate Limited: [yellow]{progress_data['rate_limited']}[/yellow]")
    console.print(f"   • Errors: [red]{progress_data['errors']}[/red]")
    
    # Show top processors
    if phone_models_list:
        console.print(f"\n🏆 [bold gold1]TOP PROCESSORS[/bold gold1]")
        top_processors = sorted(phone_models_list.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        
        for i, (proc_name, models) in enumerate(top_processors, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            console.print(f"   {medal} [bold]{proc_name}[/bold]: [magenta]{len(models)}[/magenta] models")
    
    # CSV export summary (data already saved incrementally)
    if phone_models_list:
        console.print(f"\n💾 [bold blue]CSV EXPORT COMPLETE[/bold blue]")
        try:
            total_records = sum(len(models) for models in phone_models_list.values())
            file_size = os.path.getsize(csv_filename) / 1024  # Size in KB
            console.print(f"   ✅ [green]Data saved to:[/green] [bold cyan]{csv_filename}[/bold cyan]")
            console.print(f"   📊 [green]Total records:[/green] [bold magenta]{total_records}[/bold magenta]")
            console.print(f"   📁 [green]File size:[/green] [bold yellow]{file_size:.1f} KB[/bold yellow]")
            console.print(f"   📋 [green]Format:[/green] CSV with columns: Processor, Brand, Model, Full_Name")
            console.print(f"   💡 [blue]Data was saved incrementally during processing[/blue]")
        except Exception as e:
            console.print(f"   ❌ [red]Error accessing CSV file:[/red] {str(e)}")
    else:
        console.print(f"\n⚠️  [yellow]No data to export[/yellow]")


def print_detailed_results(phone_models_list: Dict[str, List[str]]) -> None:
    """Print detailed phone models in a beautiful format"""
    console.print(f"\n📋 [bold cyan]DETAILED PHONE MODELS[/bold cyan]")
    console.print("="*80)
    
    for proc_name, models in phone_models_list.items():
        if not models:
            continue
            
        # Create a panel for each processor
        model_text = ""
        for i, model in enumerate(sorted(models), 1):
            model_text += f"{i:2d}. {model}\n"
        
        panel = Panel(
            model_text.rstrip(),
            title=f"🔧 {proc_name}",
            title_align="left",
            border_style="blue",
            box=box.ROUNDED
        )
        console.print(panel)


async def main():
    """Main routine with beautiful output"""
    start_time = time.time()
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Print header
    print_header()
    
    # Load configuration
    console.print(f"⚙️  [bold cyan]Loading configuration from: {args.config}[/bold cyan]")
    config = load_config(args.config)
    
    # Extract configuration values
    bands = config['bands']
    processors = config['processors']
    FETCH_DELAY_MS = config.get('fetch_delay_ms', 100)
    FETCH_RETRY_MS = config.get('fetch_retry_ms', 5000)
    
    # Fetch All Processor models
    console.print("🌐 [bold blue]Connecting to kimovil.com...[/bold blue]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        
        task = progress.add_task("🔍 Fetching processor list...", total=None)
        
        async with async_playwright() as p:
            # Configure browser to use system Chrome, with fallback to Chromium
            try:
                # First try to use system Chrome
                browser = await p.chromium.launch(
                    headless=True,
                    channel="chrome",  # Use system Chrome
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-extensions'
                    ]
                )
            except Exception as e:
                console.print(f"⚠️  [yellow]Could not launch system Chrome, falling back to Chromium: {e}[/yellow]")
                # Fallback to downloaded Chromium
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-extensions'
                    ]
                )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                extra_http_headers={
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Referer': 'https://www.kimovil.com/en/compare-smartphones',
                }
            )
            
            page = await context.new_page()
            
            try:
                response = await page.goto('https://www.kimovil.com/en/compare-smartphones?xhr=1')
                
                if response.status == 429:
                    console.print("❌ [bold red]Too many requests, try again later![/bold red]")
                    sys.exit(1)
                
                if response.status != 200:
                    console.print(f"❌ [bold red]HTTP Error {response.status}: {response.status_text}[/bold red]")
                    sys.exit(1)
                
                # Get JSON content from page
                json_content = await page.evaluate('() => document.body.textContent')
                res_json = json.loads(json_content)
                
            except (json.JSONDecodeError, ValueError) as e:
                console.print(f"❌ [bold red]Invalid JSON response: {e}[/bold red]")
                sys.exit(1)
            except Exception as e:
                console.print(f"❌ [bold red]Error fetching processors: {e}[/bold red]")
                sys.exit(1)
            finally:
                await page.close()
                await context.close()
                await browser.close()
    
    # Create maps of processors name to kimovil id
    processors_list = filter_response(res_json['filters'], 'data-for', 'f_dpg+id', 0, 'value')
    
    console.print(f"✅ [bold green]Found {len(processors_list)} processors on kimovil.com[/bold green]")
    
    # Show target processors
    console.print(f"\n🎯 [bold yellow]Target Processors ({len(processors)}):[/bold yellow]")
    for i, proc in enumerate(processors, 1):
        status = "✅" if proc in processors_list else "❌"
        console.print(f"   {i:2d}. {status} {proc}")
    
    # Initialize band list dictionary
    band_query_list = {}
    for band in bands:
        band_query_list[band] = {}
    
    console.print(f"\n📡 [bold cyan]5G Bands to filter:[/bold cyan]")
    for band in bands:
        console.print(f"   • {band}")
    
    # Initialize proc_pages dictionary
    proc_query_list = {}
    missing_processors = []
    
    for proc in processors:
        if proc not in processors_list:
            missing_processors.append(proc)
        else:
            proc_query_list[proc] = {band: {} for band in band_query_list.keys()}
    
    if missing_processors:
        console.print(f"\n❌ [bold red]Missing processors:[/bold red]")
        for proc in missing_processors:
            console.print(f"   • {proc}")
        console.print("\n[yellow]Please double-check processor names![/yellow]")
        sys.exit(1)
    
    console.print(f"\n🚀 [bold green]Starting data collection for {len(proc_query_list)} processors...[/bold green]")
    
    # Create CSV file with headers at the beginning
    global csv_filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"kimovil_phone_data_{timestamp}.csv"
    
    # Check if a CSV file with similar name already exists and ask user
    existing_files = [f for f in os.listdir('.') if f.startswith('kimovil_phone_data_') and f.endswith('.csv')]
    if existing_files:
        console.print(f"\n💾 [yellow]Found existing CSV files:[/yellow]")
        for file in existing_files[-3:]:  # Show last 3 files
            try:
                file_size = os.path.getsize(file) / 1024  # Size in KB
                console.print(f"   • {file} ({file_size:.1f} KB)")
            except OSError:
                console.print(f"   • {file}")
        console.print(f"\n❓ [bold yellow]Continue with new file {csv_filename}? (Y/n):[/bold yellow] ", end="")
        try:
            response = input().strip().lower()
            if response in ['n', 'no']:
                console.print("👋 [yellow]Operation cancelled by user.[/yellow]")
                sys.exit(0)
        except KeyboardInterrupt:
            console.print("\n👋 [yellow]Operation cancelled by user.[/yellow]")
            sys.exit(0)
    
    # Create the CSV file with headers
    csv_filename = create_csv_file(csv_filename)
    console.print(f"📄 [bold cyan]Created CSV file: {csv_filename}[/bold cyan]")
    console.print("💡 [blue]Data will be saved incrementally as processors are processed[/blue]")
    
    # Fetch all data and save incrementally during fetching
    await fill_all_proc_pages(proc_query_list, band_query_list, processors_list, csv_filename, FETCH_DELAY_MS, FETCH_RETRY_MS)
    
    # Extract final results (data already saved to CSV during fetching)
    phone_models_list = get_proc_phone_models(proc_query_list)
    
    # Print beautiful statistics
    print_beautiful_stats(phone_models_list)
    
    # Ask if user wants detailed results
    console.print(f"\n❓ [bold yellow]Show detailed phone models? (y/N):[/bold yellow] ", end="")
    try:
        response = input().strip().lower()
        if response in ['y', 'yes']:
            print_detailed_results(phone_models_list)
    except KeyboardInterrupt:
        console.print("\n👋 [yellow]Goodbye![/yellow]")
    
    # Print completion message
    elapsed_time = time.time() - start_time
    console.print(f"\n🎉 [bold green]Completed in {elapsed_time:.1f} seconds![/bold green]")
    
    # Create a final summary panel
    summary_text = Text()
    summary_text.append("✅ Data collection completed successfully!\n", style="bold green")
    summary_text.append(f"📱 Found {sum(len(models) for models in phone_models_list.values())} phone models\n", style="cyan")
    summary_text.append(f"🔧 Across {len(phone_models_list)} processors\n", style="magenta")
    summary_text.append(f"⏱️  In {elapsed_time:.1f} seconds", style="yellow")
    
    final_panel = Panel(
        Align.center(summary_text),
        title="🏁 Summary",
        border_style="green",
        box=box.DOUBLE
    )
    console.print(final_panel)


if __name__ == '__main__':    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n\n👋 [yellow]Operation cancelled by user. Goodbye![/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n❌ [bold red]Unexpected error: {e}[/bold red]")
        sys.exit(1)