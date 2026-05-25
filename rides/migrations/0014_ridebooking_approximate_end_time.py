from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rides', '0013_add_long_distance_chauffeur_ride_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='ridebooking',
            name='approximate_end_time',
            field=models.TimeField(blank=True, null=True),
        ),
    ]
