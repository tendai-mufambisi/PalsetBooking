from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rides', '0010_sitesettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='pricing_min_km',
            field=models.DecimalField(decimal_places=2, default=13.0, max_digits=6),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='pricing_brackets',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='pricing_above_35_per_km',
            field=models.DecimalField(decimal_places=2, default=1.0, max_digits=6),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='pricing_base_passengers',
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='pricing_extra_adult_fee',
            field=models.DecimalField(decimal_places=2, default=10.0, max_digits=6),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='pricing_free_luggage',
            field=models.PositiveSmallIntegerField(default=5),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='pricing_luggage_fee',
            field=models.DecimalField(decimal_places=2, default=3.0, max_digits=6),
        ),
    ]
