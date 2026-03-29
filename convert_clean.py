#!/usr/bin/env python3
"""
Clean conversion of HTML to Django templates
"""

import re
from pathlib import Path

TEMPLATES_DIR = r"c:\Users\BIGSAM TECH\Desktop\PalsetBooking\templates\rides"

URL_MAPPING = {
    'index.html': 'rides:index',
    'about.html': 'rides:about',
    'airport-transfers.html': 'rides:airport_transfers',
    'corporate-transfers.html': 'rides:corporate_transfers',
    'chauffeur-drive.html': 'rides:chauffeur_drive',
    'private-tours.html': 'rides:private_tours',
    'group-transfers.html': 'rides:group_transfers',
    'point-transfers.html': 'rides:point_transfers',
    'car-rental.html': 'rides:car_rental',
    'special-events.html': 'rides:special_events',
    'long-distance.html': 'rides:long_distance',
    'dinner-transfers.html': 'rides:dinner_transfers',
    'fleet.html': 'rides:fleet',
    'tours.html': 'rides:tours',
    'gallery.html': 'rides:gallery',
    'blog.html': 'rides:blog',
    'blog-details.html': 'rides:blog_details',
    'booking.html': 'rides:booking_page',
    'contact.html': 'rides:contact',
    'testimonials.html': 'rides:testimonials',
    'faq.html': 'rides:faq',
    'terms.html': 'rides:terms',
    'privacy.html': 'rides:privacy',
    'services.html': 'rides:services',
}

def convert_file(file_path):
    """Convert a single HTML file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    filename = Path(file_path).name
    print(f"Converting {filename}...")
    
    # Add {% load static %} at the beginning (after any existing doctype/comments)
    if lines and '{% load static %}' not in ''.join(lines):
        # Insert after <!DOCTYPE or at line 0
        insert_pos = 0
        for i, line in enumerate(lines):
            if '<!DOCTYPE' in line or '<html' in line.lower():
                insert_pos = i
                break
        lines.insert(insert_pos, '{% load static %}\n')
    
    # Join and process
    content = ''.join(lines)
    
    # CONVERT STATIC PATHS
    # Pattern: find "assets/[TYPE]/[FILE]" and wrap appropriately
    
    # Handle href="assets/css/..." -> href="{% static 'css/...' %}"
    content = re.sub(
        r'href="assets/css/([^"]+)"',
        r'href="{% static \'css/\1\' %}"',
        content
    )
    
    # Handle src="assets/js/..." -> src="{% static 'js/...' %}"
    content = re.sub(
        r'src="assets/js/([^"]+)"',
        r'src="{% static \'js/\1\' %}"',
        content
    )
    
    # Handle href="assets/img/..." and src="assets/img/..."
    content = re.sub(
        r'href="assets/img/([^"]+)"',
        r'href="{% static \'img/\1\' %}"',
        content
    )
    content = re.sub(
        r'src="assets/img/([^"]+)"',
        r'src="{% static \'img/\1\' %}"',
        content
    )
    
    # Handle href="assets/vendor/..." and src="assets/vendor/..."
    content = re.sub(
        r'href="assets/vendor/([^"]+)"',
        r'href="{% static \'vendor/\1\' %}"',
        content
    )
    content = re.sub(
        r'src="assets/vendor/([^"]+)"',
        r'src="{% static \'vendor/\1\' %}"',
        content
    )
    
    # CONVERT PAGE LINKS
    # href="about.html" -> href="{% url 'rides:about' %}"
    for html_file, url_name in URL_MAPPING.items():
        content = re.sub(
            rf'href="{html_file}"',
            f'href="{{% url \'{url_name}\' %}}',
            content
        )
        # Also handle case variations like #about.html
        content = re.sub(
            rf'href="#?({html_file})"',
            f'href="{{% url \'{url_name}\' %}}',
            content
        )
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ {filename}")

def main():
    templates_path = Path(TEMPLATES_DIR)
    html_files = sorted([f for f in templates_path.glob('*.html') if f.name != 'base.html'])
    
    print(f"Found {len(html_files)} HTML files to convert\n")
    
    for html_file in html_files:
        try:
            convert_file(str(html_file))
        except Exception as e:
            print(f"✗ Error converting {html_file.name}: {e}")

    print(f"\n✓ Conversion complete!")

if __name__ == '__main__':
    main()
