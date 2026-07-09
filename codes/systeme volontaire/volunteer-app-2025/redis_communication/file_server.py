"""
Serveur HTTP simple pour servir les fichiers de sortie des tâches.
"""

import os
import logging
import threading
import json
from http.server import SimpleHTTPRequestHandler
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)



# Dictionnaire pour stocker les serveurs de fichiers par tâche
task_file_servers = {}


# Classe pour le gestionnaire de fichiers spécifique à une tâche
class TaskSpecificFileHandler(SimpleHTTPRequestHandler):
    """
    Gestionnaire HTTP pour servir les fichiers d'une tâche spécifique.
    """
    
    def __init__(self, task_id, directory, *args, **kwargs):
        self.task_id = task_id
        self.directory = directory
        # Définir le répertoire de base avant d'initialiser la classe parente
        # C'est crucial pour que SimpleHTTPRequestHandler serve les fichiers du bon répertoire
        super().__init__(directory=directory, *args, **kwargs)
    
    def do_GET(self):
        """
        Gère les requêtes GET.
        """
        # Analyser l'URL
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        if path == '/' or path == '/index.html' or path == '/files/':
            # Lister les fichiers disponibles
            self._list_files()
        elif path.startswith('/files/'):
            # Téléchargement de fichier
            filename = path[7:]  # Enlever '/files/'
            self._serve_file(filename)
        else:
            # 404 pour tout autre chemin
            self.send_error(404, "Fichier non trouvé")
    
    def _list_files(self):
        """
        Liste les fichiers disponibles pour cette tâche.
        """
        try:
            files = []
            for filename in os.listdir(self.directory):
                file_path = os.path.join(self.directory, filename)
                if os.path.isfile(file_path):
                    files.append({
                        'name': filename,
                        'size': os.path.getsize(file_path),
                        'url': f'/files/{filename}'
                    })
            
            # Créer une reponse json pour lister les fichiers
            self._send_json_response(files)
            
        except Exception as e:
            logger.error(f"Erreur lors de la liste des fichiers: {e}")
            self.send_error(500, "Erreur interne du serveur")
    
    def _serve_file(self, filename):
        """
        Sert un fichier spécifique.
        
        Args:
            filename: Nom du fichier à servir
        """
        file_path = os.path.join(self.directory, filename)
        
        if not os.path.isfile(file_path):
            self.send_error(404, "Fichier non trouvé")
            return
        
        try:
            with open(file_path, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(os.path.getsize(file_path)))
                self.end_headers()
                self.wfile.write(f.read())
        except Exception as e:
            logger.error(f"Erreur lors du téléchargement du fichier {file_path}: {e}")
            self.send_error(500, "Erreur lors du téléchargement")
    
    def _format_size(self, size_bytes):
        """
        Formate la taille en bytes en une chaîne lisible.
        
        Args:
            size_bytes: Taille en bytes
            
        Returns:
            str: Taille formatée
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"


    def _send_json_response(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(json.dumps(data))))
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    
    def log_message(self, format, *args):
        """
        Redirige les logs vers le logger Django.
        """
        logger.debug(f"TaskFileServer[{self.task_id}]: {format % args}")

# Classe pour le serveur de fichiers spécifique à une tâche
class TaskFileServer:
    """
    Serveur de fichiers pour une tâche spécifique.
    """
    
    def __init__(self, task_id, directory):
        """
        Initialise le serveur de fichiers pour une tâche spécifique.
        
        Args:
            task_id: ID de la tâche
            directory: Répertoire contenant les fichiers de la tâche
        """
        self.task_id = task_id
        self.directory = directory
        self.server = None
        self.server_thread = None
        self.running = False
        self.port = None
    
    def start(self, port=None):
        """
        Démarre le serveur de fichiers.
        
        Args:
            port: Port sur lequel démarrer le serveur (optionnel)
            
        Returns:
            int: Port sur lequel le serveur a été démarré
        """
        if self.running:
            logger.warning(f"Le serveur de fichiers pour la tâche {self.task_id} est déjà en cours d'exécution")
            return self.port
        
        # Créer le répertoire s'il n'existe pas
        os.makedirs(self.directory, exist_ok=True)
        
        # Trouver un port disponible si non spécifié
        if port is None:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', 0))
            port = s.getsockname()[1]
            s.close()
        
        self.port = port
        
        # Créer une classe de gestionnaire avec le répertoire spécifié
        # Utiliser une fonction pour créer le gestionnaire avec le répertoire correct
        def handler_factory(*args, **kwargs):
            return TaskSpecificFileHandler(self.task_id, self.directory, *args, **kwargs)
        handler = handler_factory
        
        # Démarrer le serveur dans un thread séparé
        def run_server():
            self.running = True
            try:
                import socketserver
                self.server = socketserver.ThreadingTCPServer(('0.0.0.0', self.port), handler)
                self.server.allow_reuse_address = True
                logger.info(f"Serveur de fichiers pour la tâche {self.task_id} en écoute sur http://localhost:{self.port} pour le dossier {self.directory}")
                self.server.serve_forever()
            except Exception as e:
                logger.error(f"Erreur lors du démarrage du serveur de fichiers pour la tâche {self.task_id}: {e}")
                self.running = False
        
        self.server_thread = threading.Thread(target=run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        logger.info(f"Serveur de fichiers pour la tâche {self.task_id} démarré sur le port {self.port}")
        return self.port
    
    def stop(self):
        """
        Arrête le serveur de fichiers.
        """
        if not self.running:
            logger.warning(f"Le serveur de fichiers pour la tâche {self.task_id} n'est pas en cours d'exécution")
            return
        
        self.running = False
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        
        logger.info(f"Serveur de fichiers pour la tâche {self.task_id} arrêté")

# Fonction pour démarrer un serveur de fichiers pour une tâche spécifique
def start_task_file_server(task_id, directory, port=None):
    """
    Démarre un serveur de fichiers pour une tâche spécifique.
    
    Args:
        task_id: ID de la tâche
        directory: Répertoire contenant les fichiers de la tâche
        port: Port sur lequel démarrer le serveur (optionnel)
        
    Returns:
        int: Port sur lequel le serveur a été démarré
    """
    # Arrêter le serveur existant si nécessaire
    if task_id in task_file_servers:
        task_file_servers[task_id].stop()
    
    # Créer et démarrer un nouveau serveur
    server = TaskFileServer(task_id, directory)
    port = server.start(port)
    
    # Stocker le serveur pour pouvoir l'arrêter plus tard
    task_file_servers[task_id] = server
    
    return port

# Fonction pour arrêter un serveur de fichiers pour une tâche spécifique
def stop_task_file_server(task_id):
    """
    Arrête un serveur de fichiers pour une tâche spécifique.
    
    Args:
        task_id: ID de la tâche
    """
    if task_id in task_file_servers:
        task_file_servers[task_id].stop()
        del task_file_servers[task_id]
        logger.info(f"Serveur de fichiers pour la tâche {task_id} supprimé")
    else:
        logger.warning(f"Aucun serveur de fichiers trouvé pour la tâche {task_id}")

