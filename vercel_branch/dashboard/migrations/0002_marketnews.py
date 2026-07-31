from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="MarketNews",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(db_index=True, default="Investing RSS", max_length=50)),
                ("external_id", models.CharField(max_length=64, unique=True)),
                ("title", models.TextField()),
                ("summary", models.TextField(blank=True)),
                ("url", models.URLField(max_length=1000)),
                ("category", models.CharField(db_index=True, max_length=40)),
                ("published_at", models.DateTimeField(db_index=True)),
                ("collected_at", models.DateTimeField(auto_now_add=True)),
                ("relevance_score", models.PositiveSmallIntegerField(db_index=True, default=0)),
                ("win_relevance", models.PositiveSmallIntegerField(default=0)),
                ("wdo_relevance", models.PositiveSmallIntegerField(default=0)),
                ("markets", models.JSONField(blank=True, default=list)),
                ("topics", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={"ordering": ["-published_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="marketnews",
            index=models.Index(fields=["category", "-published_at"], name="dashboard_n_cat_pub_idx"),
        ),
        migrations.AddIndex(
            model_name="marketnews",
            index=models.Index(fields=["relevance_score", "-published_at"], name="dashboard_n_rel_pub_idx"),
        ),
    ]
