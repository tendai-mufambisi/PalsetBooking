from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rides', '0009_ridebooking_baby_car_seater'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('taxi_owner_email', models.EmailField(default='enquiries@easytransit.co.zw', max_length=254)),
                ('taxi_owner_phone', models.CharField(default='+263789423154', max_length=32)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Site Settings',
            },
        ),
    ]
