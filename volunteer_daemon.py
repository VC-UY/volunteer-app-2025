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
from pathlib import Path

# Ajouter le chemin du projet
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django
django.setup()

from redis_communication.resilient_client import ResilientRedisClient
from redis_communication.apps import RedisCommunicationConfig

# Configuration du logging
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'volunteer_daemon.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('VolunteerDaemon')

class VolunteerDaemon:
    """Daemon principal du volontaire"""
    
    def __init__(self):
        self.running = False
        self.redis_config = None
        
    def start(self):
        """Démarre le daemon"""
        logger.info("=" * 70)
        logger.info("Démarrage du daemon volontaire...")
        logger.info("=" * 70)
        
        self.running = True
        
        # Enregistrer les gestionnaires de signaux
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        try:
            # Initialiser le système de communication Redis
            logger.info("Initialisation du système de communication Redis...")
            self.redis_config = RedisCommunicationConfig('redis_communication', None)
            self.redis_config.ready()
            
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
            import traceback
            logger.error(traceback.format_exc())
            self.stop()
            sys.exit(1)
    
    def _main_loop(self):
        """Boucle principale du daemon"""
        logger.info("Entrée dans la boucle principale")
        
        while self.running:
            try:
                # Afficher les statistiques toutes les 60 secondes
                time.sleep(60)
                
                if ResilientRedisClient._instance:
                    stats = ResilientRedisClient._instance.get_stats()
                    logger.info(
                        f"Stats: Connecté={stats['connected']}, "
                        f"Messages envoyés={stats['messages_sent']}, "
                        f"Messages reçus={stats['messages_received']}, "
                        f"Reconnexions={stats['reconnections']}, "
                        f"Uptime={stats['uptime']/3600:.1f}h"
                    )
                
            except Exception as e:
                logger.error(f"Erreur dans la boucle principale: {e}")
                time.sleep(5)
    
    def stop(self):
        """Arrête le daemon"""
        logger.info("Arrêt du daemon volontaire...")
        self.running = False
        
        # Arrêter le client Redis
        if ResilientRedisClient._instance:
            ResilientRedisClient._instance.stop()
        
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
