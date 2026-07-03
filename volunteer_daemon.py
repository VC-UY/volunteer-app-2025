#!/usr/bin/env python3
"""
Service daemon principal pour le volontaire.
Gère le cycle de vie complet du volontaire en tant que service système.
"""

import os
import sys
import signal
import logging
import time
import threading
import json
import uuid
import hashlib
import socket
from pathlib import Path
from datetime import datetime

# Ajouter le chemin du projet
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Fichier de statistiques partagé
STATS_FILE = BASE_DIR / '.volunteer' / 'agent_stats.json'

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

from redis_communication.client import RedisClient
from redis_communication.handlers import DEFAULT_HANDLERS
from redis_communication.auth_client import  get_volunteer_info

# Configuration du logging
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'volunteer_daemon.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('VolunteerDaemon')

# Import des fonctions de l'agent pour la collecte de données
import gzip
try:
    from agent import (
        collect_initial_data, 
        collect_variable_data, 
        initialize_data_collection,
        DATA_DIR as AGENT_DATA_DIR
    )
    AGENT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Module agent non disponible: {e}")
    AGENT_AVAILABLE = False


class VolunteerDaemon:
    """Daemon principal du volontaire"""
    
    def __init__(self):
        self.running = False
        self.redis_client = None
        self.data_collection_thread = None
        self.task_listener_thread = None
        self.stats_thread = None
        self.connection_retry_delay = 30  # Délai entre les tentatives de connexion
        
        # Statistiques de l'agent
        self.agent_stats = {
            'status': 'stopped',
            'connected': False,
            'start_time': None,
            'messages_sent': 0,
            'messages_received': 0,
            'files_collected': 0,
            'files_sent': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'data_collected_mb': 0.0,
            'data_sent_mb': 0.0,
            'reconnections': 0,
            'last_sync': None,
            'last_error': None,
            'uptime_seconds': 0
        }
        
        # Créer le dossier .volunteer si nécessaire
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    def _save_stats(self):
        """Sauvegarde les statistiques dans un fichier JSON"""
        try:
            # Calculer l'uptime
            if self.agent_stats['start_time']:
                start = datetime.fromisoformat(self.agent_stats['start_time'])
                self.agent_stats['uptime_seconds'] = (datetime.now() - start).total_seconds()
            
            # Mettre à jour depuis le client Redis si disponible
            if self.redis_client:
                try:
                    redis_stats = self.redis_client.get_stats()
                    self.agent_stats['connected'] = redis_stats.get('connected', False)
                    self.agent_stats['messages_sent'] = redis_stats.get('messages_sent', 0)
                    self.agent_stats['messages_received'] = redis_stats.get('messages_received', 0)
                    self.agent_stats['reconnections'] = redis_stats.get('reconnections', 0)
                    if redis_stats.get('last_activity'):
                        self.agent_stats['last_sync'] = datetime.fromtimestamp(
                            redis_stats['last_activity']
                        ).isoformat()
                except Exception:
                    pass
            
            # Sauvegarder
            with open(STATS_FILE, 'w') as f:
                json.dump(self.agent_stats, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Erreur sauvegarde stats: {e}")
        
    def start(self):
        """Démarre le daemon"""
        logger.info("=" * 70)
        logger.info("Démarrage du daemon volontaire...")
        logger.info("=" * 70)
        
        self.running = True
        self.agent_stats['status'] = 'starting'
        self.agent_stats['start_time'] = datetime.now().isoformat()
        self._save_stats()
        
        # Enregistrer les gestionnaires de signaux
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Démarrer le thread de sauvegarde des stats IMMÉDIATEMENT (indépendant de Redis)
        self._start_stats_thread()
        
        # Démarrer la collecte de données IMMÉDIATEMENT (indépendant de Redis)
        self._start_data_collection_thread()
        
        try:
            # Initialiser le client Redis avec retries
            logger.info("Initialisation du système de communication Redis...")
            self._connect_with_retry()
            
            # Authentification et enregistrement du volontaire
            if self.redis_client:
                from redis_communication.apps import auth_volunteer_flow
                auth_volunteer_flow()
                logger.info("✅ Volontaire authentifié avec succès auprès du coordinateur")
                
                # Démarrer les threads de communication Redis
                self._start_redis_threads()
                
                self.agent_stats['status'] = 'running'
                self.agent_stats['connected'] = True
            else:
                self.agent_stats['status'] = 'collecting'  # Collecte en cours, pas de Redis
            
            self._save_stats()
            
            logger.info("✅ Daemon volontaire démarré avec succès")
            logger.info("   Le volontaire est maintenant actif et en attente de tâches")
            logger.info("   Ctrl+C pour arrêter")
            
            # Boucle principale
            self._main_loop()
            
        except KeyboardInterrupt:
            logger.info("Interruption clavier détectée")
            self.stop()
        except Exception as e:
            logger.error(f"Erreur fatale dans le daemon: {e}")
            self.agent_stats['status'] = 'error'
            self.agent_stats['last_error'] = str(e)
            self._save_stats()
            import traceback
            logger.error(traceback.format_exc())
            self.stop()
            sys.exit(1)
    
    def _connect_with_retry(self):
        """Tente de se connecter au serveur Redis avec plusieurs tentatives"""
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries and self.running:
            try:
                self.redis_client = RedisClient.get_instance()
                
                if not self.redis_client.running:
                    self.redis_client.start()
                
                # Enregistrer les gestionnaires par défaut
                for channel, handler in DEFAULT_HANDLERS.items():
                    self.redis_client.subscribe(channel, handler)
                
                logger.info("✅ Connexion Redis établie avec succès")
                return True
                
            except Exception as e:
                retry_count += 1
                logger.warning(f"Échec de connexion Redis (tentative {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    logger.info(f"Nouvelle tentative dans {self.connection_retry_delay} secondes...")
                    # Attendre avec vérification de l'état running
                    for _ in range(self.connection_retry_delay):
                        if not self.running:
                            return False
                        time.sleep(1)
        
        logger.error("Impossible de se connecter au serveur Redis après plusieurs tentatives")
        logger.warning("Le daemon continuera à fonctionner et tentera de se reconnecter périodiquement")
        return False
    
    def _start_data_collection_thread(self):
        """Démarre le thread de collecte de données (INDÉPENDANT de Redis)
        
        Utilise les fonctions de l'agent pour collecter les données dans le même format
        (fichiers .json.gz numérotés)
        """
        
        if not AGENT_AVAILABLE:
            logger.error("Module agent non disponible - collecte de données désactivée")
            return
        
        # Initialiser la collecte de données de l'agent
        try:
            initialize_data_collection()
            logger.info(f"Collecte initialisée, dossier: {AGENT_DATA_DIR}")
        except Exception as e:
            logger.error(f"Erreur initialisation collecte: {e}")
            return
        
        def data_collection_loop():
            file_counter = 1
            initial_saved = False
            
            # Trouver le prochain numéro de fichier disponible
            while os.path.exists(f"{AGENT_DATA_DIR}/{file_counter}.json.gz"):
                file_counter += 1
            
            while self.running:
                try:
                    # Premier fichier = données initiales (1.json.gz)
                    if not initial_saved and not os.path.exists(f"{AGENT_DATA_DIR}/1.json.gz"):
                        data = collect_initial_data()
                        filename = f"{AGENT_DATA_DIR}/1.json.gz"
                        initial_saved = True
                        logger.info("Collecte des données initiales")
                    else:
                        # Fichiers suivants = données variables
                        data = collect_variable_data()
                        filename = f"{AGENT_DATA_DIR}/{file_counter}.json.gz"
                        file_counter += 1
                        initial_saved = True
                    
                    if data:
                        # Sauvegarder en format gzip comme l'agent
                        with gzip.open(filename, 'wt', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        
                        # Mettre à jour les statistiques
                        self.agent_stats['files_collected'] += 1
                        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
                        self.agent_stats['data_collected_mb'] += file_size_mb
                        self.agent_stats['last_sync'] = datetime.now().isoformat()
                        
                        # Extraire les infos pour le log
                        cpu_info = data.get('cpu', {})
                        mem_info = data.get('memoire', {}).get('ram', {})
                        cpu_usage = cpu_info.get('global_utilise', 'N/A')
                        ram_usage = mem_info.get('pourcentage_utilise', 'N/A')
                        
                        logger.info(f"Données collectées -> {filename}: CPU={cpu_usage}%, RAM={ram_usage}%")
                        
                        # Si connecté à Redis, envoyer les données
                        if self.redis_client and self.redis_client.connected:
                            try:
                                self.redis_client.publish('volunteer_state', data)
                                self.agent_stats['files_sent'] += 1
                                self.agent_stats['data_sent_mb'] += file_size_mb
                                self.agent_stats['messages_sent'] += 1
                            except Exception as e:
                                logger.warning(f"Impossible d'envoyer via Redis: {e}")
                        
                except Exception as e:
                    logger.error(f"Erreur lors de la collecte de données: {e}")
                    self.agent_stats['last_error'] = str(e)
                
                # Attendre avant la prochaine collecte (2 secondes comme l'agent)
                for _ in range(2):
                    if not self.running:
                        break
                    time.sleep(1)
        
        self.data_collection_thread = threading.Thread(target=data_collection_loop, daemon=True)
        self.data_collection_thread.start()
        logger.info("Thread de collecte de données démarré (utilisant l'agent)")
    
    def _cleanup_old_data_files(self, data_dir, max_files=100):
        """Supprime les anciens fichiers de données pour éviter de remplir le disque"""
        try:
            files = sorted(data_dir.glob('state_*.json'), key=lambda x: x.stat().st_mtime)
            if len(files) > max_files:
                for f in files[:-max_files]:
                    f.unlink()
        except Exception as e:
            logger.warning(f"Erreur nettoyage fichiers: {e}")
    
    def _start_redis_threads(self):
        """Démarre les threads de communication Redis (nécessite une connexion Redis)"""
        from redis_communication.apps import start_communication_threads

        self.task_listener_thread = start_communication_threads()
    
    def _start_stats_thread(self):
        """Démarre le thread de sauvegarde des statistiques (indépendant de Redis)"""
        def stats_save_loop():
            while self.running:
                self._save_stats()
                # Sauvegarder toutes les 5 secondes
                for _ in range(5):
                    if not self.running:
                        break
                    time.sleep(1)
        
        self.stats_thread = threading.Thread(target=stats_save_loop, daemon=True)
        self.stats_thread.start()
        logger.info("Thread de statistiques démarré")
    
    def _main_loop(self):
        """Boucle principale du daemon"""
        logger.info("Entrée dans la boucle principale")
        reconnect_check_interval = 300  # Vérifier la reconnexion toutes les 5 minutes
        last_reconnect_check = time.time()
        
        while self.running:
            try:
                # Attendre avec vérification de l'état
                for _ in range(60):
                    if not self.running:
                        return
                    time.sleep(1)
                
                # Tenter de se reconnecter si pas connecté
                if not self.redis_client and time.time() - last_reconnect_check >= reconnect_check_interval:
                    logger.info("Tentative de reconnexion au serveur Redis...")
                    if self._connect_with_retry():
                        self._start_redis_threads()
                        
                    logger.info("✅ Daemon reconnecté au serveur Redis avec les bons gestionnaires à l'écoute des messages")

                    last_reconnect_check = time.time()
                
                # Afficher les statistiques si connecté
                if self.redis_client:
                    try:
                        stats = self.redis_client.get_stats()
                        logger.info(
                            f"Stats: Connecté={stats['connected']}, "
                            f"Messages envoyés={stats['messages_sent']}, "
                            f"Messages reçus={stats['messages_received']}, "
                            f"Reconnexions={stats['reconnections']}, "
                            f"Uptime={stats['uptime']/3600:.1f}h"
                        )
                    except Exception:
                        logger.warning("Impossible de récupérer les statistiques Redis")
                else:
                    logger.info("En attente de connexion au serveur Redis...")
                
            except Exception as e:
                logger.error(f"Erreur dans la boucle principale: {e}")
                time.sleep(5)
    
    def stop(self):
        """Arrête le daemon"""
        logger.info("Arrêt du daemon volontaire...")
        self.running = False
        
        self.agent_stats['status'] = 'stopped'
        self.agent_stats['connected'] = False
        self._save_stats()
        
        # Attendre que les threads se terminent
        if self.data_collection_thread and self.data_collection_thread.is_alive():
            self.data_collection_thread.join(timeout=5)
        
        if self.task_listener_thread and self.task_listener_thread.is_alive():
            self.task_listener_thread.join(timeout=5)
        
        if self.stats_thread and self.stats_thread.is_alive():
            self.stats_thread.join(timeout=5)
        
        # Arrêter le client Redis
        if self.redis_client:
            self.redis_client.stop()
        
        logger.info("✅ Daemon volontaire arrêté")
    
    def _signal_handler(self, signum, frame):
        """Gestionnaire de signaux système"""
        logger.info(f"Signal {signum} reçu")
        self.stop()
        sys.exit(0)


def main():
    """Point d'entrée principal"""
    daemon = VolunteerDaemon()
    daemon.start()


if __name__ == '__main__':
    main()
