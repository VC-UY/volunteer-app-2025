"""
Serveur HTTP simple pour servir les fichiers de sortie des tâches.
"""

import os
import logging
import threading
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import socketserver

from django.conf import settings

logger = logging.getLogger(__name__)

# Répertoire pour stocker les fichiers des tâches
TASKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'tasks')

class TaskFileHandler(SimpleHTTPRequestHandler):
    """
    Gestionnaire HTTP pour servir les fichiers de tâches.
    """
    
    def __init__(self, *args, **kwargs):
        self.directory = TASKS_DIR
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """
        Gère les requêtes GET.
        """
        # Analyser l'URL
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        
        # Vérifier le chemin
        if path.startswith('/api/tasks'):
            # API pour lister les tâches ou les fichiers
            self._handle_api_request(path, query)
        elif path.startswith('/download'):
            # Téléchargement de fichier
            self._handle_download_request(path, query)
        else:
            # Page d'accueil ou 404
            if path == '/' or path == '/index.html':
                self._serve_index_page()
            else:
                self.send_error(404, "Fichier non trouvé")
    
    def _handle_api_request(self, path, query):
        """
        Gère les requêtes API.
        
        Args:
            path: Chemin de l'URL
            query: Paramètres de requête
        """
        if path == '/api/tasks':
            # Lister toutes les tâches
            self._list_tasks()
        elif path.startswith('/api/tasks/'):
            # Lister les fichiers d'une tâche spécifique
            task_id = path.split('/')[3]
            self._list_task_files(task_id)
        else:
            self.send_error(404, "API non trouvée")
    
    def _handle_download_request(self, path, query):
        """
        Gère les requêtes de téléchargement.
        
        Args:
            path: Chemin de l'URL
            query: Paramètres de requête
        """
        # Format: /download/task_id/type/filename
        parts = path.split('/')
        if len(parts) < 5:
            self.send_error(400, "URL de téléchargement invalide")
            return
        
        task_id = parts[2]
        file_type = parts[3]  # 'input' ou 'output'
        filename = '/'.join(parts[4:])  # Au cas où le nom de fichier contient des '/'
        
        # Construire le chemin du fichier
        if file_type not in ['input', 'output']:
            self.send_error(400, "Type de fichier invalide")
            return
        
        file_path = os.path.join(TASKS_DIR, task_id, file_type, filename)
        
        # Vérifier si le fichier existe
        if not os.path.isfile(file_path):
            self.send_error(404, "Fichier non trouvé")
            return
        
        # Servir le fichier
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
    
    def _list_tasks(self):
        """
        Liste toutes les tâches disponibles.
        """
        try:
            # Lister les répertoires de tâches
            tasks = []
            for task_id in os.listdir(TASKS_DIR):
                task_dir = os.path.join(TASKS_DIR, task_id)
                if os.path.isdir(task_dir):
                    # Vérifier s'il y a un fichier de métadonnées
                    meta_file = os.path.join(task_dir, 'meta.json')
                    task_info = {
                        'id': task_id,
                        'has_input': os.path.isdir(os.path.join(task_dir, 'input')),
                        'has_output': os.path.isdir(os.path.join(task_dir, 'output'))
                    }
                    
                    if os.path.isfile(meta_file):
                        try:
                            with open(meta_file, 'r') as f:
                                meta = json.load(f)
                                task_info.update(meta)
                        except:
                            pass
                    
                    tasks.append(task_info)
            
            # Envoyer la réponse
            self._send_json_response(tasks)
        
        except Exception as e:
            logger.error(f"Erreur lors de la liste des tâches: {e}")
            self.send_error(500, "Erreur lors de la liste des tâches")
    
    def _list_task_files(self, task_id):
        """
        Liste les fichiers d'une tâche spécifique.
        
        Args:
            task_id: ID de la tâche
        """
        try:
            task_dir = os.path.join(TASKS_DIR, task_id)
            if not os.path.isdir(task_dir):
                self.send_error(404, "Tâche non trouvée")
                return
            
            # Collecter les informations sur les fichiers
            files = {
                'input': [],
                'output': []
            }
            
            # Fichiers d'entrée
            input_dir = os.path.join(task_dir, 'input')
            if os.path.isdir(input_dir):
                for filename in os.listdir(input_dir):
                    file_path = os.path.join(input_dir, filename)
                    if os.path.isfile(file_path):
                        files['input'].append({
                            'name': filename,
                            'size': os.path.getsize(file_path),
                            'url': f'/download/{task_id}/input/{filename}'
                        })
            
            # Fichiers de sortie
            output_dir = os.path.join(task_dir, 'output')
            if os.path.isdir(output_dir):
                for filename in os.listdir(output_dir):
                    file_path = os.path.join(output_dir, filename)
                    if os.path.isfile(file_path):
                        files['output'].append({
                            'name': filename,
                            'size': os.path.getsize(file_path),
                            'url': f'/download/{task_id}/output/{filename}'
                        })
            
            # Envoyer la réponse
            self._send_json_response(files)
        
        except Exception as e:
            logger.error(f"Erreur lors de la liste des fichiers de la tâche {task_id}: {e}")
            self.send_error(500, "Erreur lors de la liste des fichiers")
    
    def _serve_index_page(self):
        """
        Sert la page d'accueil.
        """
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Serveur de fichiers de tâches</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                h1 { color: #333; }
                .task-list { margin-top: 20px; }
                .task-item { border: 1px solid #ddd; padding: 10px; margin-bottom: 10px; border-radius: 5px; }
                .task-item h3 { margin-top: 0; }
                .file-list { margin-top: 10px; }
                .file-item { padding: 5px; }
                .hidden { display: none; }
                button { padding: 5px 10px; background-color: #4CAF50; color: white; border: none; border-radius: 3px; cursor: pointer; }
                button:hover { background-color: #45a049; }
            </style>
        </head>
        <body>
            <h1>Serveur de fichiers de tâches</h1>
            <p>Ce serveur permet de télécharger les fichiers d'entrée et de sortie des tâches.</p>
            
            <div class="task-list" id="taskList">
                <p>Chargement des tâches...</p>
            </div>
            
            <script>
                // Charger la liste des tâches
                fetch('/api/tasks')
                    .then(response => response.json())
                    .then(tasks => {
                        const taskList = document.getElementById('taskList');
                        taskList.innerHTML = '';
                        
                        if (tasks.length === 0) {
                            taskList.innerHTML = '<p>Aucune tâche disponible.</p>';
                            return;
                        }
                        
                        tasks.forEach(task => {
                            const taskItem = document.createElement('div');
                            taskItem.className = 'task-item';
                            
                            const taskName = task.name || `Tâche ${task.id}`;
                            
                            taskItem.innerHTML = `
                                <h3>${taskName}</h3>
                                <p>ID: ${task.id}</p>
                                ${task.description ? `<p>${task.description}</p>` : ''}
                                <button onclick="loadTaskFiles('${task.id}')">Voir les fichiers</button>
                                <div id="files-${task.id}" class="file-list hidden"></div>
                            `;
                            
                            taskList.appendChild(taskItem);
                        });
                    })
                    .catch(error => {
                        console.error('Erreur lors du chargement des tâches:', error);
                        document.getElementById('taskList').innerHTML = '<p>Erreur lors du chargement des tâches.</p>';
                    });
                
                // Charger les fichiers d'une tâche
                function loadTaskFiles(taskId) {
                    const filesDiv = document.getElementById(`files-${taskId}`);
                    
                    if (!filesDiv.classList.contains('hidden')) {
                        filesDiv.classList.add('hidden');
                        return;
                    }
                    
                    filesDiv.innerHTML = '<p>Chargement des fichiers...</p>';
                    filesDiv.classList.remove('hidden');
                    
                    fetch(`/api/tasks/${taskId}`)
                        .then(response => response.json())
                        .then(files => {
                            filesDiv.innerHTML = '';
                            
                            // Fichiers d'entrée
                            if (files.input.length > 0) {
                                filesDiv.innerHTML += '<h4>Fichiers d\'entrée</h4>';
                                const inputList = document.createElement('ul');
                                
                                files.input.forEach(file => {
                                    const fileItem = document.createElement('li');
                                    fileItem.className = 'file-item';
                                    fileItem.innerHTML = `
                                        <a href="${file.url}" download>${file.name}</a> (${formatFileSize(file.size)})
                                    `;
                                    inputList.appendChild(fileItem);
                                });
                                
                                filesDiv.appendChild(inputList);
                            }
                            
                            // Fichiers de sortie
                            if (files.output.length > 0) {
                                filesDiv.innerHTML += '<h4>Fichiers de sortie</h4>';
                                const outputList = document.createElement('ul');
                                
                                files.output.forEach(file => {
                                    const fileItem = document.createElement('li');
                                    fileItem.className = 'file-item';
                                    fileItem.innerHTML = `
                                        <a href="${file.url}" download>${file.name}</a> (${formatFileSize(file.size)})
                                    `;
                                    outputList.appendChild(fileItem);
                                });
                                
                                filesDiv.appendChild(outputList);
                            }
                            
                            if (files.input.length === 0 && files.output.length === 0) {
                                filesDiv.innerHTML = '<p>Aucun fichier disponible pour cette tâche.</p>';
                            }
                        })
                        .catch(error => {
                            console.error(`Erreur lors du chargement des fichiers de la tâche ${taskId}:`, error);
                            filesDiv.innerHTML = '<p>Erreur lors du chargement des fichiers.</p>';
                        });
                }
                
                // Formater la taille du fichier
                function formatFileSize(size) {
                    if (size < 1024) {
                        return `${size} octets`;
                    } else if (size < 1024 * 1024) {
                        return `${(size / 1024).toFixed(2)} Ko`;
                    } else if (size < 1024 * 1024 * 1024) {
                        return `${(size / (1024 * 1024)).toFixed(2)} Mo`;
                    } else {
                        return `${(size / (1024 * 1024 * 1024)).toFixed(2)} Go`;
                    }
                }
            </script>
        </body>
        </html>
        """
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(html.encode())))
        self.end_headers()
        self.wfile.write(html.encode())
    
    def _send_json_response(self, data):
        """
        Envoie une réponse JSON.
        
        Args:
            data: Données à envoyer
        """
        json_data = json.dumps(data).encode()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(json_data)))
        self.end_headers()
        self.wfile.write(json_data)
    
    def log_message(self, format, *args):
        """
        Redirige les logs vers le logger Django.
        """
        logger.debug(f"FileServer: {format % args}")

class FileServer:
    """
    Serveur de fichiers pour les tâches.
    """
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """
        Récupère l'instance unique du serveur de fichiers.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    def __init__(self):
        """
        Initialise le serveur de fichiers.
        """
        self.server = None
        self.server_thread = None
        self.running = False
        self.port = 8080  # Port par défaut
    
    def start(self, port=None):
        """
        Démarre le serveur de fichiers.
        
        Args:
            port: Port sur lequel démarrer le serveur (optionnel)
        """
        if self.running:
            logger.warning("Le serveur de fichiers est déjà en cours d'exécution")
            return
        
        if port is not None:
            self.port = port
        
        # Créer le répertoire des tâches s'il n'existe pas
        os.makedirs(TASKS_DIR, exist_ok=True)
        
        # Démarrer le serveur dans un thread séparé
        self.server_thread = threading.Thread(target=self._run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        logger.info(f"Serveur de fichiers démarré sur le port {self.port}")
        return self.port
    
    def stop(self):
        """
        Arrête le serveur de fichiers.
        """
        if not self.running:
            logger.warning("Le serveur de fichiers n'est pas en cours d'exécution")
            return
        
        self.running = False
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        
        logger.info("Serveur de fichiers arrêté")
    
    def _run_server(self):
        """
        Exécute le serveur HTTP.
        """
        self.running = True
        
        # Créer le serveur
        try:
            self.server = socketserver.ThreadingTCPServer(('0.0.0.0', self.port), TaskFileHandler)
            self.server.allow_reuse_address = True
            
            # Servir jusqu'à ce que le serveur soit arrêté
            logger.info(f"Serveur de fichiers en écoute sur http://localhost:{self.port}")
            self.server.serve_forever()
        
        except Exception as e:
            logger.error(f"Erreur lors du démarrage du serveur de fichiers: {e}")
            self.running = False

# Fonction pour démarrer le serveur de fichiers
def start_file_server(port=None):
    """
    Démarre le serveur de fichiers.
    
    Args:
        port: Port sur lequel démarrer le serveur (optionnel)
        
    Returns:
        int: Port sur lequel le serveur a été démarré
    """
    server = FileServer.get_instance()
    return server.start(port)

# Fonction pour arrêter le serveur de fichiers
def stop_file_server():
    """
    Arrête le serveur de fichiers.
    """
    server = FileServer.get_instance()
    server.stop()
