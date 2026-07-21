from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("volontaire", "0008_task_command_local_input_path"),
    ]

    operations = [
        migrations.RenameField(
            model_name="task",
            old_name="docker_information",
            new_name="runtime_info",
        ),
    ]
