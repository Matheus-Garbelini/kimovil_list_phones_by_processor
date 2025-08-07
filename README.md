# 📱 Kimovil Phone Processor List

A Python web scraper that fetches phone data from kimovil.com based on specific processors and 5G bands. Because manually checking which phones have Snapdragon 8 Gen2 is for chumps.

## 🚀 Quick Start (TL;DR)

```bash
# One command setup (installs everything)
./setup.sh

# Activate environment 
source venv/bin/activate

# Run
python list_phones_by_processor.py
```

That's it. Go grab coffee while it scrapes ☕

## 🎯 What This Does

- Scrapes kimovil.com for phone data
- Filters by processors (Snapdragon, Apple A-series, MediaTek Dimensity)
- Filters by 5G bands (n78/n41) 
- Exports to CSV

## ⚙️ Customization

Want different processors or bands? Edit the `config.yaml` file.

## 🤷 FAQ

**Q: How long does it take?**  
A: ~2-5 minutes depending on how many processors you're querying.

**Q: Will kimovil.com block me?**  
A: The script includes delays and rate limiting.