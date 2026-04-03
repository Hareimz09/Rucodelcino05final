from django.db import migrations


def trim_hat_catalog_and_assets(apps, schema_editor):
    HatModel = apps.get_model('constructor', 'HatModel')
    HatModel.objects.filter(slug__in=['beanie', 'pompom-beanie']).update(is_active=True)
    HatModel.objects.exclude(slug__in=['beanie', 'pompom-beanie']).update(is_active=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('constructor', '0014_refresh_hat_shop_palette'),
    ]

    operations = [
        migrations.RunPython(trim_hat_catalog_and_assets, noop_reverse),
    ]
