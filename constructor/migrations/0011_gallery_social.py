from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('constructor', '0010_refresh_hat_catalog_for_shop_update'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='tryongeneration',
            name='gallery_description',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='tryongeneration',
            name='gallery_title',
            field=models.CharField(blank=True, max_length=140),
        ),
        migrations.AddField(
            model_name='tryongeneration',
            name='is_public_gallery',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='GalleryComment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('generation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gallery_comments', to='constructor.tryongeneration')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gallery_comments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('created_at',),
            },
        ),
        migrations.CreateModel(
            name='GalleryLike',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('generation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gallery_likes', to='constructor.tryongeneration')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gallery_likes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at',),
                'constraints': [models.UniqueConstraint(fields=('user', 'generation'), name='uniq_gallery_like_per_user_generation')],
            },
        ),
    ]
