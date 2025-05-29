APPLICATION VOLONTAIRE POUR L'EXECUTION DES CALCULS DISTRIBUES

DESCRIPTION DU PROJET
Cette application permet aux volontaires d'utiliser leurs ressources informatiques inutilisées pour effectuer des calculs demandés par des gestionnaires de workflow. 
Elle offre une solution flexible et peu coûteuse pour le calcul distribué, particulièrement adaptée aux environnements à ressources limitées.

OBJECTIFS
Objectif principal : Développer un système permettant aux volontaires de partager leurs ressources informatiques pour l'exécution de tâches de calcul
Problématique : Pallier les difficultés d'accès aux supercalculateurs et infrastructures HPC dans les environnements contraints (réseau instable, alimentation irrégulière)
Solution : Système de calcul distribué basé sur des machines volontaires non dédiées.

FONCTIONNALITES

  INSCRIPTION DES VOLONTAIRES
 1) Enregistrement des capacités machine (CPU, RAM, stockage)
   la machine volontaire entre ses caracteristiques 
 2) Configuration des préférences d'exécution
   La machine volontaire decide elle-meme de la quantite de ressources dans sa machine et ceci a des heures et jours qui lui conviennent
 4) Gestion du profil utilisateur

    SUIVI DE LA DISPONIBILITE
    
    Pendant que le volontaire execute un calcul, il est monotorise en temps reel, c'est-a-dire que le systeme Surveiller si la machine est allumée et disponible mesure l'utilisation du CPU, de la RAM, du disque,
    détecte les pannes ou ralentissements,suit les performances des tâches en cours. La communication automatique avec le coordinateur et la mise a jour dynamique du statut des volontaires et des taches

    GESTION DES TACHES
    Réception automatique des tâches de calcul via un canal pub/sub (Redis)
    Exécution, suspension, reprise et annulation des tâches( le coordinateur est au courant en temps reel de l'avancement de l'execution de la tache
    Envoi sécurisé des résultats

    INTERFACE GRAPHIQUE
    Tableau de bord pour le suivi des tâches(Le volontaire peut voir ses taches en cours, celles deja traitees et celle en attente ou suspendues)
    Visualisation des performances( Ici le volontaire peut voir ses performances concernant le traitement des taches)
    Configuration des préférences( Ici le volontaire peut modifier a volonte ses preferences concernant l'utilisation de sa machine)

    GESTION DES FICHIERS
    Il s'agit ici des fichiers necessaires ( fichiers d'entree et de sortie) pour le traitement de la tache. Quand le volontaire recoit une tache( nous la mettons dans une image docker qui contient tout le necessaire pour traiter la tache)
   Une fois la tache terminee, le systeme nettoie automatiquemnt les fichiers utilises afin de ne pas surcharger le stockage local du volontaire.

 COMMENT LANCER LE PROJET?

 PREREQUIS
 Avoir dans sa machine installes les technologies suivantes
  * Redis pour la communication pub/sub
  * Docker pour la conteneurisation des taches
  * Python( Django )

    INSTALLATION
     git clone 
