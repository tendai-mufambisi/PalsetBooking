#!/usr/bin/env python3
"""Fix escaped quotes in template files"""

import re
from pathlib import Path

TEMPLATES_DIR = r"c:\Users\BIGSAM TECH\Desktop\PalsetBooking\templates\rides"

def fix_escaped_quotes(file_path):
    """Remove unnecessary backslash escapes from Django templating"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix the escaped quotes - they should not be escaped inside {% %}
    # Replace \' with '
    content = content.replace("\\'", "'")
    
    # Fix broken vendor tags - they're missing closing %}
    # Looking for: href="{% static 'vendor/... without closing %}
    content = re.sub(r'href="{% static \'([^"]*)"', r'href="{% static \'\1\' %}"', content)
    content = re.sub(r'src="{% static \'([^"]*)"', r'src="{% static \'\1\' %}"', content)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def main():
    templates_path = Path(TEMPLATES_DIR)
    html_files = list(templates_path.glob('*.html'))
    
    for html_file in html_files:
        fix_escaped_quotes(str(html_file))
        print(f"Fixed {html_file.name}")
    
    print("✓ Quote fixing complete!")

if __name__ == '__main__':
    main()
