from django.db import migrations


def update_hat_preview_assets(apps, schema_editor):
    HatModel = apps.get_model('constructor', 'HatModel')
    preview_map = {
        'beanie': 'img/catalog/hats/beanie.png',
        'hood-scarf': 'img/catalog/hats/hood-scarf.png',
        'balaclava': 'img/catalog/hats/balaclava.png',
        'cat-hood': 'img/catalog/hats/cat-hood.png',
        'pompom-beanie': 'img/catalog/hats/pompom-beanie.png',
        'ushanka': 'img/catalog/hats/ushanka.png',
    }
    for slug, asset_path in preview_map.items():
        HatModel.objects.filter(slug=slug).update(preview_asset_path=asset_path, is_active=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('constructor', '0007_update_yarn_brands'),
    ]

    operations = [
        migrations.RunPython(update_hat_preview_assets, noop_reverse),
    ]
