#!/usr/bin/env python3
import re
from pathlib import Path

for html in Path(r'c:\Users\BIGSAM TECH\Desktop\PalsetBooking\templates\rides').glob('*.html'):
    content = html.read_text(encoding='utf-8', errors='ignore')
    
    # Fix duplicated/malformed static tags
    # Pattern: {% static 'xyz' %}' %}  -->  {% static 'xyz' %}
    content = re.sub(r"{%\s*static\s+(['\"].*?['\"])\s*%}['\"]?\s*%}", r"{% static \1 %}", content)
    content = re.sub(r"{%\s*static\s+(['\"].*?['\"])\s*%}'", r"{% static \1 %}", content)
    
    html.write_text(content, encoding='utf-8')

print('✓ Fixed all malformed tags')
