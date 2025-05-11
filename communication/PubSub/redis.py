import redis
import threading


class RedisPubSubManager:
    def __init__(self, host='192.168.1.117', port=6379, db=0, channels=None):
        self.host = host
        self.port = port
        self.db = db
        self.channels = channels or [] 
        self.redis_client = None
        self.pubsub = None
        self.listener_thread = None
        self.subscribed = False

    def connect(self):
        """Établit une connexion au broker Redis."""
        self.redis_client = redis.Redis(
            host=self.host,
            port=self.port,
            db=self.db,
            decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()
        print("[INFO] Connexion Redis établie.")

    def subscribe(self, callback):
        """Souscrit aux canaux et démarre l'écoute avec le callback."""
        if not self.redis_client or not self.pubsub:
            raise ConnectionError("Pas de connexion Redis. Appelez d'abord connect().")
        
        if not self.channels:
            raise ValueError("Aucun canal spécifié pour la souscription.")
        
        self.pubsub.subscribe(**{channel: callback for channel in self.channels})
        self.subscribed = True
        self.listener_thread = threading.Thread(target=self._listen, daemon=True)
        self.listener_thread.start()
        print(f"[INFO] Souscrit aux canaux : {self.channels}")

    def _listen(self):
        """Boucle d'écoute des messages."""
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                # Les callbacks sont appelés automatiquement
                pass

    def publish(self, channel, message):
        """Publie un message sur un canal."""
        if not self.redis_client:
            raise ConnectionError("Connexion Redis manquante.")
        self.redis_client.publish(channel, message)

    def unsubscribe_channel(self, channel):
        """Se désabonne d'un canal spécifique."""
        if self.pubsub and channel in self.channels:
            self.pubsub.unsubscribe(channel)
            self.channels.remove(channel)
            print(f"[INFO] Désabonné du canal : {channel}")
        else:
            print(f"[WARN] Canal {channel} non trouvé ou pas souscrit.")

    def unsubscribe_all(self):
        """Se désabonne de tous les canaux."""
        if self.pubsub:
            self.pubsub.unsubscribe()
            self.channels = []
            self.subscribed = False
            print("[INFO] Désabonné de tous les canaux.")

    def close(self):
        """Ferme proprement la connexion et les souscriptions."""
        self.unsubscribe_all()
        if self.pubsub:
            self.pubsub.close()
        self.redis_client = None
        self.pubsub = None
        print("[INFO] Connexion Redis fermée.")






