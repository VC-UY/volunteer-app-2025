import time
import sys
import uuid
import heartbeat, collector, syncer, persistence
from predictor import HybridRuntimePredictor
import logging
import os
import json
import argparse
import random

# Configure logging to file for background execution
LOG_FILE = "agent_system.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=LOG_FILE,
    filemode='a'
)
logger = logging.getLogger("VC-Agent")

def print_welcome_message():
    """Display a professional terminal message to the user."""
    message = r"""
    ############################################################
    #                                                          #
    #   VC-UY1 : VOLUNTEER COMPUTING RESEARCH AGENT            #
    #                                                          #
    #   Installation terminée avec succès !                     #
    #                                                          #
    #   Tout se passera bien sans déranger votre machine.      #
    #   Nous allons juste collecter des données sur la charge  #
    #   de votre CPU et mémoire.                               #
    #                                                          #
    #   Merci de participer à l'évolution de la tech           #
    #   en Afrique par la recherche scientifique.              #
    #                                                          #
    ############################################################
    """
    print(message)
    print("\nL'agent fonctionne maintenant en arrière-plan. Vous pouvez fermer ce terminal.\n")

def get_consent():
    """Silently write/return default research consent level (level 3)."""
    consent_file = "consent.json"
    level = 3
    if os.path.exists(consent_file):
        try:
            with open(consent_file, "r") as f:
                return json.load(f).get("consent_level", 3)
        except:
            pass
    try:
        with open(consent_file, "w") as f:
            json.dump({"consent_level": level, "accepted_at": time.time()}, f)
    except Exception as e:
        logger.error(f"Failed to write consent: {e}")
    return level

def set_preferences():
    """Prompt for user availability preferences in a simple, descriptive way."""
    pref_file = "preferences.json"
    if os.path.exists(pref_file) and "--setup" not in sys.argv:
        return
    # Mode démon / systemd : pas de TTY → defaults silencieux
    if not sys.stdin.isatty() and "--setup" not in sys.argv:
        prefs = {
            "allowed_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
            "allowed_slots": ["00:00-23:59"],
            "mode": "total",
        }
        try:
            with open(pref_file, "w") as f:
                json.dump(prefs, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to write default preferences: {e}")
        return

    print("\n" + "="*60)
    print("   PREFERENCES DE DISPONIBILITE DU VOLONTAIRE")
    print("="*60)
    print("A quel moment souhaitez-vous que votre machine soit utilisee ?")
    print("1. Tout le temps (24h/24, 7j/7) [Recommande]")
    print("2. Seulement la nuit (22h00 - 06h00)")
    print("3. Seulement le matin (06h00 - 12h00)")
    print("4. Seulement l'apres-midi (12h00 - 18h00)")
    print("5. Le soir (18h00 - 22h00)")
    print("="*60)
    
    moment = "1"
    try:
        ans = input("Entrez votre choix (1-5) [Par defaut: 1] : ").strip()
        if ans in ["1", "2", "3", "4", "5"]:
            moment = ans
    except (EOFError, KeyboardInterrupt):
        pass

    # Map moment to allowed_slots
    slots = ["00:00-23:59"]
    if moment == "2":
        slots = ["22:00-06:00"]
    elif moment == "3":
        slots = ["06:00-12:00"]
    elif moment == "4":
        slots = ["12:00-18:00"]
    elif moment == "5":
        slots = ["18:00-22:00"]

    print("\n" + "="*60)
    print("Quels jours de la semaine autorisez-vous ?")
    print("1. Tous les jours (Lundi a Dimanche) [Recommande]")
    print("2. En semaine uniquement (Lundi a Vendredi)")
    print("3. Le week-end uniquement (Samedi et Dimanche)")
    print("="*60)
    
    days_choice = "1"
    try:
        ans = input("Entrez votre choix (1-3) [Par defaut: 1] : ").strip()
        if ans in ["1", "2", "3"]:
            days_choice = ans
    except (EOFError, KeyboardInterrupt):
        pass

    # Map days_choice to allowed_days
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    if days_choice == "2":
        days = ["mon", "tue", "wed", "thu", "fri"]
    elif days_choice == "3":
        days = ["sat", "sun"]

    print("\n" + "="*60)
    print("Quel type de contribution preferez-vous ?")
    print("1. Contribution Totale (100% de la ressource libre utilisee)")
    print("2. Contribution Partielle (Limiter la charge CPU pour ne pas ralentir)")
    print("="*60)
    
    contrib_choice = "1"
    try:
        ans = input("Entrez votre choix (1-2) [Par defaut: 1] : ").strip()
        if ans in ["1", "2"]:
            contrib_choice = ans
    except (EOFError, KeyboardInterrupt):
        pass

    mode = "total" if contrib_choice == "1" else "partial"

    prefs = {
        "allowed_days": days,
        "allowed_slots": slots,
        "mode": mode
    }
    
    try:
        with open(pref_file, "w") as f:
            json.dump(prefs, f, indent=4)
        print("\n-> Vos preferences de calcul ont ete enregistrees avec succes !")
    except Exception as e:
        logger.error(f"Failed to write preferences: {e}")


def daemonize():
    """Fork the process into the background (Linux/Posix only)."""
    if os.name != 'posix':
        return # Windows uses Registry/Startup for backgrounding (non-blocking)
    
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        logger.error(f"Fork #1 failed: {e}")
        sys.exit(1)

    os.setsid()
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        logger.error(f"Fork #2 failed: {e}")
        sys.exit(1)
    
    # Detach standard file descriptors for full daemonization
    sys.stdout.flush()
    sys.stderr.flush()
    with open('/dev/null', 'rb') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'ab') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
    with open('/dev/null', 'ab') as f:
        os.dup2(f.fileno(), sys.stderr.fileno())

