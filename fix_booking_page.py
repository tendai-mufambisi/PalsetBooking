#!/usr/bin/env python3
import re
from pathlib import Path

templates_dir = Path(r'c:\Users\BIGSAM TECH\Desktop\PalsetBooking\templates\rides')

# Find all HTML files
for html_file in templates_dir.glob('*.html'):
    content = html_file.read_text(encoding='utf-8', errors='ignore')
    
    original = content
    
    # Replace all rides:booking_page with rides:booking_wizard_start
    content = content.replace(
        "rides:booking_page",
        "rides:booking_wizard_start"
    )
    
    if content != original:
        html_file.write_text(content, encoding='utf-8')
        print(f"✓ Fixed {html_file.name}")
    else:
        print(f"- No changes needed in {html_file.name}")

print("\n✓ All booking_page references have been replaced with booking_wizard_start")
