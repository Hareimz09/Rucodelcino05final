from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def cleanup_hat_catalog(apps, schema_editor):
    HatModel = apps.get_model('constructor', 'HatModel')

    HatModel.objects.filter(slug__in=['beanie', 'pompom-beanie', 'hood-scarf']).update(is_active=True)
    HatModel.objects.filter(slug='beanie').update(sort_order=10, name='Бини')
    HatModel.objects.filter(slug='pompom-beanie').update(sort_order=20, name='Бини с помпоном')
    HatModel.objects.filter(slug='hood-scarf').update(sort_order=30, name='Капор-шарф')
    HatModel.objects.filter(slug__in=['cat-hood', 'chepchik', 'balaclava', 'ushanka']).update(is_active=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('constructor', '0011_gallery_social'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='gallerycomment',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='replies', to='constructor.gallerycomment'),
        ),
        migrations.CreateModel(
            name='GalleryCommentVote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.SmallIntegerField(choices=[(1, 'Палец вверх'), (-1, 'Палец вниз')])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('comment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to='constructor.gallerycomment')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gallery_comment_votes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at',),
                'constraints': [models.UniqueConstraint(fields=('user', 'comment'), name='uniq_gallery_comment_vote_per_user')],
            },
        ),
        migrations.RunPython(cleanup_hat_catalog, noop_reverse),
    ]
