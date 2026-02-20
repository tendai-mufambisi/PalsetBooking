"""Add human-friendly reference to RideBooking and populate existing rows."""
from django.db import migrations, models
import re


def forwards(apps, schema_editor):
    import datetime
    RideBooking = apps.get_model('rides', 'RideBooking')
    # use year-based prefix like ET26
    yy = datetime.date.today().year % 100
    prefix = f'ET{yy:02d}'
    refs = RideBooking.objects.filter(reference__startswith=prefix).values_list('reference', flat=True)
    max_num = 0
    for r in refs:
        if not r:
            continue
        m = re.match(rf'^{re.escape(prefix)}(\d+)$', r)
        if m:
            try:
                n = int(m.group(1))
                if n > max_num:
                    max_num = n
            except Exception:
                continue

    qs = RideBooking.objects.filter(reference__isnull=True).order_by('created_at')
    for b in qs:
        max_num += 1
        b.reference = f'{prefix}{max_num:03d}'
        b.save(update_fields=['reference'])


def backwards(apps, schema_editor):
    # no-op: we won't remove references on reverse
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rides', '0006_add_passengers_json'),
    ]

    operations = [
        migrations.AddField(
            model_name='ridebooking',
            name='reference',
            field=models.CharField(max_length=16, unique=True, null=True, blank=True),
        ),
        migrations.RunPython(forwards, backwards),
    ]
