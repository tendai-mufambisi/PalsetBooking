#!/usr/bin/env python3
import re
from pathlib import Path

templates_dir = Path(r'c:\Users\BIGSAM TECH\Desktop\PalsetBooking\templates\rides')

# Find all HTML files
for html_file in templates_dir.glob('*.html'):
    content = html_file.read_text(encoding='utf-8', errors='ignore')
    
    original = content
    
    # Replace all booking.html?... with the Django URL tag
    content = re.sub(
        r'href="booking\.html\?[^"]*"',
        'href="{% url \'rides:booking_wizard_start\' %}"',
        content
    )
    
    if content != original:
        html_file.write_text(content, encoding='utf-8')
        print(f"✓ Fixed {html_file.name}")
    else:
        print(f"- No changes needed in {html_file.name}")

print("\n✓ All booking.html links have been replaced with the wizard URL")
