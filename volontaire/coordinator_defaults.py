"""
Configuration réseau VC-UY — une seule adresse pour tous les volontaires.

Port 6380 = proxy Redis public (connexion volontaire → coordinateur).
Port 6379 = Redis interne au serveur (Docker uniquement, jamais pour les volontaires).
"""

COORDINATOR_HOST = "173.249.38.251"
COORDINATOR_PROXY_PORT = 6380
MANAGER_PUBLIC_URL = "https://manager-vc-uy.npe-techs.com"
VOLUNTEER_API_PORT = 8003
