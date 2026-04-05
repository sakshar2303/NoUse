"""
b76.metacognition.snapshot — Forsknings-snapshots
===================================================
Tar kompletta frysta kopior ("snapshots") av hela AI-systemets tillstånd:
 - Grafdatabasen (KuzuDB miljön)
 - Limbiska värden (Dopamin, λ, Arousal)
 - Domän-betti (TDA H0/H1 värden)

Denna modul används för att kunna "spola tillbaka" hjärnan för forskning,
eller för att jämföra systemets kreativitet över tid (före/efter en bisociation).
"""
import os
import json
import shutil
from datetime import datetime
from pathlib import Path
import logging

from nouse.field.surface import FieldSurface
from nouse.limbic.signals import load_state
from nouse.daemon.lock import BrainLock

log = logging.getLogger("nouse.snapshot")

SNAPSHOT_DIR = Path.home() / ".local" / "share" / "nouse" / "snapshots"

def create_snapshot(field: FieldSurface, tag: str = "auto") -> str:
    """
    Skapar ett fryst snapshot av hjärnans nuvarande konfiguration.
    Tar cirka 1 sekund. MÅSTE använda BrainLock runtom.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_name = f"snapshot_{timestamp}_{tag}"
    target_dir = SNAPSHOT_DIR / snapshot_name
    
    target_dir.mkdir(parents=True, exist_ok=True)
    
    log.info(f"Metacognition: Påbörjar snapshot '{snapshot_name}' för forskningsanalys.")
    
    with BrainLock(timeout=10.0):
        # 1. SQLite Backup — kopiera databasfilen
        sqlite_path = Path.home() / ".local" / "share" / "nouse" / "field.sqlite"
        if sqlite_path.exists():
            db_target = target_dir / "field.sqlite"
            shutil.copy2(sqlite_path, db_target)
            
        # 2. Limbic State
        limbic = load_state()
        
        # 3. Extrahera TDA Betti Numbers per domän
        domains = field.domains()
        topo_profiles = {}
        for d in domains:
            try:
                topo_profiles[d] = field.domain_tda_profile(d)
            except Exception:
                pass
                
        # 4. Generell graf-statistik
        stats = field.stats()
        
        # Spara all metadata
        meta = {
            "timestamp": datetime.now().isoformat(),
            "tag": tag,
            "architecture_phase": "5_Autonomy",
            "stats": stats,
            "limbic": {
                "dopamine": limbic.dopamine,
                "noradrenaline": limbic.noradrenaline,
                "acetylcholine": limbic.acetylcholine,
                "lam": limbic.lam,
                "arousal": limbic.arousal,
                "pruning_aggression": limbic.pruning_aggression,
                "cycle": limbic.cycle,
            },
            "topological_profiles": topo_profiles
        }
        
        (target_dir / "meta.json").write_text(json.dumps(meta, indent=2))
        
    log.info(f"Snapshot '{snapshot_name}' färdigställt: sparat till {target_dir}")
    return str(target_dir)
