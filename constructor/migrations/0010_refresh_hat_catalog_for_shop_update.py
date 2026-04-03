from django.db import migrations


def refresh_hat_catalog(apps, schema_editor):
    HatModel = apps.get_model('constructor', 'HatModel')

    active_rows = [
        ('beanie', 'Бини', 'img/catalog/hats/beanie.svg', 'Классическая базовая модель.', 10),
        ('pompom-beanie', 'Бини с помпоном', 'img/catalog/hats/pompom-beanie.svg', 'Бини с аккуратным помпоном.', 20),
        ('hood-scarf', 'Капор-шарф', 'img/catalog/hats/hood-scarf.svg', 'Мягкий капор с удлинённой формой.', 30),
        ('cat-hood', 'Капор с ушками', 'img/catalog/hats/cat-hood.svg', 'Капор с декоративными ушками.', 40),
        ('chepchik', 'Чепчик', 'img/catalog/hats/chepchik.svg', 'Вязаный чепчик с завязками.', 50),
    ]

    for slug, name, asset_path, description, sort_order in active_rows:
        HatModel.objects.update_or_create(
            slug=slug,
            defaults={
                'name': name,
                'preview_asset_path': asset_path,
                'description': description,
                'sort_order': sort_order,
                'is_active': True,
                'render_preset': {},
            },
        )

    HatModel.objects.filter(slug__in=['balaclava', 'ushanka']).update(is_active=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('constructor', '0009_switch_hat_previews_to_svg'),
    ]

    operations = [
        migrations.RunPython(refresh_hat_catalog, noop_reverse),
    ]
