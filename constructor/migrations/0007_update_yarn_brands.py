from django.db import migrations


def update_yarn_catalog(apps, schema_editor):
    YarnBrand = apps.get_model('constructor', 'YarnBrand')
    YarnColor = apps.get_model('constructor', 'YarnColor')

    brand_specs = [
        (
            'alize-lanagold',
            'ALIZE Lanagold',
            [
                ('lavender-lanagold', 'Лавандовый', '#C5A0BD'),
                ('dusty-rose-lanagold', 'Пыльная роза', '#C493A8'),
                ('milk-lanagold', 'Молочный', '#EFE9DF'),
            ],
        ),
        (
            'alize-superlana-maxi',
            'ALIZE Superlana Maxi',
            [
                ('lilac-superlana', 'Лиловый', '#B4889C'),
                ('powder-plum-superlana', 'Пудровая слива', '#9F7D8B'),
                ('graphite-superlana', 'Графит', '#5E6269'),
            ],
        ),
        (
            'lanoso-alpacana',
            'Lanoso Alpacana',
            [
                ('denim-alpacana', 'Деним', '#6E8FA8'),
                ('steel-blue-alpacana', 'Стальной голубой', '#5D798F'),
                ('cream-alpacana', 'Кремовый', '#E8E0D4'),
            ],
        ),
    ]

    used_brand_ids = []
    used_color_ids = []
    sort_index = 10
    color_sort = 10

    for brand_slug, brand_name, colors in brand_specs:
        brand, _ = YarnBrand.objects.get_or_create(slug=brand_slug, defaults={'name': brand_name})
        brand.name = brand_name
        brand.sort_order = sort_index
        brand.is_active = True
        brand.save(update_fields=['name', 'sort_order', 'is_active'])
        used_brand_ids.append(brand.id)
        sort_index += 10

        local_sort = 10
        for color_slug, color_name, hex_value in colors:
            color, _ = YarnColor.objects.get_or_create(
                brand=brand,
                slug=color_slug,
                defaults={'name': color_name, 'hex_value': hex_value},
            )
            color.name = color_name
            color.hex_value = hex_value
            color.sort_order = local_sort
            color.is_active = True
            color.save(update_fields=['name', 'hex_value', 'sort_order', 'is_active'])
            used_color_ids.append(color.id)
            local_sort += 10
        color_sort += 10

    YarnBrand.objects.exclude(id__in=used_brand_ids).update(is_active=False)
    YarnColor.objects.exclude(id__in=used_color_ids).update(is_active=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('constructor', '0006_catalog_and_master_inquiry'),
    ]

    operations = [
        migrations.RunPython(update_yarn_catalog, noop_reverse),
    ]
