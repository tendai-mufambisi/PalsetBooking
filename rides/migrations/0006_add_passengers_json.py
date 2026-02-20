"""Add passengers_json field to RideBooking."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rides", "0005_rename_flight_arrival_date_ridebooking_arrival_date_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ridebooking",
            name="passengers_json",
            field=models.JSONField(null=True, blank=True),
        ),
    ]
