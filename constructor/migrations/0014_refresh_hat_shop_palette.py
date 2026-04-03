from django.db import migrations


def refresh_hat_shop_palette(apps, schema_editor):
    HatModel = apps.get_model('constructor', 'HatModel')
    YarnBrand = apps.get_model('constructor', 'YarnBrand')
    YarnColor = apps.get_model('constructor', 'YarnColor')

    HatModel.objects.filter(slug='hood-scarf').update(is_active=False)

    brand_specs = [
        (
            'alize-lanagold',
            'ALIZE Lanagold',
            [
                ('milk-lanagold', 'Молочный', '#F2EEE6'),
                ('beige-lanagold', 'Бежевый', '#D8BEA4'),
                ('dry-rose-lanagold', 'Сухая роза', '#B98D97'),
                ('denim-lanagold', 'Джинсовый', '#5E7DA8'),
            ],
        ),
        (
            'lanoso-alpacana',
            'Lanoso Alpacana',
            [
                ('cream-alpacana', 'Кремовый', '#E8E0D4'),
                ('coffee-alpacana', 'Кофейный', '#8C6A59'),
                ('denim-alpacana', 'Деним', '#6E8FA8'),
                ('graphite-alpacana', 'Графит', '#62656C'),
            ],
        ),
    ]

    used_brand_ids = []
    used_color_ids = []
    sort_order = 10
    for brand_slug, brand_name, colors in brand_specs:
        brand, _ = YarnBrand.objects.get_or_create(slug=brand_slug, defaults={'name': brand_name})
        brand.name = brand_name
        brand.is_active = True
        brand.sort_order = sort_order
        brand.save(update_fields=['name', 'is_active', 'sort_order'])
        used_brand_ids.append(brand.id)
        sort_order += 10

        color_sort = 10
        for color_slug, color_name, hex_value in colors:
            color, _ = YarnColor.objects.get_or_create(
                brand=brand,
                slug=color_slug,
                defaults={'name': color_name, 'hex_value': hex_value},
            )
            color.name = color_name
            color.hex_value = hex_value
            color.is_active = True
            color.sort_order = color_sort
            color.save(update_fields=['name', 'hex_value', 'is_active', 'sort_order'])
            used_color_ids.append(color.id)
            color_sort += 10

    YarnBrand.objects.exclude(id__in=used_brand_ids).update(is_active=False)
    YarnColor.objects.exclude(id__in=used_color_ids).update(is_active=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('constructor', '0013_tryongeneration_title_was_edited'),
    ]

    operations = [
        migrations.RunPython(refresh_hat_shop_palette, noop_reverse),
    ]
