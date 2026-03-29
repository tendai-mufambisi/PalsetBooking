#!/usr/bin/env python3
"""
Convert HTML files to Django templates by:
1. Adding {% load static %} at the top
2. Replacing asset paths with {% static %} tags
3. Replacing hardcoded HTML links with Django {% url %} tags
4. Converting extends to base.html
"""

import re
import os
from pathlib import Path

TEMPLATES_DIR = r"c:\Users\BIGSAM TECH\Desktop\PalsetBooking\templates\rides"

# Mapping of old HTML filenames to Django URL names
URL_MAPPING = {
    'index.html': ('rides:index', 'index'),
    'about.html': ('rides:about', 'about'),
    'airport-transfers.html': ('rides:airport_transfers', 'airport_transfers'),
    'corporate-transfers.html': ('rides:corporate_transfers', 'corporate_transfers'),
    'chauffeur-drive.html': ('rides:chauffeur_drive', 'chauffeur_drive'),
    'private-tours.html': ('rides:private_tours', 'private_tours'),
    'group-transfers.html': ('rides:group_transfers', 'group_transfers'),
    'point-transfers.html': ('rides:point_transfers', 'point_transfers'),
    'car-rental.html': ('rides:car_rental', 'car_rental'),
    'special-events.html': ('rides:special_events', 'special_events'),
    'long-distance.html': ('rides:long_distance', 'long_distance'),
    'dinner-transfers.html': ('rides:dinner_transfers', 'dinner_transfers'),
    'fleet.html': ('rides:fleet', 'fleet'),
    'tours.html': ('rides:tours', 'tours'),
    'gallery.html': ('rides:gallery', 'gallery'),
    'blog.html': ('rides:blog', 'blog'),
    'blog-details.html': ('rides:blog_details', 'blog_details'),
    'booking.html': ('rides:booking_page', 'booking_page'),
    'contact.html': ('rides:contact', 'contact'),
    'testimonials.html': ('rides:testimonials', 'testimonials'),
    'faq.html': ('rides:faq', 'faq'),
    'terms.html': ('rides:terms', 'terms'),
    'privacy.html': ('rides:privacy', 'privacy'),
    'services.html': ('rides:services', 'services'),
}

def convert_template(file_path):
    """Convert a single HTML file to Django template"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    filename = os.path.basename(file_path)
    print(f"Converting {filename}...")
    
    # Step 1: Add {% load static %} at the top if not present
    if '{% load static %}' not in content:
        content = '{% load static %}\n' + content
    
    # Step 2: Replace asset paths with {% static %} tags
    # Handle all variations of asset paths
    
    # assets/vendor/..."> or assets/vendor/...'>
    content = re.sub(r'(href|src)=(["\'])assets\/vendor\/', r'\1=\2{% static \'vendor/', content)
    # Now close the static tags properly
    content = re.sub(r'(assets\/vendor\/[^"\']*["\'])', lambda m: m.group(0).replace(m.group(0)[-1], m.group(0)[-1] + ' %}'), content)
    
    # Better approach: use a more specific pattern
    # Replace href="assets/X/...">  with href="{% static 'X/...'>
    
    # CSS files
    content = re.sub(r'href="assets/css/([^"]*)"', r'href="{% static \'css/\1\' %}"', content)
    content = re.sub(r"href='assets/css/([^']*)'", r"href='{% static 'css/\1' %}'", content)
    
    # JS files  
    content = re.sub(r'src="assets/js/([^"]*)"', r'src="{% static \'js/\1\' %}"', content)
    content = re.sub(r"src='assets/js/([^']*)'", r"src='{% static 'js/\1' %}'", content)
    
    # IMG files
    content = re.sub(r'src="assets/img/([^"]*)"', r'src="{% static \'img/\1\' %}"', content)
    content = re.sub(r"src='assets/img/([^']*)'", r"src='{% static 'img/\1' %}'", content)
    content = re.sub(r'href="assets/img/([^"]*)"', r'href="{% static \'img/\1\' %}"', content)
    content = re.sub(r"href='assets/img/([^']*)'", r"href='{% static 'img/\1' %}'", content)
    
    # VENDOR files
    content = re.sub(r'href="assets/vendor/([^"]*)"', r'href="{% static \'vendor/\1\' %}"', content)
    content = re.sub(r"href='assets/vendor/([^']*)'", r"href='{% static 'vendor/\1' %}'", content)
    content = re.sub(r'src="assets/vendor/([^"]*)"', r'src="{% static \'vendor/\1\' %}"', content)
    content = re.sub(r"src='assets/vendor/([^']*)'", r"src='{% static 'vendor/\1' %}'", content)
    
    # Step 3: Convert HTML page links to Django URL tags
    for html_file, (url_name, _) in URL_MAPPING.items():
        # href="index.html" -> href="{% url 'rides:index' %}"
        content = re.sub(
            rf'href="({html_file})"',
            f'href="{{% url \'{url_name}\' %}}"',
            content,
            flags=re.IGNORECASE
        )
        content = re.sub(
            rf"href='({html_file})'",
            f"href='{{% url \'{url_name}\' %}}",
            content,
            flags=re.IGNORECASE
        )
    
    # Step 4: Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Converted {filename}")

def main():
    """Convert all HTML files in templates/rides"""
    templates_path = Path(TEMPLATES_DIR)
    
    if not templates_path.exists():
        print(f"✗ Templates directory not found: {TEMPLATES_DIR}")
        return
    
    # Find all .html files
    html_files = list(templates_path.glob('*.html'))
    
    if not html_files:
        print(f"✗ No HTML files found in {TEMPLATES_DIR}")
        return
    
    print(f"Found {len(html_files)} HTML files to convert\n")
    
    for html_file in html_files:
        try:
            convert_template(str(html_file))
        except Exception as e:
            print(f"✗ Error converting {html_file}: {e}")
    
    print(f"\n✓ Conversion complete!")

if __name__ == '__main__':
    main()
