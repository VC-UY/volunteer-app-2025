# import os
import docker

# Remplace par ton UID si besoin
# os.environ["DOCKER_HOST"] = "unix:///run/user/1000/docker.sock"

client = docker.from_env()
print([img.tags for img in client.images.list()])
