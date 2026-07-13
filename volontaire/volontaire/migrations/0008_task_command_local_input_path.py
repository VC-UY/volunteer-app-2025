from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("volontaire", "0007_alter_preferencemodel_duree_max_execution_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="command",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="task",
            name="local_input_path",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
