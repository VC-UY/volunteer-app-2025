"""Docker retiré — stub pour éviter les imports cassés dans la copie imbriquée."""


class DockerManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        raise RuntimeError(
            "Docker a été retiré. Utilisez volontaire.services.runtime_client.RuntimeClient."
        )
