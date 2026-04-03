from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("constructor", "0012_gallery_comment_votes_and_hat_cleanup"),
    ]

    operations = [
        migrations.AddField(
            model_name="tryongeneration",
            name="title_was_edited",
            field=models.BooleanField(default=False),
        ),
    ]
