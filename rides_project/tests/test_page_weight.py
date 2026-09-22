import re, pytest
from django.urls import reverse

@pytest.mark.django_db
def test_no_render_blocking_bootstrap(client):
    """Bootstrap was 229KB standing in front of the first paint on every step."""
    b = client.get(reverse('rides:booking_wizard_start')).content.decode()
    head = b[:b.index('</head>')]

    assert 'bootstrap.min.css' not in b
    assert 'bootstrap.bundle' not in b
    # The icon font is the one external stylesheet left
    sheets = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', head)
    assert sheets == ['https://cdn.jsdelivr.net/npm/bootstrap-icons/font/bootstrap-icons.css'], sheets
    # ...and its connection is warmed first
    assert 'rel="preconnect" href="https://cdn.jsdelivr.net"' in head

    # Form controls must still inherit the page font without Reboot
    css = b[b.index('<style>'):b.index('</style>')]
    assert re.search(r'input, button, select, textarea[^{]*\{[^}]*font-family:\s*inherit', css, re.S)

@pytest.mark.django_db
def test_loading_indicator_survives_the_gap(client):
    b = client.get(reverse('rides:booking_wizard_start')).content.decode()
    # Fixed and outside the stage, so the step sliding away cannot take it
    assert 'class="wz-loadbar"' in b
    assert b.index('class="wz-loadbar"') < b.index('class="wz-stage"')
    css = b[b.index('<style>'):b.index('</style>')]
    assert re.search(r'\.wz-loadbar\s*\{[^}]*position:\s*fixed', css, re.S)
    assert '[data-wz-leaving] .wz-loadbar' in css
