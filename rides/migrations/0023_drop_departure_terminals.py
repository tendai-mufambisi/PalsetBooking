from django.db import migrations


REMOVED = {'Departures / Drop-off', 'Private & Charter Terminal'}


def drop_departure_terminals(apps, schema_editor):
    """Stop offering the departures and private terminals as collection points.

    We only meet passengers in the arrivals halls, so those two options only ever
    produced bookings the driver had to ring back about. Anything else the owner
    added in the dashboard is left alone, and a site whose list is empty keeps
    falling through to the model default.
    """
    SiteSettings = apps.get_model('rides', 'SiteSettings')
    for row in SiteSettings.objects.all():
        terminals = row.airport_terminals or []
        kept = [t for t in terminals if str(t).strip() not in REMOVED]
        if kept != terminals:
            row.airport_terminals = kept
            row.save(update_fields=['airport_terminals'])


def restore_departure_terminals(apps, schema_editor):
    """Nothing to restore — the list stays editable in the dashboard."""


class Migration(migrations.Migration):

    dependencies = [
        ('rides', '0022_ridebooking_paylink_card_name_and_more'),
    ]

    operations = [
        migrations.RunPython(drop_departure_terminals, restore_departure_terminals),
    ]
