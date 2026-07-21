from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("volontaire", "0011_task_command"),
    ]

    operations = [
        migrations.RenameField(
            model_name="task",
            old_name="docker_information",
            new_name="runtime_info",
        ),
    ]
