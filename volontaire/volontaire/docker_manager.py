"""
Docker n'est plus utilisé. Conservé uniquement pour éviter les imports cassés
dans d'anciens scripts / copies imbriquées. Toute utilisation lève une erreur.
"""


class DockerManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        raise RuntimeError(
            "Docker a été retiré de l'application volontaire. "
            "Utilisez le runtime vc-uyr (volontaire.services.runtime_client.RuntimeClient)."
        )
