from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_DIR = ROOT / "protocol"
CONFIG_PATH = PROTOCOL_DIR / "protocol_config.yaml"
PROTOCOL_DOC = PROTOCOL_DIR / "PROTOCOL.md"
CODING_RUBRIC = PROTOCOL_DIR / "coding_rubric.md"
DATA_DIR = ROOT / "data"
CORPUS_PATH = DATA_DIR / "corpus.csv"
S2_EVIDENCE_PATH = DATA_DIR / "build_declaration_evidence.csv"
S5_JUDGMENTS_PATH = DATA_DIR / "s5_judgments.csv"
OUT_DIR = ROOT / "out"
PREREGISTRATION_JSON = OUT_DIR / "preregistration.json"
PANEL_DRAW_CSV = OUT_DIR / "panel_draw.csv"
CANDIDATE_RANKING_CSV = OUT_DIR / "candidate_ranking.csv"
SCREENING_LOG_CSV = OUT_DIR / "screening_log.csv"
PENDING_S5_CSV = OUT_DIR / "pending_s5.csv"
FREEZE_MANIFEST_JSON = OUT_DIR / "freeze_manifest.json"
DEPOSIT_ARCHIVE = OUT_DIR / "deposit_bundle.tar.gz"
