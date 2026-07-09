"""
Client Redis universel pour la communication entre les composants du système.
"""

import json
import logging
import socket
import threading
import time
import uuid
from typing import Dict, Callable, Any, List, Optional
import redis
from django.conf import settings

from .message import Message, MessageType
from .exceptions import ChannelError, ConnectionError

logger = logging.getLogger(__name__)

class RedisClient:
    """
    Client Redis universel pour la communication entre les composants du système.
    Implémente le pattern Singleton pour garantir une instance unique.
    """
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls, config=None):
        """
        Récupère l'instance unique du client Redis ou en crée une nouvelle.
        
        Args:
            config: Configuration optionnelle pour surcharger les paramètres par défaut
            
        Returns:
            RedisClient: L'instance unique du client
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config)
            return cls._instance
    
    def __init__(self, config=None):
        """
        Initialise le client Redis avec la configuration fournie ou les paramètres par défaut.
        
        Args:
            config: Configuration optionnelle (host, port, db, etc.)
        """
        if RedisClient._instance is not None:
            raise RuntimeError("Utilisez RedisClient.get_instance() pour obtenir l'instance")
        
        self.config = config or {}
        self.client_type = self.config.get('client_type', 'volunteer')
        from redis_communication.utils import get_volunteer_id
        self.client_id = get_volunteer_id() or 'volunteer'
        
        # Paramètres de connexion
        self.host = self.config.get('host', getattr(settings, 'REDIS_PROXY_HOST', '173.249.38.251'))
        self.port = self.config.get('port', getattr(settings, 'REDIS_PROXY_PORT', 6380))
        self.db = self.config.get('db', getattr(settings, 'REDIS_DB', 0))
        
        # État de connexion
        self.connected = False
        self.reconnect_attempts = 0
        
        # Paramètres de reconnexion
        self.reconnect_delay = 5  # Délai initial en secondes
        self.max_reconnect_delay = 60  # Délai maximum
        self.reconnect_multiplier = 1.5  # Multiplicateur pour exponential backoff
        
        # Client Redis (sera initialisé par _initialize_connection)
        self.redis = None
        self.pubsub = None
        self._pubsub_redis = None  # Connexion dédiée écoute (évite conflit PING/pubsub)
        
        # Gestionnaires d'événements par canal (pour réabonnement)
        self.handlers: Dict[str, List[Callable]] = {}
        self.subscribed_channels = set()
        
        # Thread d'écoute et watchdog
        self.listen_thread = None
        self.watchdog_thread = None
        self.running = False
        
        # Statistiques
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'reconnections': 0,
            'connection_errors': 0,
            'last_activity': time.time(),
            'start_time': time.time()
        }
        
        # Initialiser la connexion
        self._initialize_connection()
        
        logger.info(f"Client Redis initialisé: {self.client_type}:{self.client_id} @ {self.host}:{self.port}")
    
    def _initialize_connection(self):
        """
        Initialise ou réinitialise la connexion Redis avec socket keepalive.
        """
        try:
            # Créer le client Redis avec socket keepalive.
            # protocol=2 (RESP2) obligatoire: le proxy coordinateur ne gere pas HELLO/RESP3.
            redis_kwargs = dict(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={
                    socket.TCP_KEEPIDLE: 60,
                    socket.TCP_KEEPINTVL: 10,
                    socket.TCP_KEEPCNT: 3
                },
                socket_connect_timeout=10,
                socket_timeout=5,
                health_check_interval=0,  # Désactiver le health check automatique
                # Evite CLIENT SETINFO: le proxy le filtre sans repondre (timeout)
                lib_name=None,
                lib_version=None,
            )
            try:
                self.redis = redis.Redis(protocol=2, **redis_kwargs)
            except TypeError:
                redis_kwargs.pop('lib_name', None)
                redis_kwargs.pop('lib_version', None)
                try:
                    self.redis = redis.Redis(protocol=2, **redis_kwargs)
                except TypeError:
                    self.redis = redis.Redis(**redis_kwargs)

            # Connexion séparée pour SUBSCRIBE (ne jamais PING sur la même socket que pubsub)
            ps_kwargs = dict(redis_kwargs)
            ps_kwargs['socket_timeout'] = 5
            try:
                self._pubsub_redis = redis.Redis(protocol=2, **ps_kwargs)
            except TypeError:
                self._pubsub_redis = redis.Redis(**ps_kwargs)
            self.pubsub = self._pubsub_redis.pubsub(ignore_subscribe_messages=True)
            
            self.connected = True
            self.reconnect_attempts = 0
            logger.info(f"Connexion Redis établie: {self.host}:{self.port}")
            
        except Exception as e:
            self.connected = False
            logger.error(f"Erreur de connexion Redis: {e}")
            # Ne pas bloquer le démarrage : le watchdog reconnectera
    
    def start(self):
        """
        Démarre les threads d'écoute des messages et de watchdog.
        """
        if self.running:
            logger.warning("Le client est déjà en cours d'exécution")
            return
        
        self.running = True
        
        # Démarrer le thread d'écoute
        self.listen_thread = threading.Thread(target=self._listen_loop)
        self.listen_thread.daemon = True
        self.listen_thread.start()
        logger.info("Thread d'écoute démarré")
        
        # Démarrer le watchdog
        self.watchdog_thread = threading.Thread(target=self._watchdog_loop)
        self.watchdog_thread.daemon = True
        self.watchdog_thread.start()
        logger.info("Watchdog démarré")
        
        logger.info(f"Client Redis démarré avec watchdog: {self.client_type}:{self.client_id}")
        return True
    
    def stop(self):
        """
        Arrête le thread d'écoute et ferme les connexions.
        """
        if not self.running:
            return
        
        self.running = False
        if self.listen_thread:
            self.listen_thread.join(timeout=2.0)
        
        # Désabonnement de tous les canaux
        self.pubsub.unsubscribe()
        self.pubsub.close()
        
        logger.info(f"Client Redis arrêté: {self.client_type}:{self.client_id}")
    
    def subscribe(self, channel: str, handler: Callable[[str, Any], None]):
        """
        S'abonne à un canal et associe un gestionnaire d'événements.
        
        Args:
            channel: Nom du canal
            handler: Fonction de rappel qui sera appelée avec (channel, message)
        """
        # Initialiser la liste des handlers pour ce canal si nécessaire
        if channel not in self.handlers:
            self.handlers[channel] = []
        
        # Vérifier si ce handler existe déjà (par nom de fonction) pour éviter les doublons
        handler_name = getattr(handler, '__name__', str(handler))
        existing_handler_names = [getattr(h, '__name__', str(h)) for h in self.handlers[channel]]
        
        if handler_name not in existing_handler_names:
            self.handlers[channel].append(handler)
            logger.debug(f"Handler '{handler_name}' ajouté pour le canal {channel}")
        else:
            logger.debug(f"Handler '{handler_name}' existe déjà pour le canal {channel}, ignoré")
        
        # Garder trace des canaux souscrits (pour réabonnement)
        self.subscribed_channels.add(channel)
        
        # S'abonner au canal Redis si connecté (et pas déjà abonné)
        if self.connected and self.pubsub:
            try:
                # Vérifier si on n'est pas déjà abonné au niveau Redis
                if not hasattr(self, '_redis_subscribed_channels'):
                    self._redis_subscribed_channels = set()
                
                if channel not in self._redis_subscribed_channels:
                    self.pubsub.subscribe(channel)
                    self._redis_subscribed_channels.add(channel)
                    logger.info(f"Abonné au canal: {channel}")
                else:
                    logger.debug(f"Déjà abonné au canal Redis: {channel}")
            except Exception as e:
                # Ne pas marquer la connexion comme morte: le publish utilise un autre
                # socket, et le proxy peut renvoyer des erreurs non-fatales au SUBSCRIBE.
                logger.error(f"Erreur lors de l'abonnement à {channel}: {e}")
        
        return True
    
    def unsubscribe(self, channel: str, handler: Optional[Callable] = None):
        """
        Se désabonne d'un canal et supprime le(s) gestionnaire(s) associé(s).
        
        Args:
            channel: Nom du canal
            handler: Gestionnaire spécifique à supprimer (si None, tous les gestionnaires sont supprimés)
        """
        if channel in self.handlers:
            if handler is None:
                # Supprimer tous les gestionnaires
                self.handlers[channel] = []
            else:
                # Supprimer un gestionnaire spécifique
                self.handlers[channel] = [h for h in self.handlers[channel] if h != handler]
            
            # Si plus aucun gestionnaire, se désabonner du canal
            if not self.handlers[channel]:
                self.pubsub.unsubscribe(channel)
                del self.handlers[channel]
                
        logger.info(f"Désabonné du canal: {channel}")
        return True
    
    def publish(self, channel: str, message_data: Any, request_id: str = None, token: str = None, message_type: str = None):
        """
        Publie un message sur un canal.
        
        Args:
            channel: Nom du canal
            message_data: Données du message
            request_id: ID de requête optionnel (généré automatiquement si non fourni)
            token: Token JWT pour l'authentification (optionnel)
            message_type: Type de message (request ou response)
            
        Returns:
            str: ID de la requête
        """
        # Vérifier la connexion
        if not self.connected:
            logger.error(f"Impossible de publier sur {channel}: non connecté")
            return None
        
        # Déterminer le type de message en fonction du canal si non spécifié
        if message_type is None:
            if '_response' in channel:
                message_type = "response"
            else:
                message_type = "request"
                
        logger.info(f"Publication d'un message de type '{message_type}' sur le canal {channel}")
        
        # Créer un message standardisé
        message = Message(
            request_id=request_id or str(uuid.uuid4()),
            sender={
                'type': self.client_type,
                'id': self.client_id
            },
            message_type=message_type,
            data=message_data
        )
        
        # Ajouter le token JWT si fourni
        if token:
            message.token = token
            logger.info(f"Token JWT ajouté au message pour le canal {channel}")
        elif channel != 'auth/token_refresh' and not channel.startswith('auth/'):
            from redis_communication.auth_client import load_volunter_credentials, refresh_token_if_needed
            auth_info = load_volunter_credentials()
            if auth_info and 'token' in auth_info:
                # Vérifier si le token n'est pas expiré et le rafraîchir si nécessaire
                last_login = auth_info.get('last_login')
                import datetime
                if datetime.datetime.now() - datetime.datetime.fromtimestamp(last_login) < datetime.timedelta(hours=1):
                    message.token = auth_info['token']
                    logger.info(f"Token JWT valide ajouté au message pour le canal {channel}")
                else:
                    # Token expiré, tenter de le rafraîchir
                    logger.info(f"Token expiré, tentative de rafraîchissement pour le canal {channel}")
                    new_token = refresh_token_if_needed(auth_info)
                    if new_token:
                        message.token = new_token
                        logger.info(f"Token JWT rafraîchi et ajouté au message pour le canal {channel}")
                    else:
                        logger.warning(f"Impossible de rafraîchir le token pour le canal {channel}")
            else:
                logger.warning(f"Aucun token disponible pour le canal {channel}")
        
        # Publier via la connexion dédiée (pas une nouvelle socket à chaque fois)
        try:
            json_message = message.to_json()
            logger.info(f"Message sérialisé pour {channel}: {json_message}")

            if not self.redis:
                raise redis.ConnectionError("Client Redis non initialisé")

            self.redis.publish(channel, json_message)

            self.stats['messages_sent'] += 1
            self.stats['last_activity'] = time.time()

            logger.debug(f"Message publié sur {channel}: {message.request_id}")
            return message.request_id
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Publication {channel} ignorée (Redis lent/hors ligne): {e}")
            self.stats['connection_errors'] += 1
            self.connected = False
            return None
        except Exception as e:
            logger.warning(f"Publication {channel} ignorée: {e}")
            return None
    
    def _reconnect(self):
        """
        Tente de se reconnecter à Redis avec exponential backoff.
        """
        if self.connected:
            return True
        
        self.reconnect_attempts += 1
        backoff = min(
            self.reconnect_delay * (self.reconnect_multiplier ** (self.reconnect_attempts - 1)),
            self.max_reconnect_delay
        )
        
        logger.info(f"Tentative de reconnexion à Redis {self.host}:{self.port}...")
        
        try:
            # Fermer l'ancienne connexion
            if self.pubsub:
                try:
                    self.pubsub.close()
                except Exception:
                    pass
            if self._pubsub_redis:
                try:
                    self._pubsub_redis.close()
                except Exception:
                    pass
            
            # Réinitialiser la connexion
            self._initialize_connection()
            
            # Réabonner aux canaux
            if self.subscribed_channels:
                self._resubscribe_all()
            
            
            logger.info("✅ Reconnexion réussie!")
            self.stats['reconnections'] += 1

            # Reprise immédiate : heartbeat + écoute des assignations
            try:
                from redis_communication.task_handlers import TaskManager
                tm = TaskManager.get_instance()
                if tm.volunteer_id:
                    if not tm.running:
                        tm.start(tm.volunteer_id)
                    else:
                        tm._send_heartbeat()
            except Exception as resume_exc:
                logger.warning("Reprise TaskManager après reconnexion: %s", resume_exc)

            # Vérifier le token d'authentification
            from redis_communication.auth_client import load_volunter_credentials
            from redis_communication.auth_client import get_volunteer_info
            import datetime
            creds = load_volunter_credentials()
            if creds:
                last_login = creds.get('last_login')
                if last_login and datetime.datetime.fromtimestamp(last_login) + datetime.timedelta(hours=24) > datetime.datetime.now():
                    logger.info("✅  Le volontaire était déjà authentifié et token valide")
                    
            else:
                logger.warning("Aucune information d'authentification du volontaire disponible après reconnexion")
            return True
            
        except Exception as e:
            logger.warning(f"Échec de reconnexion (tentative {self.reconnect_attempts}): {e}")
            import traceback
            logger.error(traceback.format_exc())
            logger.info(f"Nouvelle tentative dans {backoff:.1f}s...")
            time.sleep(backoff)
            return False
    
    def _resubscribe_all(self):
        """
        Réabonne à tous les canaux après une reconnexion.
        """
        logger.info(f"Réabonnement à {len(self.subscribed_channels)} canaux...")
        
        for channel in self.subscribed_channels:
            try:
                self.pubsub.subscribe(channel)
                logger.info(f"  ✓ Réabonné à {channel}")
            except Exception as e:
                logger.error(f"  ✗ Erreur réabonnement à {channel}: {e}")
    
    def _watchdog_loop(self):
        """
        Thread de surveillance qui vérifie périodiquement la connexion.
        """
        while self.running:
            time.sleep(10)  # Vérifier toutes les 10 secondes
            
            if not self.connected:
                logger.warning("⚠️ Déconnexion détectée par le watchdog")
                # Tenter de se reconnecter
                while self.running and not self.connected:
                    if self._reconnect():
                        break
                    time.sleep(1)
            else:
                # Vérifier l'activité récente (ne pas PING sur la connexion pubsub)
                idle = time.time() - self.stats.get('last_activity', 0)
                if idle > 120:
                    logger.warning("⚠️ Watchdog: inactivité Redis > 120s, reconnexion")
                    self.connected = False
                    self.stats['connection_errors'] += 1
    
    def _listen_loop(self):
        """
        Boucle d'écoute des messages dans un thread séparé.
        """
        while self.running:
            try:
                # Si déconnecté, attendre la reconnexion
                if not self.connected:
                    time.sleep(1)
                    continue
                
                message = self.pubsub.get_message(timeout=0.1)
                if message and message['type'] == 'message':
                    channel = message['channel']
                    data = message['data']
                    
                    try:
                        # Décoder le message
                        logger.warning(f"Message reçu sur le canal {channel}: {data}")
                        msg_obj = Message.from_json(data)
                        # logger.info(f"Message désérialisé sur {channel}: request_id={msg_obj.request_id}, data={msg_obj.data}")
                        
                        # Mettre à jour les statistiques
                        self.stats['messages_received'] += 1
                        self.stats['last_activity'] = time.time()
                        
                        # Appeler les gestionnaires pour ce canal
                        if channel in self.handlers:
                            logger.info(f"Gestionnaires trouvés pour le canal {channel}: {len(self.handlers[channel])}")
                            for handler in self.handlers[channel]:
                                try:
                                    logger.info(f"Appel du gestionnaire {handler.__name__ if hasattr(handler, '__name__') else 'anonyme'} pour {channel}")
                                    handler(channel, msg_obj)
                                except Exception as e:
                                    import traceback
                                    logger.error(f"Erreur dans le gestionnaire pour {channel}: {e}")
                                    logger.error(traceback.format_exc())
                        else:
                            logger.warning(f"Aucun gestionnaire pour le canal {channel}")
                    except json.JSONDecodeError as je:
                        logger.error(f"Message non JSON sur {channel}: {data}")
                        logger.error(f"Erreur de décodage JSON: {je}")
                    except Exception as e:
                        import traceback
                        logger.error(f"Erreur lors du traitement du message: {e}")
                        logger.error(traceback.format_exc())
                elif message is not None:
                    logger.error(f"Message recu inconne donc ignoré. Message: {message}")
                # Petite pause pour éviter de surcharger le CPU
                time.sleep(0.01)
                
            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.error(f"Erreur de connexion Redis: {e}")
                self.connected = False
                self.stats['connection_errors'] += 1
                time.sleep(1.0)
            except redis.RedisError as e:
                logger.error(f"Erreur Redis: {e}")
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"Erreur inattendue: {e}")
                time.sleep(1.0)
    
    def get_stats(self):
        """
        Récupère les statistiques du client.
        
        Returns:
            dict: Statistiques d'utilisation
        """
        return {
            **self.stats,
            'subscribed_channels': list(self.handlers.keys()),
            'uptime': time.time() - self.stats.get('start_time', time.time()),
            'connected': self.connected,
            'reconnect_attempts': self.reconnect_attempts
        }