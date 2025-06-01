import os
import docker

# Remplace par ton UID si besoin
os.environ["DOCKER_HOST"] = "unix:///run/user/1000/docker.sock"

client = docker.from_env()
print([img.tags for img in client.images.list()])


from docker_manager import DockerManager as DM 


print("Lancement de l'image")
dm = DM.get_instance()
volumes = {
    '/home/sergeo/Master-II/Recherches/Projet_M_I/Groupe A VolunteerApp/volunteer-app-2025/.volunteer/tasks/1': {'bind': '/app/output', 'mode': 'rw'},
    '/home/sergeo/Master-II/Recherches/Projet_M_I/Groupe A VolunteerApp/volunteer-app-2025/.volunteer/tasks/b602c2aa-4124-435f-aa16-e99107e8ad11/input':{'bind': '/app/input', 'mode': 'ro'}
        }
container = dm.run_container(
    image_name='traning-test',
    task_id=1, 
    volumes= volumes
)
print(container.exec_run("ls input")) 
print(container.exec_run("cat train_on_shard.py"))
print(container.logs())


from datetime import datetime, timezone

def parse_docker_time(timestr):
    # Exemple : '2025-05-31T17:37:59.156252358+00:00'
    if '.' in timestr:
        date_part, frac_part = timestr.split('.')
        frac_part, tz = frac_part[:9], ''
        if '+' in frac_part or '-' in frac_part:
            for sep in ['+', '-']:
                if sep in frac_part:
                    frac_part, tz = frac_part.split(sep)
                    tz = sep + tz
                    break
        frac_part = frac_part[:6]  # Garder 6 chiffres max
        timestr = f"{date_part}.{frac_part}{tz}"
    return datetime.fromisoformat(timestr)

container.wait()
container.reload()

started_at = container.attrs["State"]["StartedAt"]
finished_at = container.attrs["State"]["FinishedAt"]

started_dt = parse_docker_time(started_at)
finished_dt = parse_docker_time(finished_at)

lifetime = finished_dt - started_dt

print(f"🕒 Temps total d'exécution : {lifetime.total_seconds():.2f} secondes")

print([cnt for cnt in client.containers.list()])



