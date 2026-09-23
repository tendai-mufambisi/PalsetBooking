import re, pytest
from django.test import override_settings
from django.urls import reverse

@pytest.mark.django_db
@override_settings(ENABLE_DEV_FILL=True)
def test_transition_contract(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    client.get('/booking/dev-fill/?step=3')
    b = client.get(reverse('rides:booking_wizard', kwargs={'step': 3})).content.decode()

    # Direction is resolved before paint, in the head
    head = b[:b.index('</head>')]
    assert 'data-wz-dir' in head, 'direction must be set before first paint'
    assert 'wz-last-step' in head

    # Everything the step renders travels as one stage
    assert 'class="wz-stage"' in b
    stage = b[b.index('class="wz-stage"'):b.index('</main>')]
    assert 'id="step3_form"' in stage and '<form' in stage

    # Back target handed to the shell, so the exit can play first
    assert 'data-wz-prev="/booking/step/2/"' in b

    # Hardware-accelerated only: no width/height/margin in the step keyframes
    css = b[b.index('<style>'):b.index('</style>')]
    for name in ('wz-enter-forward', 'wz-enter-back', 'wz-exit-forward', 'wz-exit-back', 'wz-rise'):
        block = re.search(r'@keyframes ' + name + r'\s*\{(.*?)\n        \}', css, re.S)
        assert block, name
        body = block.group(1)
        assert 'translate3d' in body, name
        for banned in ('width:', 'height:', 'margin', 'left:', 'top:'):
            assert banned not in body, '%s animates %s' % (name, banned)

    # Timing and curve per brief
    assert 'cubic-bezier(0.16, 1, 0.3, 1)' in css
    dur = int(re.search(r'--wz-in:\s*(\d+)ms', css).group(1))
    assert 400 <= dur <= 500, dur
    stag = int(re.search(r'--wz-stagger:\s*(\d+)ms', css).group(1))
    assert 30 <= stag <= 50, stag

    # Sliding must not raise a horizontal scrollbar
    assert re.search(r'body\s*\{[^}]*overflow-x:\s*hidden', css, re.S)

@pytest.mark.django_db
@override_settings(ENABLE_DEV_FILL=True)
def test_first_arrival_has_no_direction(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    b = client.get(reverse('rides:booking_wizard_start')).content.decode()
    # Step 1 still ships the resolver; it simply has nothing to compare against
    assert 'wz-last-step' in b
    assert 'wz-enter-plain' in b


@pytest.mark.django_db
@override_settings(ENABLE_DEV_FILL=True)
def test_step_scripts_do_not_reach_forward_into_the_dock(monkeypatch, client):
    """A step's inline script runs while the page is still being parsed.

    The action dock is rendered after the stage, so anything the script
    dereferences straight away has to appear before it in the document -
    otherwise getElementById returns null and the whole script dies on the
    spot, taking every listener registered after it with it. That is what
    silently broke Back on steps 2-4 and left the payment dialogs stuck open.

    Work deferred with wzReady() runs after parsing, so it may look forward.
    """
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    client.get('/booking/dev-fill/?step=5')

    def blank_out_deferred(text):
        """Replace each wzReady(...) call with spaces, keeping every offset."""
        out = list(text)
        start = text.find('wzReady(')
        while start != -1:
            depth, i = 0, text.index('(', start)
            while i < len(text):
                if text[i] == '(':
                    depth += 1
                elif text[i] == ')':
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            for j in range(start, min(i + 1, len(text))):
                out[j] = ' '
            start = text.find('wzReady(', i + 1)
        return ''.join(out)

    # Step 6 needs a confirmed booking to render, and carries no dock script.
    for step in (1, 2, 3, 4, 5):
        body = client.get(reverse('rides:booking_wizard', kwargs={'step': step})).content.decode()
        immediate = blank_out_deferred(body)

        # An immediate dereference: getElementById('x') followed by a property
        for match in re.finditer(r"getElementById\('([\w\-]+)'\)\s*\.", immediate):
            element = body.find('id="%s"' % match.group(1))
            assert element != -1, 'step %d references a missing id: %s' % (step, match.group(1))
            assert element < match.start(), (
                'step %d dereferences #%s before the parser has reached it'
                % (step, match.group(1)))
