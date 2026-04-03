from django.db import migrations


def switch_hat_previews_to_svg(apps, schema_editor):
    HatModel = apps.get_model('constructor', 'HatModel')
    preview_map = {
        'beanie': 'img/catalog/hats/beanie.svg',
        'hood-scarf': 'img/catalog/hats/hood-scarf.svg',
        'balaclava': 'img/catalog/hats/balaclava.svg',
        'cat-hood': 'img/catalog/hats/cat-hood.svg',
        'pompom-beanie': 'img/catalog/hats/pompom-beanie.svg',
        'ushanka': 'img/catalog/hats/ushanka.svg',
    }
    for slug, asset_path in preview_map.items():
        HatModel.objects.filter(slug=slug).update(preview_asset_path=asset_path)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('constructor', '0008_update_hat_preview_assets'),
    ]

    operations = [
        migrations.RunPython(switch_hat_previews_to_svg, noop_reverse),
    ]