def main():
    # 0. Check if --setup mode is requested
    if "--setup" in sys.argv:
        print_welcome_message()
        get_consent()
        set_preferences()
        print("\nConfiguration terminée avec succès. L'agent démarrera automatiquement en arrière-plan.")
        sys.exit(0)

    # 1. Interactive setup before backgrounding
    consent_level = get_consent()
    set_preferences()
    
    # 2. Backgrounding
    if "--foreground" not in sys.argv:
        daemonize()


    logger.info("Starting VC-Agent Daemon...")
    
    # 3. Ensure persistence (Auto-start)
    persistence.ensure_persistence()
    
    # 4. Startup check for power cut
    machine_id = collector.get_mac_address()
    status = heartbeat.detect_power_cut()
    if status and status['type'] == 'power_cut':
        logger.warning(f"Power cut detected! Downtime: {status['gap_s']}s")
        syncer.report_power_event(machine_id, "power_cut", status['gap_s'])
    
    # 5. Register and verify consent
    session_id = str(uuid.uuid4())
    syncer.register(machine_id, consent_level=consent_level)
    syncer.start_session(machine_id, session_id)
    
    # Modele final obligatoire : hybride ARX 15D + GRU
    predictor = HybridRuntimePredictor()
    logger.info(
        "Hybride pret — ARX=%s GRU=%s",
        predictor.rls.weights_path,
        predictor.gru_path,
    )

    # API locale : le volontaire / coordinateur consulte /predict (horizon 15 min)
    try:
        from availability_api import start_availability_api

        start_availability_api(predictor)
    except Exception as exc:
        logger.error("Availability API non démarrée: %s", exc)
    
    # NEW: Immediate Startup Pulse (for instant visibility)
    logger.info("Sending initial startup pulse...")
    initial_stats = collector.get_stats(aggregate=False)
    
    # Predict initial step
    pred_init = predictor.predict_from_snapshot(initial_stats)
    initial_stats["predicted_availability"] = pred_init["hybrid"]
    initial_stats["prediction_detail"] = pred_init
    
    syncer.sync_batch(machine_id, session_id, [initial_stats])
    
    # 5. Main collection loop (Privacy-Aware)
    # Intervalle sync configurable (défaut 20s) — assez fréquent pour la page /donnees
    sync_every = max(5, int(os.environ.get("VC_AGENT_SYNC_SECONDS", "20")))
    last_power_status = None
    try:
        while True:
            stats = collector.get_stats(aggregate=True)

            current_power_status = stats['power_plugged']
            if last_power_status is not None and current_power_status != last_power_status:
                event_type = "to_ac" if current_power_status else "to_battery"
                logger.info(f"Power transition: {event_type}")
                syncer.report_power_event(machine_id, event_type, 0)
            last_power_status = current_power_status

            heartbeat.write_heartbeat()

            if syncer.check_connectivity():
                final_stats = collector.get_stats(aggregate=False)

                y_current = 1.0 if final_stats.get("is_available", False) else 0.0
                pred = predictor.predict_from_snapshot(final_stats)
                final_stats["predicted_availability"] = pred["hybrid"]
                final_stats["prediction_detail"] = pred
                predictor.observe(final_stats, y_current)

                # Mettre à jour le cache HTTP /predict
                try:
                    from availability_api import bind_predictor, last_prediction
                    bind_predictor(predictor)
                except Exception:
                    pass

                ok = syncer.sync_batch(machine_id, session_id, [final_stats])
                collector.clear_aggregation_buffers()
                logger.info(
                    "Snapshot sync=%s hybrid=%.3f launch=%s (every %ss)",
                    ok,
                    float(pred.get("hybrid") or 0),
                    pred.get("launch"),
                    sync_every,
                )

            time.sleep(sync_every)
    except KeyboardInterrupt:
        logger.info("Shutting down cleanly...")
        heartbeat.write_heartbeat(shutdown_clean=True)

if __name__ == "__main__":
    main()
