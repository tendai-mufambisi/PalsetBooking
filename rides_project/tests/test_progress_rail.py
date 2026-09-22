import re, pytest
from django.test import override_settings
from django.urls import reverse

def rail(body):
    frag = body[body.index('class="wz-rail"'):body.index('</ol>')]
    return [(m.group(1), m.group(2)) for m in
            re.finditer(r'wz-step is-(\w+)".*?wz-label">([^<]+)', frag, re.S)]

@pytest.mark.django_db
@override_settings(ENABLE_DEV_FILL=True)
def test_rail_states(monkeypatch, client):
    monkeypatch.setattr('rides.services.distance.DistanceService.get_distance_km',
                        lambda o, d, use_cache=True: 14.0)
    for step, expect_ratio in ((1, '0.0000'), (3, '0.5000'), (5, '1.0000')):
        client.get('/booking/dev-fill/?step=%d' % step)
        b = client.get(reverse('rides:booking_wizard', kwargs={'step': step})).content.decode()
        states = rail(b)
        assert len(states) == 5, states
        assert [s for s, _ in states] == (
            ['done'] * (step - 1) + ['current'] + ['todo'] * (5 - step)), states
        assert '--wz-ratio:%s' % expect_ratio in b, 'fill must match the step'
        # Finished steps are reachable, the rest are not links
        links = re.findall(r'<a class="wz-node" href="([^"]+)"', b)
        assert len(links) == step - 1, links
        print('step %d -> %s' % (step, [s for s, _ in states]))

@pytest.mark.django_db
def test_confirmation_has_no_rail(client):
    b = client.get(reverse('rides:booking_wizard', kwargs={'step': 6}))
    assert b.status_code in (200, 302)
    if b.status_code == 200:
        assert 'wz-rail' not in b.content.decode()
