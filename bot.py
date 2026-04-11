import os
import time
from chess_board import ChessBoard
from opening_book import choose_book_move, book_move_bonus

try:
    import torch
except Exception:
    torch = None

from dataclasses import dataclass, asdict

@dataclass
class SearchStats:
    nodes: int = 0
    qnodes: int = 0
    leaf_evals: int = 0
    terminal_hits: int = 0
    cutoffs: int = 0

    move_order_calls: int = 0
    move_order_time: float = 0.0

    evaluate_calls: int = 0
    evaluate_time: float = 0.0

    quiescence_calls: int = 0
    quiescence_time: float = 0.0

    refresh_calls: int = 0
    refresh_time: float = 0.0

    snapshot_calls: int = 0
    snapshot_time: float = 0.0

    restore_calls: int = 0
    restore_time: float = 0.0

    root_candidates: int = 0
    root_moves: int = 0
    book_hit: int = 0

    elapsed: float = 0.0
    nps: float = 0.0

    @property
    def total_nodes(self) -> int:
        return self.nodes + self.qnodes


_LAST_SEARCH_STATS = SearchStats()


def _reset_search_stats() -> None:
    global _LAST_SEARCH_STATS
    _LAST_SEARCH_STATS = SearchStats()


def get_last_search_stats() -> dict:
    return {
        **asdict(_LAST_SEARCH_STATS),
        "total_nodes": _LAST_SEARCH_STATS.total_nodes,
    }

try:
    from model import load_model
    print("Imported load_model successfully")
except Exception as e:
    load_model = None
    print(f"Failed importing load_model from model.py: {e}")

try:
    from tensor import board_to_tensor
    print("Imported board_to_tensor successfully")
except Exception as e:
    board_to_tensor = None
    print(f"Failed importing board_to_tensor from tensor.py: {e}")

MODEL_PATH = os.environ.get("CHESS_MODEL_PATH", "check_points/model_v7.pt")
MODEL_NAME = "model_v7.pt"

MATE_BOT_PATH = os.environ.get("MATE_BOT_PATH", "check_points/kill_bot_v2.pt")
MATE_BOT_NAME = "kill_bot_v2.pt"

print(f"MODEL_PATH={MODEL_PATH}")

print(f"load_model available? {load_model is not None}")
print(f"board_to_tensor available? {board_to_tensor is not None}")
print(f"path exists? {os.path.exists(MODEL_PATH)}")

model = None
if load_model is None:
    print("Model loader import failed.")
elif not os.path.exists(MODEL_PATH):
    print(f"Model file not found: {MODEL_PATH}")
else:
    try:
        model = load_model(MODEL_PATH)
        model.eval()
        print(f"Bot model loaded from {MODEL_PATH}")
    except Exception as e:
        print(f"Warning: failed to load bot model from {MODEL_PATH}: {e}")
        model = None

print(f"MATE_BOT_PATH={MATE_BOT_PATH}")

print(f"load_model available? {load_model is not None}")
print(f"board_to_tensor available? {board_to_tensor is not None}")
print(f"path exists? {os.path.exists(MATE_BOT_PATH)}")

mate_model = None
if load_model is None:
    print("Model loader import failed.")
elif not os.path.exists(MATE_BOT_PATH):
    print(f"Model file not found: {MATE_BOT_PATH}")
else:
    try:
        mate_model = load_model(MATE_BOT_PATH)
        mate_model.eval()
        print(f"Mate model loaded from {MATE_BOT_PATH}")
    except Exception as e:
        print(f"Warning: failed to load bot model from {MATE_BOT_PATH}: {e}")
        mate_model = None

WHITE = 'W'
BLACK = 'B'

COLOR = {"W": "White", "B": "Black"}

MAX_BOOK_PLIES = 12

EARLY = "EARLY"
MIDDLE = "MIDDLE"
LATE = "LATE"

def fmt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60

    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    parts.append(f"{s:.1f}s")

    return " ".join(parts)

def game_phase(chess_board):

    total_pieces = 0
    total_not_pawn = 0

    for color in (WHITE, BLACK):
        for piece in chess_board.players[color].pieces:
            if piece.name == "K":
                continue
            total_pieces += 1
            if piece.name != "P":
                total_not_pawn += 1

    # --- LATE GAME ---
    if total_pieces <= 12 or total_not_pawn <= 4:
        return LATE

    # --- MIDDLE GAME ---
    if total_pieces <= 26 or total_not_pawn <= 10:
        return MIDDLE

    # --- OTHERWISE ---
    return EARLY

try:
    import chess
    import chess.pgn
except Exception:
    chess = None
from datetime import datetime


def export_game_to_pgn(chess_board, output_path: str, model_path: str, result: str = "*"):
    if chess is None:
        raise RuntimeError("python-chess is required for PGN export")

    board = chess.Board()
    game = chess.pgn.Game()

    model_name = os.path.basename(model_path).replace(".pt", "")

    game.headers["Event"] = "Bot Self-Play"
    game.headers["Site"] = "Local"
    game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
    game.headers["White"] = model_name
    game.headers["Black"] = model_name
    game.headers["Result"] = result

    node = game

    for i, action in enumerate(chess_board.actions):
        move_uci = action.from_tile + action.to_tile
        if action.promotion:
            move_uci += action.promotion.lower()

        move = chess.Move.from_uci(move_uci)

        if move not in board.legal_moves:
            print(f"\nFailed at action {i}: {action}")
            print(f"UCI attempted: {move_uci}")
            print(f"python-chess board:\n{board}")
            print(f"Legal moves: {list(board.legal_moves)}")
            raise ValueError(f"Illegal move during PGN export: {move_uci}")

        board.push(move)
        node = node.add_variation(move)

    save_dir = output_path
    os.makedirs(save_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"game_{timestamp}.pgn"
    filepath = os.path.join(save_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        exporter = chess.pgn.FileExporter(f)
        game.accept(exporter)

    return filepath

# ── Debug print tree ───────────────────────────────────────────────────────

DEBUG_SEARCH = False
DEBUG_SEARCH_ROOT_ONLY = False
DEBUG_MAX_CHILDREN = 4

def _tree_prefix(level: int, is_last: bool | None = None) -> str:
    if level <= 0:
        return ""
    stem = "│   " * (level - 1)
    if is_last is None:
        return stem
    return stem + ("└── " if is_last else "├── ")

def _debug_log(debug: int, level: int, text: str, is_last: bool | None = None):
    if debug <= 0:
        return
    print(f"{_tree_prefix(level, is_last)}{text}")


def _fmt_score(x) -> str:
    if x == float("inf"):  return "inf"
    if x == float("-inf"): return "-inf"
    return f"{x:.4f}"   



# ── Piece-Square Tables ───────────────────────────────────────────────────────
# Each table is 64 values, index 0 = a1, index 63 = h8 (white's perspective)
# Values are fractional to keep them below material value thresholds
# Black's tables are mirrored automatically in get_position_bonus()

PAWN_TABLE = [
    0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,
    0.3,  0.3,  0.3,  0.3,  0.3,  0.3,  0.3,  0.3,
    0.1,  0.15,  0.2,  0.25,  0.25,  0.2,  0.15,  0.1,
    0.05, 0.1, 0.15,  0.2, 0.2, 0.15,  0.1, 0.05,
    0.0,  0.0,  0.0,  0.15,  0.15,  0.0,  0.0,  0.0,
    0.05,-0.05,-0.1,  0.0,  0.0, -0.1, -0.05, 0.05,
    0.05, 0.1,  0.1, -0.2, -0.2,  0.1,  0.1,  0.05,
    0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,
]

KNIGHT_TABLE = [
    -0.5, -0.4, -0.3, -0.3, -0.3, -0.3, -0.4, -0.5,
    -0.4, -0.2,  0.0,  0.0,  0.0,  0.0, -0.2, -0.4,
    -0.3,  0.0,  0.1,  0.15, 0.15, 0.1,  0.0, -0.3,
    -0.3,  0.05, 0.15, 0.2,  0.2,  0.15, 0.05,-0.3,
    -0.3,  0.0,  0.15, 0.2,  0.2,  0.15, 0.0, -0.3,
    -0.3,  0.05, 0.1,  0.15, 0.15, 0.1,  0.05,-0.3,
    -0.4, -0.2,  0.0,  0.05, 0.05, 0.0, -0.2, -0.4,
    -0.5, -0.4, -0.3, -0.3, -0.3, -0.3, -0.4, -0.5,
]

BISHOP_TABLE = [
    -0.2, -0.1, -0.1, -0.1, -0.1, -0.1, -0.1, -0.2,
    -0.1,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0, -0.1,
    -0.1,  0.0,  0.05, 0.1,  0.1,  0.05, 0.0, -0.1,
    -0.1,  0.05, 0.05, 0.15,  0.15,  0.05, 0.05,-0.1,
    -0.1,  0.0,  0.1,  0.15,  0.15,  0.1,  0.0, -0.1,
    -0.1,  0.1,  0.1,  0.1,  0.1,  0.1,  0.1, -0.1,
    -0.1,  0.05, 0.0,  0.0,  0.0,  0.0,  0.05,-0.1,
    -0.2, -0.1, -0.1, -0.1, -0.1, -0.1, -0.1, -0.2,
]

ROOK_TABLE = [
    0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,
    0.05, 0.1,  0.1,  0.1,  0.1,  0.1,  0.1,  0.05,
   -0.05, 0.0,  0.0,  0.0,  0.0,  0.0,  0.0, -0.05,
   -0.05, 0.0,  0.0,  0.0,  0.0,  0.0,  0.0, -0.05,
   -0.05, 0.0,  0.0,  0.0,  0.0,  0.0,  0.0, -0.05,
   -0.05, 0.0,  0.0,  0.0,  0.0,  0.0,  0.0, -0.05,
   -0.05, 0.0,  0.0,  0.0,  0.0,  0.0,  0.0, -0.05,
    0.0,  0.0,  0.0,  0.05, 0.05, 0.0,  0.0,  0.0,
]

QUEEN_TABLE = [
    -0.2, -0.1, -0.1, -0.05,-0.05,-0.1, -0.1, -0.2,
    -0.1,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0, -0.1,
    -0.1,  0.0,  0.05, 0.05, 0.05, 0.05, 0.0, -0.1,
    -0.05, 0.0,  0.05, 0.05, 0.05, 0.05, 0.0, -0.05,
     0.0,  0.0,  0.05, 0.05, 0.05, 0.05, 0.0, -0.05,
    -0.1,  0.05, 0.05, 0.05, 0.05, 0.05, 0.0, -0.1,
    -0.1,  0.0,  0.05, 0.0,  0.0,  0.0,  0.0, -0.1,
    -0.2, -0.1, -0.1, -0.05,-0.05,-0.1, -0.1, -0.2,
]

# King wants to stay safe and castled in the middlegame
KING_TABLE = [
    -0.10,  0.10,  0.20, -0.30, -0.30,  0.20,  0.10, -0.10,  
     0.15,  0.10,  0.05, -0.05, -0.05,  0.05,  0.10,  0.15, 
    -0.10, -0.20, -0.20, -0.20, -0.20, -0.20, -0.20, -0.10,  
    -0.20, -0.30, -0.30, -0.40, -0.40, -0.30, -0.30, -0.20, 
    -0.30, -0.40, -0.40, -0.50, -0.50, -0.40, -0.40, -0.30,  
    -0.30, -0.40, -0.40, -0.50, -0.50, -0.40, -0.40, -0.30,  
    -0.30, -0.40, -0.40, -0.50, -0.50, -0.40, -0.40, -0.30, 
    -0.30, -0.40, -0.40, -0.50, -0.50, -0.40, -0.40, -0.30, 
]

PIECE_TABLES = {
    'P': PAWN_TABLE,
    'N': KNIGHT_TABLE,
    'B': BISHOP_TABLE,
    'R': ROOK_TABLE,
    'Q': QUEEN_TABLE,
    'K': KING_TABLE,
}

from dataclasses import dataclass, field
from typing import List

@dataclass
class EvalParams:
    # ── Piece values (pawn anchored at 1.0 — DO NOT tune this) ──
    knight_value: float = 3.0
    bishop_value: float = 3.0
    rook_value:   float = 5.0
    queen_value:  float = 9.0

    # ── Piece-Square Tables (flattened 64-value lists) ──
    pawn_table:   List[float] = field(default_factory=lambda: list(PAWN_TABLE))
    knight_table: List[float] = field(default_factory=lambda: list(KNIGHT_TABLE))
    bishop_table: List[float] = field(default_factory=lambda: list(BISHOP_TABLE))
    rook_table:   List[float] = field(default_factory=lambda: list(ROOK_TABLE))
    queen_table:  List[float] = field(default_factory=lambda: list(QUEEN_TABLE))
    king_table:   List[float] = field(default_factory=lambda: list(KING_TABLE))

    # ── Pawn structure ──
    doubled_pawn_penalty:           float = 0.30
    isolated_pawn_penalty:          float = 0.35
    connected_pawn_bonus:           float = 0.15
    passed_pawn_base:               float = 0.15 
    passed_pawn_advance:            float = 0.10

    # ── Mobility ──
    mobility_weight:                float = 0.05

    # ── King safety ──
    castle_bonus:                   float = 0.50
    pawn_shield_bonus:              float = 0.15
    open_file_penalty:              float = 0.25
    semi_open_file_penalty:         float = 0.10
    attacker_proximity_weight:      float = 0.15
    immediate_proximity_penalty:    float = 0.12
    moderate_proximity_penalty:     float = 0.05

    # ── Piece bonuses ──
    bishop_pair_bonus:              float = 0.30
    bishop_mobility_bonus:          float = 0.02
    
    rook_open_file_bonus:           float = 0.25
    rook_semi_open_bonus:           float = 0.10
    loosly_connnected_rooks_bonus:  float = 0.05
    
    queen_early_exposure_penalty:   float = 0.20
    queen_rook_bonus:               float = 0.04
    queen_bishop_bonus:             float = 0.03 

    # ── Hanging pieces ──
    hanging_outnumbered_weight:     float = 0.5
    hanging_undefended_weight:      float = 0.25

    # -- Backtrack penalties --
    backtrack_penalty_light: float = 1.0
    backtrack_penalty_strong: float = 2.0


# Global instance — used by evaluate() at runtime
EVAL_PARAMS = EvalParams()

PIECE_VALUES = {'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 0}

def _piece_value(name: str, p: EvalParams) -> float:
    return {
        'P': 1.0,
        'N': p.knight_value,
        'B': p.bishop_value,
        'R': p.rook_value,
        'Q': p.queen_value,
        'K': 0.0,
    }[name]


COLUMNS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
ROWS    = ['1', '2', '3', '4', '5', '6', '7', '8']

def _square_index(location: str, color: str) -> int:
    """Convert a square like 'e4' to a table index 0-63.
    White reads the table bottom-up (rank 1 = index 0).
    Black's table is mirrored so rank 8 = index 0."""
    col = COLUMNS.index(location[0])
    row = ROWS.index(location[1])
    if color == WHITE:
        return (7 - row) * 8 + col       
    else:
        return row * 8 + col    # rank 8 row=7 → index 0..7 (mirrored)


def _search_legal_moves(chess_board, turn: str, repertoire_name="balanced"):
    moves = []
    for from_sq, move in chess_board.players[turn].possible_moves:
        piece = next(
            (p for p in chess_board.players[turn].pieces if p.location == from_sq),
            None
        )
        if piece is None:
            continue

        target_tile = chess_board._get_tile(move)
        if target_tile and target_tile.piece and target_tile.piece.name == "K":
            continue

        order_score = move_order_score(
            chess_board, piece, move, color=turn, repertoire_name=repertoire_name
        )
        moves.append((piece, move, order_score))
    return moves


# --- Search depth handling ----------------------------------------------

def _square_pressure(board, square: str, color: str) -> tuple[int, int]:
    opp = BLACK if color == WHITE else WHITE
    attack_pressure = board.pressure_map[opp].get(square, {"count": 0, "weight": 0.0, "total_cost": [], "min_cost": 0.0})
    defend_pressure = board.pressure_map[color].get(square, {"count": 0, "weight": 0.0, "total_cost": [], "min_cost": 0.0})
    return attack_pressure, defend_pressure


def _should_extend(piece, move, chess_board):
    target_tile = chess_board._get_tile(move)

    if not (target_tile and target_tile.piece and target_tile.piece.color != piece.color):
        return False

    victim = target_tile.piece.name
    attacker_val = PIECE_VALUES[piece.name]
    victim_val = PIECE_VALUES[victim]

    # only extend clearly forcing captures
    return victim_val >= attacker_val or victim == 'Q'

def _adjusted_depth(base_depth, num_moves, total_pieces):
    d = base_depth

    if num_moves <= 8:
        d += 1
    elif total_pieces <= 16:
        d += 1

    return min(d, base_depth + 1)


def _complexity_adjusted_depth(base_depth, num_moves, total_pieces, in_check, tactical, king_safety_gap):
    d = _adjusted_depth(base_depth, num_moves, total_pieces)
    if in_check or tactical:
        d += 1
    if king_safety_gap >= 0.55 and total_pieces > 10:
        d += 1
    # Keep runtime stable for interactive depth-3 play.
    return min(d, base_depth + 1)


def _is_tactical_position(chess_board, turn: str, moves: list[tuple], capture_count: int) -> bool:
    """Cheap tacticality signal used for move-cap widening."""
    if chess_board.players[turn].checked:
        return True
    if capture_count >= 4:
        return True

    # Quick proxy: plausible checking moves indicate tactical tension.
    plausible_checks = 0
    for piece, move, _ in moves:
        if _could_plausibly_give_check(chess_board, piece, move):
            plausible_checks += 1
            if plausible_checks >= 1:
                return True
    return False

# ── Evaluation Scoring ────────────────────────────────────────────────────────────────

MATE_SCORE = 100000

# In get_position_bonus, pass params:
def get_position_bonus(piece, p: EvalParams = None) -> float:
    if p is None:
        p = EVAL_PARAMS
    tables = {
        'P': p.pawn_table,
        'N': p.knight_table,
        'B': p.bishop_table,
        'R': p.rook_table,
        'Q': p.queen_table,
        'K': p.king_table,
    }
    table = tables.get(piece.name)
    if table is None:
        return 0.0
    return table[_square_index(piece.location, piece.color)]


def _pawn_structure(chess_board, color) -> float:
    """
    Returns a score (from color's perspective) for pawn structure.
    Penalties: doubled pawns, isolated pawns.
    Bonuses:   passed pawns, connected pawns.
    """
    opponent = BLACK if color == WHITE else WHITE
    my_pawns    = [p for p in chess_board.players[color].pieces    if p.name == 'P']
    opp_pawns   = [p for p in chess_board.players[opponent].pieces if p.name == 'P']

    my_files  = [p.location[0] for p in my_pawns]
    opp_files = [p.location[0] for p in opp_pawns]

    score = 0.0
    file_counts = {f: my_files.count(f) for f in set(my_files)}

    opp_pawn_rows = {}
    for p in opp_pawns:
        f = p.location[0]
        r = int(p.location[1])
        opp_pawn_rows.setdefault(f, []).append(r)

    for pawn in my_pawns:
        col = pawn.location[0]
        row = int(pawn.location[1])
        col_idx = COLUMNS.index(col)

        # ── Doubled pawn penalty ──────────────────────────────────────────
        if file_counts[col] > 1:
            score -= EVAL_PARAMS.doubled_pawn_penalty

        # ── Isolated pawn penalty ─────────────────────────────────────────
        left_file  = COLUMNS[col_idx - 1] if col_idx > 0 else None
        right_file = COLUMNS[col_idx + 1] if col_idx < 7 else None
        has_neighbor = (left_file  in my_files) or (right_file in my_files)
        if not has_neighbor:
            score -= EVAL_PARAMS.isolated_pawn_penalty

        # ── Connected pawn bonus ──────────────────────────────────────────
        # A pawn is "connected" if a friendly pawn guards it (diagonally adjacent)
        if left_file and left_file in my_files:
            left_pawns = [p for p in my_pawns if p.location[0] == left_file]
            if any(abs(int(p.location[1]) - row) == 1 for p in left_pawns):
                score += EVAL_PARAMS.connected_pawn_bonus
        if right_file and right_file in my_files:
            right_pawns = [p for p in my_pawns if p.location[0] == right_file]
            if any(abs(int(p.location[1]) - row) == 1 for p in right_pawns):
                score += EVAL_PARAMS.connected_pawn_bonus

        # ── Passed pawn bonus ─────────────────────────────────────────────
        # No opposing pawns on the same or adjacent files ahead of this pawn
        advance_rows = range(row + 1, 9) if color == WHITE else range(1, row)
        blocking_files = [f for f in [col, left_file, right_file] if f is not None]
        is_passed = not any(
            opp_r in advance_rows
            for f in blocking_files
            for opp_r in opp_pawn_rows.get(f, [])
        )
        if is_passed:
            # Bonus scales with how far advanced the pawn is
            advancement = (row - 1) if color == WHITE else (8 - row)
            score += EVAL_PARAMS.passed_pawn_base + EVAL_PARAMS.passed_pawn_advance * advancement

    return score


def _mobility(chess_board) -> float:
    """Legal move count difference: positive = white has more mobility."""
    white_moves = sum(len(p.moves) for p in chess_board.players[WHITE].pieces)
    black_moves = sum(len(p.moves) for p in chess_board.players[BLACK].pieces)
    return 0.05 * (white_moves - black_moves)


def _king_safety(chess_board, color) -> float:
    """
    Dynamic king safety based on:
      - Castled Structure Bonus (+)
      - Pawn shield in front of the king (+)
      - Open/semi-open files near the king (-)
      - Enemy piece proximity to the king (-)
      - Pressure opp attacks proximity to king (-)
    """
    opponent = BLACK if color == WHITE else WHITE
    king_pieces = [p for p in chess_board.players[color].pieces if p.name == 'K']
    if not king_pieces:
        return 0.0

    king = king_pieces[0]
    king_col_idx = COLUMNS.index(king.location[0])
    king_row     = int(king.location[1])

    score = 0.0

    # ── Castled Structure Bonus───────────────────────────────────────────────────────

    # Board has a castle structure
    phase = game_phase(chess_board)

    if phase != LATE:
        row = 1 if color == WHITE else 8
        piece = chess_board._get_tile(f"d{row}").piece
        if piece is not None and piece.name == 'R' and piece.color == color and king.location == f"c{row}":
            score += EVAL_PARAMS.castle_bonus
        piece = chess_board._get_tile(f"f{row}").piece
        if piece is not None and piece.name == 'R' and piece.color == color and king.location == f"g{row}":
            score += EVAL_PARAMS.castle_bonus
    else:
        # Endgame: reward king centralization
        king_col_idx = COLUMNS.index(king.location[0])
        king_row_idx = ROWS.index(king.location[1])
        center_dist = max(abs(king_col_idx - 3.5), abs(king_row_idx - 3.5))
        score += max(0.0, 0.6 - 0.15 * center_dist)


    # ── Pawn shield ───────────────────────────────────────────────────────
    # The two ranks directly in front of the king should have friendly pawns
    shield_row = king_row + 1 if color == WHITE else king_row - 1
    shield_files = [
        COLUMNS[i] for i in range(
            max(0, king_col_idx - 1),
            min(8, king_col_idx + 2)
        )
    ]
    friendly_pawns = {
        p.location for p in chess_board.players[color].pieces if p.name == 'P'
    }
    for f in shield_files:
        sq = f + str(shield_row)
        if 1 <= shield_row <= 8 and sq in friendly_pawns:
            score += EVAL_PARAMS.pawn_shield_bonus

    # ── Open file penalty ─────────────────────────────────────────────────
    all_pawn_files = {
        p.location[0]
        for side in (WHITE, BLACK)
        for p in chess_board.players[side].pieces
        if p.name == 'P'
    }
    for f in shield_files:
        if f not in all_pawn_files:          # fully open file near king
            score -= EVAL_PARAMS.open_file_penalty
        elif f not in {p.location[0] for p in chess_board.players[color].pieces if p.name == 'P'}:
            score -= EVAL_PARAMS.semi_open_file_penalty                    # semi-open (opponent pawn only)

    # ── Enemy attacker proximity ──────────────────────────────────────────
    for piece in chess_board.players[opponent].pieces:
        if piece.name in ('K', 'P'):
            continue
        opp_col = COLUMNS.index(piece.location[0])
        opp_row = int(piece.location[1])
        dist = max(abs(opp_col - king_col_idx), abs(opp_row - king_row))
        if dist <= 2:
            score -= EVAL_PARAMS.attacker_proximity_weight * PIECE_VALUES[piece.name] / 5.0

    # ── Attack proximity ──────────────────────────────────────────────────
    king_file_idx = COLUMNS.index(king.location[0])
    king_rank = int(king.location[1])
    
    for dr in range(-2, 3):
        for df in range(-2, 3):
            if df == 0 and dr == 0:
                continue

            file_idx = king_file_idx + df
            rank = king_rank + dr

            if not (0 <= file_idx < 8 and 1 <= rank <= 8):
                continue

            sq = f"{COLUMNS[file_idx]}{rank}"

            if chess_board._is_square_attacked(sq, opponent):
                # Heavier penalty for immediate ring
                if max(abs(df), abs(dr)) == 1:
                    score -= EVAL_PARAMS.immediate_proximity_penalty
                else:
                    score -= EVAL_PARAMS.moderate_proximity_penalty
            
    return score


def _bishop_tactics(chess_board, color) -> float:
    """
    Bonus for bishop pair, often stronger together than separately.
    Bonus for bishops controlling long diagonals, but this is somewhat captured by mobility and piece-square tables, so not implemented here.
    """
    score = 0.0

    bishops = [p for p in chess_board.players[color].pieces if p.name == 'B']

    if len(bishops) >= 2:       # Bonus for bishop pair
        score += EVAL_PARAMS.bishop_pair_bonus  

    bishop_mobility = sum(len(p.moves) for p in bishops)

    score += EVAL_PARAMS.bishop_mobility_bonus * bishop_mobility  # Bonus for each bishop helping queen mobility

    return score


def _rook_tactics(chess_board, color) -> float:
    """Bonus for rooks on open or semi-open files, or loose connection."""
    score = 0.0

    all_pawn_files = set()
    friendly_pawn_files = set()
    rooks = set()

    for side in (WHITE, BLACK):
        for p in chess_board.players[side].pieces:
            if p.name == 'P':
                all_pawn_files.add(p.location[0])
            if p.name == 'P' and p.color == color:
                friendly_pawn_files.add(p.location[0])
            if p.name == 'R' and p.color == color:
                rooks.add(p)

    for piece in chess_board.players[color].pieces:
        if piece.name != 'R':
            continue
        f = piece.location[0]
        if f not in all_pawn_files:
            score += EVAL_PARAMS.rook_open_file_bonus      # fully open file
        elif f not in friendly_pawn_files:
            score += EVAL_PARAMS.rook_semi_open_bonus       # semi-open (no friendly pawn)
    
    # Bonus for conncted rooks
    if len(rooks) >= 2:
        rook_positions = {(r.location[0], r.location[1]) for r in rooks}
        for r1 in rooks:
            for r2 in rooks:
                if r1 == r2:
                    continue
                if r1.location[0] == r2.location[0] or r1.location[1] == r2.location[1]:
                    score += EVAL_PARAMS.loosly_connnected_rooks_bonus / 2.0  # connected rooks bonus 
    
    return score


def _hanging_pieces(chess_board, color: str) -> float:
    """Penalty for loose/hanging pieces from color perspective."""
    score = 0.0
    for piece in chess_board.players[color].pieces:
        if piece.name == "K":
            continue
        attack_pressure, defend_pressure = _square_pressure(chess_board, piece.location, color)
        if attack_pressure['count'] == 0:
            continue

        piece_weight = PIECE_VALUES[piece.name]
        if defend_pressure['count'] == 0:
            score -= EVAL_PARAMS.hanging_undefended_weight * piece_weight
        elif attack_pressure['count'] > defend_pressure['count']:
            score -= EVAL_PARAMS.hanging_outnumbered_weight * piece_weight

    return score


def _repetition_penalty(chess_board, color) -> float:
    """
    Penalize clearly noise-driven repetition: same piece oscillating between
    two squares with no captures, checks, or pawn advances in between.
    Light deterrent only — should not punish legitimate retreats.
    """
    actions = chess_board.players[color].actions
    if len(actions) < 2:
        return 0.0

    def _is_meaningful(action) -> bool:
        """A move is meaningful if it captured, was a pawn move, or involved a castle."""
        return (
            getattr(action, 'captured', None) is not None
            or getattr(action, 'castle', None) is not None
            or getattr(action, 'piece_name', '') == 'P'
        )

    penalty = 0.0

    # --- Pattern 1: A->B then B->A with nothing meaningful in between ---
    if len(actions) >= 2:
        a_prev = actions[-2]
        a_last = actions[-1]
        if (not _is_meaningful(a_prev)
                and not _is_meaningful(a_last)
                and getattr(a_prev, 'piece_id', None) == getattr(a_last, 'piece_id', None)
                and a_prev.from_tile == a_last.to_tile
                and a_prev.to_tile == a_last.from_tile):
            penalty += EVAL_PARAMS.backtrack_penalty_light  # light nudge — might still be right move

    # --- Pattern 2: same move made twice (A->B ... A->B) with nothing in between ---
    if len(actions) >= 3:
        a1, a2, a3 = actions[-3], actions[-2], actions[-1]
        if (not _is_meaningful(a1)
                and not _is_meaningful(a2)
                and not _is_meaningful(a3)
                and getattr(a1, 'piece_id', None) == getattr(a3, 'piece_id', None)
                and a1.from_tile == a3.from_tile
                and a1.to_tile == a3.to_tile):
            penalty += EVAL_PARAMS.backtrack_penalty_strong # clearly going nowhere, stronger deterrent

    return penalty


def _development_score(chess_board, color: str) -> float:
    """Opening/middlegame development and pawn-structure guidance."""
    phase = game_phase(chess_board)
    if phase == LATE:
        return 0.0

    score = 0.0
    row_home = "1" if color == WHITE else "8"
    center_files = {"d", "e"}
    central_pawn_targets = {"d4", "e4"} if color == WHITE else {"d5", "e5"}
    start_minor_squares = {"b" + row_home, "g" + row_home, "c" + row_home, "f" + row_home}

    friendly = chess_board.players[color].pieces
    for piece in friendly:
        if piece.name in ("N", "B") and piece.location not in start_minor_squares:
            score += 0.12

    # Encourage occupied central pawn squares in early/midgame.
    for sq in central_pawn_targets:
        tile = chess_board._get_tile(sq)
        if tile and tile.piece and tile.piece.color == color and tile.piece.name == "P":
            score += 0.2
            atk, dfn = _square_pressure(chess_board, sq, color)
            if dfn['count'] >= atk['count']:
                score += 0.08

    # Penalize early unsupported flank pawn pushes.
    history_len = len(getattr(chess_board, "actions", []))
    for piece in friendly:
        if piece.name != "P":
            continue
        if piece.location[0] in ("a", "h") and history_len <= 18:
            start_rank = 2 if color == WHITE else 7
            advanced = abs(int(piece.location[1]) - start_rank)
            score -= 0.06 * max(0, advanced - 1)

        # Backward-ish central pawn heuristic: central pawn blocked while adjacent file lacks support.
        if piece.location[0] in center_files:
            forward = int(piece.location[1]) + (1 if color == WHITE else -1)
            if 1 <= forward <= 8:
                front_sq = f"{piece.location[0]}{forward}"
                front_tile = chess_board._get_tile(front_sq)
                if front_tile and front_tile.piece is not None:
                    left_idx = COLUMNS.index(piece.location[0]) - 1
                    right_idx = COLUMNS.index(piece.location[0]) + 1
                    neighbor_files = []
                    if left_idx >= 0:
                        neighbor_files.append(COLUMNS[left_idx])
                    if right_idx <= 7:
                        neighbor_files.append(COLUMNS[right_idx])
                    has_neighbor = any(
                        p.name == "P" and p.location[0] in neighbor_files
                        for p in friendly
                    )
                    if not has_neighbor:
                        score -= 0.08

    return score


def _queen_coordination_score(chess_board, queen, color: str, max_steps: int = 2) -> float:
    score = 0.0

    directions = [
        (1, 0), (-1, 0), (0, 1), (0, -1),
        (1, 1), (1, -1), (-1, 1), (-1, -1),
    ]

    qf = ord(queen.location[0]) - 97
    qr = int(queen.location[1]) - 1

    for df, dr in directions:
        for step in range(1, max_steps + 1):
            bf = qf - step * df
            br = qr - step * dr

            if not (0 <= bf < 8 and 0 <= br < 8):
                break

            sq = f"{chr(97 + bf)}{br + 1}"
            tile = chess_board._get_tile(sq)

            if tile is None or tile.piece is None:
                continue

            p = tile.piece
            if p.color != color:
                break

            if (df == 0 or dr == 0) and p.name == "R":
                score += EVAL_PARAMS.queen_rook_bonus
            elif abs(df) == abs(dr) and p.name == "B":
                score += EVAL_PARAMS.queen_bishop_bonus

            break

    return min(score, 0.12)


def _queen_tactics(chess_board, color: str) -> float:
    """
    Queen tactical pattern recognition and scoring.

    Exposure - penalize queen early out of home square.
    Coordination - queen aligned with rook or bishop on same file/rank/diagonal, cheap battery signal.
    """

    score = 0.0

    for piece in chess_board.players[color].pieces:
        if piece.name != 'Q':
            continue

        # Exposure
        ply_count = len(getattr(chess_board, "actions", []))
        home = "d1" if color == WHITE else "d8"
        if ply_count <= 12 and piece.location != home:
            score -= EVAL_PARAMS.queen_early_exposure_penalty

        # Coordination scoring
        score += _queen_coordination_score(chess_board, piece, color)

    return score

# --- Evaluatations -----------------------------------------------------------

def evaluate_terminal(chess_board, turn: str, root_color: str, ply: int):
    if len(chess_board.players[turn].possible_moves) == 0:
        if chess_board.players[turn].checked:
            # turn is mated
            if turn == root_color:
                return -MATE_SCORE + ply
            else:
                return MATE_SCORE - ply
        else:
            return 0.0
    return None


def evaluate_classical(chess_board, perspective_color, p=None) -> float:
    """
    Only classical evaluation based on handcrafted heuristics and piece-square tables.
    Used primarily for quescence search leaf evaluation.
    """

    if p is None:
        p = EVAL_PARAMS

    classical = 0.0
    for piece in chess_board.players[WHITE].pieces:
        classical += _piece_value(piece.name, p) + get_position_bonus(piece, p)
    for piece in chess_board.players[BLACK].pieces:
        classical -= _piece_value(piece.name, p) + get_position_bonus(piece, p)

    classical += _king_safety(chess_board, WHITE)
    classical -= _king_safety(chess_board, BLACK)

    classical += _pawn_structure(chess_board, WHITE)
    classical -= _pawn_structure(chess_board, BLACK)

    classical += _bishop_tactics(chess_board, WHITE)
    classical -= _bishop_tactics(chess_board, BLACK)

    classical += _rook_tactics(chess_board, WHITE)
    classical -= _rook_tactics(chess_board, BLACK)

    classical += _queen_tactics(chess_board, WHITE)
    classical -= _queen_tactics(chess_board, BLACK)

    classical += _mobility(chess_board)

    classical += _hanging_pieces(chess_board, WHITE)
    classical -= _hanging_pieces(chess_board, BLACK)

    classical += _development_score(chess_board, WHITE)
    classical -= _development_score(chess_board, BLACK)

    classical -= _repetition_penalty(chess_board, WHITE)
    classical += _repetition_penalty(chess_board, BLACK)

    if perspective_color == BLACK:
        classical = -classical

    return classical


def evaluate(chess_board, perspective_color, turn_to_move, p=None) -> float:

    t0 = time.perf_counter()
    _LAST_SEARCH_STATS.evaluate_calls += 1

    try:

        if p is None:
            p = EVAL_PARAMS

        if chess_board.players[WHITE].mated:
            return -MATE_SCORE if perspective_color == WHITE else MATE_SCORE

        if chess_board.players[BLACK].mated:
            return MATE_SCORE if perspective_color == WHITE else -MATE_SCORE

        phase = game_phase(chess_board)

        x = None
        if torch is not None and board_to_tensor is not None:
            tensor = board_to_tensor(chess_board, turn=turn_to_move)
            x = torch.tensor(tensor).unsqueeze(0).float()

        model_score = 0.0
        if model is not None and x is not None:
            with torch.no_grad():
                model_score = model(x).item()

        mate_score = 0.0
        if phase != EARLY:
            if mate_model is not None and x is not None:
                with torch.no_grad():
                    mate_score = mate_model(x).item()

        classical = 0.0
        for piece in chess_board.players[WHITE].pieces:
            classical += _piece_value(piece.name, p) + get_position_bonus(piece, p)
        for piece in chess_board.players[BLACK].pieces:
            classical -= _piece_value(piece.name, p) + get_position_bonus(piece, p)


        classical += _king_safety(chess_board, WHITE)
        classical -= _king_safety(chess_board, BLACK)

        classical += _pawn_structure(chess_board, WHITE)
        classical -= _pawn_structure(chess_board, BLACK)

        classical += _bishop_tactics(chess_board, WHITE)
        classical -= _bishop_tactics(chess_board, BLACK)

        classical += _rook_tactics(chess_board, WHITE)
        classical -= _rook_tactics(chess_board, BLACK)

        classical += _queen_tactics(chess_board, WHITE)
        classical -= _queen_tactics(chess_board, BLACK)

        classical += _mobility(chess_board)

        classical += _hanging_pieces(chess_board, WHITE)
        classical -= _hanging_pieces(chess_board, BLACK)

        classical += _development_score(chess_board, WHITE)
        classical -= _development_score(chess_board, BLACK)

        classical -= _repetition_penalty(chess_board, WHITE)
        classical += _repetition_penalty(chess_board, BLACK)


        model_scaled = model_score * 3
        model_scaled = max(min(model_scaled, 3), -3)

        # Model weight 
        # model is strongest early (best for natural human openings, classical eval can misread piece activity)
        # classical eval more reliable, model less trained on endgames.
        # use ply count for a sharper early-game boost independent of piece count.

        ply_count = len(getattr(chess_board, "actions", []))
        if ply_count <= 10:
            # Deep opening: model has strongest signal, classical can misread piece activity (added .1 to all)
            model_weight = 0.30
        elif phase == EARLY:
            model_weight = 0.20
        elif phase == MIDDLE:
            model_weight = 0.12
        else:  # LATE
            model_weight = 0.10

        # Mate Model Weight
        # Phase in mate_model score more heavily in mid/late game where tactical precision is critical 
        # classical eval can miss nuances (e.g. positional blunders), 
        # tapers as game becomes tactical (classical eval more reliable).

        mate_scaled = mate_score * 3
        mate_scaled = max(min(mate_scaled, 3), -3)

        mate_weight = 0.0
        if phase == MIDDLE:
            mate_weight = 0.08
            if chess_board.players[WHITE].checked or chess_board.players[BLACK].checked:
                mate_weight = 0.10
        
        if phase == LATE:
            mate_weight = 0.10
            if chess_board.players[WHITE].checked or chess_board.players[BLACK].checked:
                mate_weight = 0.20

        # Classical Weight
        # The dominant signal throughout that anchors the evaluation in fundamental chess principles, 
        # but tapers to allow model/mate signals to trigger favorable moves in critical moments.
        #
        # Typical weights may look something like the following:
        # EARLY WEIGHTS: classical (.70 - .80), model (.20 - .30), mate_model (0.0)
        # MIDDLE WEIGHTS: classical (.78 - .80), model (.12), mate_model (.08 - .10)
        # LATE WEIGHTS: classical (.70 - .80), model (.10), mate_model (.10 - .20)

        classical_weight = 1 - model_weight - mate_weight

        score = classical_weight * classical + model_weight * model_scaled + mate_weight * mate_scaled

        if perspective_color == BLACK:
            score = -score

        return score
    
    finally:
        _LAST_SEARCH_STATS.evaluate_time += time.perf_counter() - t0


def evaluate_fast(chess_board, p=None) -> float:
    """Lightweight eval for Texel tuning — material + PST only."""
    if p is None:
        p = EVAL_PARAMS
    score = 0.0
    for piece in chess_board.players[WHITE].pieces:
        score += _piece_value(piece.name, p) + get_position_bonus(piece, p)
    for piece in chess_board.players[BLACK].pieces:
        score -= _piece_value(piece.name, p) + get_position_bonus(piece, p)
    return score


# ── Minimax with Alpha-Beta Pruning ───────────────────────────────────────────
# alpha = best score the maximizing player is guaranteed so far
# beta  = best score the minimizing player is guaranteed so far
# If beta <= alpha we can stop searching this branch — the opponent
# already has a better option elsewhere and will never allow this line

def _opening_phase(board) -> bool:
    return len(getattr(board, "actions", [])) <= 10  # first 5 moves each side

def _is_castle_move(piece, move: str) -> bool:
    return (
        piece.name == 'K' and (
            (piece.color == WHITE and piece.location == 'e1' and move in ('g1', 'c1')) or
            (piece.color == BLACK and piece.location == 'e8' and move in ('g8', 'c8'))
        )
    )

def _could_plausibly_give_check(board, piece, move) -> bool:
    opp = BLACK if piece.color == WHITE else WHITE
    king_sq = board.black_king_location if opp == BLACK else board.white_king_location

    mc = ord(move[0])
    mr = int(move[1])
    kc = ord(king_sq[0])
    kr = int(king_sq[1])

    dc = abs(mc - kc)
    dr = abs(mr - kr)

    if piece.name == "N":
        return (dc, dr) in ((1, 2), (2, 1))
    if piece.name == "K":
        return dc <= 1 and dr <= 1
    if piece.name == "P":
        if piece.color == WHITE:
            return dr == 1 and dc == 1 and mr > kr
        return dr == 1 and dc == 1 and mr < kr
    if piece.name in ("B", "R", "Q"):
        return dc == 0 or dr == 0 or dc == dr

    return False

def _move_gives_check(board, piece, move) -> bool:
    mover = piece.color
    opp = BLACK if mover == WHITE else WHITE

    target_tile = board._get_tile(move)
    if target_tile and target_tile.piece and target_tile.piece.name == "K":
        return False

    snap = board._snapshot_state()

    try:
        board._move_piece(piece, move, simulate=True)
        board._sync_board()

        board.players[mover].update_moves(board, board.players[opp].actions)
        board.players[opp].update_moves(board, board.players[mover].actions)
        board.pressure_map[WHITE] = board._build_pressure_map(WHITE)
        board.pressure_map[BLACK] = board._build_pressure_map(BLACK)

        check = board._test_check(opp)

        check_mate = (
            board.players[opp].checked and
            len(board.players[opp].possible_moves) == 0
        )

        return check, check_mate

    except Exception:
        return False
    finally:
        board._restore_state(snap)


def _early_opening_safety_bonus(board, piece, move) -> float:
    """
    Reward moves that blunt cheap early mating ideas:
    - defend / vacate f7-f2 weaknesses
    - develop with tempo on an early queen
    - prefer sane responses to Qh5 / Bc4 setups
    """
    if not _opening_phase(board):
        return 0.0

    score = 0.0
    uci = f"{piece.location}{move}"

    # High-value anti-Scholar development moves
    anti_scholar = {
        "b8c6": 1.4,   # hits Qh5 ideas, natural development
        "g8f6": 1.2,   # develops and contests h5/f7 themes
        "f8c5": 0.8,   # normal Italian development
        "d7d6": 0.5,   # reinforces e5 / opens bishop
        "e7e6": 0.4,   # emergency dark-square stabilizer
        "g7g6": -0.4,  # too committal as a default anti-Qh5 answer
    }
    score += anti_scholar.get(uci, 0.0)

    # Discourage premature queen wandering in the opening
    if piece.name == "Q":
        score -= 0.8

    # Encourage knight/bishop development over random flank pawn moves
    if piece.name in ("N", "B"):
        score += 0.25
    elif piece.name == "P" and move[0] in ("a", "h"):
        score -= 0.25

    return score



def _is_quiet_backtrack(board, piece, move: str, color: str) -> bool:
    """
    Penalize moving the same piece back to the square it came from
    on its own previous turn. Uses the per-color action list so
    index -1 is always this side's last move, not the opponent's.
    """
    actions = board.players[color].actions   # ← per-color list
    if len(actions) < 1:
        return False

    target_tile = board._get_tile(move)
    is_capture = (
        target_tile is not None and
        target_tile.piece is not None and
        target_tile.piece.color != piece.color
    )
    is_promotion = (
        piece.name == 'P' and
        ((piece.color == WHITE and move[1] == '8') or
         (piece.color == BLACK and move[1] == '1'))
    )
    is_castle = _is_castle_move(piece, move)

    if is_capture or is_promotion or is_castle:
        return False

    # Check 1 ply back in THIS color's history (their last move)
    prev = actions[-1]
    if (getattr(prev, "piece_id", None) == piece.id and
        getattr(prev, "to_tile", None) == piece.location and
        getattr(prev, "from_tile", None) == move):
        return True

    # Check 2 plies back in THIS color's history
    if len(actions) >= 2:
        prev2 = actions[-2]
        if (getattr(prev2, "piece_id", None) == piece.id and
            getattr(prev2, "to_tile", None) == piece.location and
            getattr(prev2, "from_tile", None) == move):
            return True

    return False


def _see(board, square: str, color: str, captured_val: float = 0.0) -> float:
    """
    Cost-ladder Static Exchange Evaluation (SEE).
    Assumes the side `color` has just moved a piece
    onto `square`.

    Returns a net score from `color`'s perspective:
      + positive  -> favorable exchange / favorable retained control
      + negative  -> bad exchange / likely tactical loss

    Structure of the score:
      1) material exchange result from alternating cheapest captures
      2) retained-square-control bonus after the exchange sequence

    `captured_val` is the value already won by landing on the square
    (e.g. taking a pawn = 1, quiet move = 0).
    """
    opp = BLACK if color == WHITE else WHITE

    tile = board._get_tile(square)
    if tile is None or tile.piece is None:
        return captured_val

    landed_piece = tile.piece
    landed_cost = PIECE_VALUES[landed_piece.name]

    attack_pressure, defend_pressure = _square_pressure(board, square, color)

    # Opponent attackers available to capture the landed piece
    opp_costs = sorted(attack_pressure.get("costs", []))

    # Friendly defenders available to recapture AFTER the landed piece is taken.
    # Remove the landed piece itself once from the defender list if present.
    my_costs = list(defend_pressure.get("costs", []))
    removed_landed = False
    filtered_my_costs = []
    for c in sorted(my_costs):
        if not removed_landed and c == landed_cost:
            removed_landed = True
            continue
        filtered_my_costs.append(c)
    my_costs = filtered_my_costs

    # No opponent capture exists: square is tactically safe.
    if not opp_costs:
        reserve_edge = sum(my_costs) - sum(opp_costs)
        return captured_val + 0.08 * reserve_edge

    gain = captured_val
    current_target_cost = landed_cost
    side_to_act = opp  # opponent gets first recapture chance
    i_opp = 0
    i_me = 0

    while True:
        if side_to_act == opp:
            if i_opp >= len(opp_costs):
                break

            # Opponent captures our current target
            gain -= current_target_cost

            # Their capturing piece becomes the new target for us
            current_target_cost = opp_costs[i_opp]
            i_opp += 1
            side_to_act = color

        else:
            if i_me >= len(my_costs):
                break

            # We recapture opponent's current target
            gain += current_target_cost

            # Our recapturing piece becomes the new target for them
            current_target_cost = my_costs[i_me]
            i_me += 1
            side_to_act = opp

    # Residual square-control / reserve signal after the exchange ladder
    remaining_opp = opp_costs[i_opp:]
    remaining_me = my_costs[i_me:]

    remaining_me_total = sum(remaining_me)
    remaining_opp_total = sum(remaining_opp)

    remaining_me_min = remaining_me[0] if remaining_me else float("inf")
    remaining_opp_min = remaining_opp[0] if remaining_opp else float("inf")

    reserve_edge = remaining_me_total - remaining_opp_total
    cheap_control_edge = (
        (0.0 if remaining_opp_min == float("inf") else remaining_opp_min)
        - (0.0 if remaining_me_min == float("inf") else remaining_me_min)
    )

    return gain


def _passes_opening_sanity(board, piece, move: str) -> bool:
    if not _opening_phase(board):
        return True

    target_tile = board._get_tile(move)
    is_capture = (
        target_tile is not None and
        target_tile.piece is not None and
        target_tile.piece.color != piece.color
    )

    # Avoid early flank pawn pushes unless tactical
    if piece.name == "P" and move[0] in ("a", "h") and len(getattr(board, "actions", [])) <= 8 and not is_capture:
        return False

    # Avoid early queen wandering unless tactical
    if piece.name == "Q" and len(getattr(board, "actions", [])) <= 8 and not is_capture:
        return False

    return True

def _piece_table(piece, p=None):
    if p is None:
        p = EVAL_PARAMS
    return {
        'P': p.pawn_table,
        'N': p.knight_table,
        'B': p.bishop_table,
        'R': p.rook_table,
        'Q': p.queen_table,
        'K': p.king_table,
    }.get(piece.name)


def _pst_delta_for_move(piece, move: str) -> float:
    """
    Cheap quiet-move piece-improvement proxy:
    bonus = PST(after) - PST(before)
    """
    before = get_position_bonus(piece)
    idx = _square_index(move, piece.color)

    if piece.name == 'P':
        after = EVAL_PARAMS.pawn_table[idx]
    elif piece.name == 'N':
        after = EVAL_PARAMS.knight_table[idx]
    elif piece.name == 'B':
        after = EVAL_PARAMS.bishop_table[idx]
    elif piece.name == 'R':
        after = EVAL_PARAMS.rook_table[idx]
    elif piece.name == 'Q':
        after = EVAL_PARAMS.queen_table[idx]
    elif piece.name == 'K':
        after = EVAL_PARAMS.king_table[idx]
    else:
        after = 0.0

    return after - before

def _piece_placement_headroom(piece, p=None) -> float:
    """
    How much theoretical PST upside this piece still has from its current square.
    Higher = more poorly placed relative to its best known squares.
    """
    if p is None:
        p = EVAL_PARAMS

    table = _piece_table(piece, p)
    if table is None:
        return 0.0

    cur = table[_square_index(piece.location, piece.color)]
    return max(table) - cur


def _is_worst_placed_piece(piece, own_pieces, p=None, slack: float = 0.05) -> bool:
    """
    True if this piece is among the worst-placed friendly pieces by PST headroom.
    Safe when only the king remains.
    """
    if p is None:
        p = EVAL_PARAMS

    non_king_pieces = [other for other in own_pieces if other.name != 'K']
    if not non_king_pieces:
        return False

    my_headroom = _piece_placement_headroom(piece, p)
    worst_headroom = max(_piece_placement_headroom(other, p) for other in non_king_pieces)
    return my_headroom >= worst_headroom - slack


def move_order_score(board, piece, move, color=None, repertoire_name="balanced"):

    t0 = time.perf_counter()
    _LAST_SEARCH_STATS.move_order_calls += 1

    try:
            
        score = 0.0

        # Always define this first
        target_tile = board._get_tile(move)

        is_capture = (
            target_tile is not None and
            target_tile.piece is not None and
            target_tile.piece.color != piece.color
        )

        is_quiet = not is_capture

        if is_capture:
            captured_val = PIECE_VALUES[target_tile.piece.name]
        else:
            captured_val = 0.0

        # Checks and discovered checks are very forcing, so we want to give them more leeway in move ordering.
        # Currently using a cheap static proxy for whether the move could plausibly give check.
        forcing = False
        if _could_plausibly_give_check(board, piece, move):
            check, check_mate = _move_gives_check(board, piece, move)

            if check:
                forcing = True
            
            if check_mate:
                return MATE_SCORE  # immediately prioritize known mates
                
            
        see = 0.0

        # 1. Captures: strong MVV-LVA
        if is_capture:
            snap = board._snapshot_state()
            try:
                board._move_piece(piece, move, simulate=True)
                board._sync_board()

                mover = piece.color
                opp = BLACK if mover == WHITE else WHITE

                # Regenerate raw attacks for the simulated position
                board.players[mover].update_moves(board, board.players[opp].actions)
                board.players[opp].update_moves(board, board.players[mover].actions)
                board.pressure_map[WHITE] = board._build_pressure_map(WHITE)
                board.pressure_map[BLACK] = board._build_pressure_map(BLACK)

                see = _see(board, move, captured_val=captured_val, color=mover)

                if see < 0:
                    # Quiet move lands on a tactically losing square
                    score -= 5.0 + 0.75 * abs(see)
                elif see == 0:
                    # Neutral square
                    score += 0.50
                else:
                    # Safe square with favorable recapture structure —
                    # raised ceiling so this competes with center/PST bonuses
                    score += 1.50 + 0.50 * min(see, 3)

            finally:
                board._restore_state(snap)

        # 2. Promotions
        if piece.name == 'P' and (
            (piece.color == WHITE and move[1] == '8') or
            (piece.color == BLACK and move[1] == '1')
        ):
            score += 7.0

        # 3. Checks
        if forcing and see >= 0:
            score += 0.15

        # 4. Castling
        if piece.color == WHITE and piece.name == "K":
            if piece.location == "e1" and move in ("c1", "g1"):
                score += 5.0
        elif piece.color == BLACK and piece.name == "K":
            if piece.location == "e8" and move in ("c8", "g8"):
                score += 5.0

        history_len = len(getattr(board, "actions", []))

        # 5. Center / development only early
        if history_len <= 12:
            center_bonus = {
                'd4': 0.8, 'e4': 0.8, 'd5': 0.8, 'e5': 0.8,
                'c3': 0.3, 'd3': 0.3, 'e3': 0.3, 'f3': 0.3,
                'c4': 0.3, 'f4': 0.3, 'c5': 0.3, 'f5': 0.3,
                'c6': 0.3, 'd6': 0.3, 'e6': 0.3, 'f6': 0.3,
            }
            score += center_bonus.get(move, 0.0)
            score += _early_opening_safety_bonus(board, piece, move)

        # 5.5 Lightweight piece-location improvement bonus
        pst_delta = _pst_delta_for_move(piece, move)
        if piece.name != "K" and pst_delta > 0:
            score += 1.0 * pst_delta
            if _is_worst_placed_piece(piece, board.players[piece.color].pieces):
                score += 0.15

        # 6. Book bonus only when relevant
        if color is not None and history_len <= 16:
            score += book_move_bonus(
                board, piece, move,
                color=color,
                repertoire_name=repertoire_name
            )

        # 7. Quiet backtrack penalty when not in check
        if _is_quiet_backtrack(board, piece, move, color or piece.color) and not board.players[piece.color].checked:
            score -= 2.0

        # 8. Quiet move ordering
        if is_quiet:
            see = 0.0
            snap = board._snapshot_state()
            try:
                board._move_piece(piece, move, simulate=True)
                board._sync_board()

                mover = piece.color
                opp = BLACK if mover == WHITE else WHITE

                # Regenerate raw attacks for the simulated position
                board.players[mover].update_moves(board, board.players[opp].actions)
                board.players[opp].update_moves(board, board.players[mover].actions)
                board.pressure_map[WHITE] = board._build_pressure_map(WHITE)
                board.pressure_map[BLACK] = board._build_pressure_map(BLACK)

                see = _see(board, move, captured_val=captured_val, color=mover)

                if see < 0:
                    # Quiet move lands on a tactically losing square
                    score -= 5.0 + 0.75 * abs(see)
                elif see == 0:
                    # Neutral square, small reward
                    score += 0.20
                else:
                    # Safe square with favorable recapture structure
                    score += 0.50 + 0.25 * min(see, 3)

            finally:
                board._restore_state(snap)

        # 9. Penalize clearly losing captures
        if is_capture:
            piece_val = PIECE_VALUES[piece.name]
            victim_val = PIECE_VALUES[target_tile.piece.name]
            if piece_val > victim_val:
                to_attackers, to_defenders = _square_pressure(board, move, piece.color)
                if to_attackers['count'] > to_defenders['count']:
                    score -= 1.5 * (piece_val - victim_val)

        # 10. Queen Tactics
        # Discourage early queen moves that don't have a clear tactical justification.
        # Queen safety, penalize moves that expose the queen to early attacks without compensation.
        if piece.name == "Q":

            # Lightly penalize early queen development
            if len(getattr(board, "actions", [])) <= 10:
                score -= 1.5
                
            # Backdoor
            if target_tile and target_tile.piece == None:
                attack_pressure, defend_pressure = _square_pressure(board, target_tile.id, color)
                if attack_pressure['count'] == 0:
                    score += 0.2
                if attack_pressure['count'] == 0 and defend_pressure['count'] > 0: # defended safe square
                    score += 0.2

            # Trading Queens - simplify the game when ahead
            opp = BLACK if piece.color == WHITE else WHITE
            if is_capture and target_tile.piece.name == "Q" and board.players[color].points > board.players[opp].points:
                score += 0.75

        return score
    
    finally:
        _LAST_SEARCH_STATS.move_order_time += time.perf_counter() - t0


def _quiescence(chess_board, alpha: float, beta: float, root_color: str,
                turn: str, depth: int = 4, deadline: float = None) -> float:
    """
    Internal quiescence worker with explicit turn tracking.
    Search only captures from noisy positions.
    """

    t0 = time.perf_counter()
    _LAST_SEARCH_STATS.quiescence_calls += 1
    _LAST_SEARCH_STATS.qnodes += 1

    try:

        if deadline is not None and time.time() >= deadline:
            return evaluate_classical(chess_board, perspective_color=root_color)

        maximizing = (turn == root_color)
        next_turn = BLACK if turn == WHITE else WHITE

        if depth == 0:
            stand_pat = evaluate(chess_board, perspective_color=root_color, turn_to_move=turn)
        else:
            stand_pat = evaluate_classical(chess_board, perspective_color=root_color)

        # Stand-pat pruning
        if maximizing:
            if stand_pat >= beta:
                return stand_pat
            alpha = max(alpha, stand_pat)
            best = stand_pat
        else:
            if stand_pat <= alpha:
                return stand_pat
            beta = min(beta, stand_pat)
            best = stand_pat

        if depth == 0:
            return stand_pat

        captures = []
        for piece in chess_board.players[turn].pieces:
            for move in piece.moves:
                target_tile = chess_board._get_tile(move)
                # Guard against stale moves after restore
                if target_tile and target_tile.piece and target_tile.piece.color == piece.color:
                    continue
                if target_tile and target_tile.piece and target_tile.piece.color != piece.color:
                    if target_tile and target_tile.piece and target_tile.piece.name == "K":
                        continue
                    victim_val = PIECE_VALUES[target_tile.piece.name]
                    attacker_val = PIECE_VALUES[piece.name]
                    order = victim_val * 10 - attacker_val
                    captures.append((piece, move, order))

        if not captures:
            return stand_pat

        captures.sort(key=lambda x: x[2], reverse=True)
        cap = 12 if chess_board.players[turn].checked else 8

        for piece, move, _ in captures[:cap]:
            snap = chess_board._snapshot_state()
            try:
                chess_board._move_piece(piece, move, simulate=True)
                chess_board._fast_update_tiles()

                if chess_board._test_check(turn):   # turn = side that just moved
                    continue

                score = _quiescence(
                    chess_board,
                    alpha,
                    beta,
                    root_color,
                    next_turn,
                    depth - 1,
                    deadline
                )
            except ValueError as e:
                if "kings cannot be captured" in str(e):
                    continue
                raise
            finally:
                chess_board._restore_state(snap)

            if score is None:
                raise ValueError(
                    f"_quiescence returned None for {piece} {piece.location}->{move}"
                )

            if maximizing:
                if score > best:
                    best = score
                if best >= beta:
                    return best
                alpha = max(alpha, best)
            else:
                if score < best:
                    best = score
                if best <= alpha:
                    return best
                beta = min(beta, best)

        return best
    
    finally:
        _LAST_SEARCH_STATS.quiescence_time += time.perf_counter() - t0


def minimax(chess_board, depth: int, turn: str, root_color: str,
            alpha=float('-inf'), beta=float('inf'),
            repertoire_name="balanced",
            ply: int = 0,
            debug: int = 0,
            debug_max_children: int | None = None,
            deadline: float = None) -> float:
    """
    debug levels:
      0 = off
      1 = major node summaries / root-adjacent info only
      2 = full cascading tree
    """

    _LAST_SEARCH_STATS.nodes += 1

    maximizing = (turn == root_color)
    role = "MAX" if maximizing else "MIN"
    next_turn = BLACK if turn == WHITE else WHITE

    # Time cutoff check 
    if deadline is not None and time.time() >= deadline:
        return evaluate(chess_board, perspective_color=root_color, turn_to_move=turn)

    # 1. TERMINAL CHECK — FIRST
    terminal = evaluate_terminal(chess_board, turn, root_color, ply)
    if terminal is not None:
        _LAST_SEARCH_STATS.terminal_hits += 1
        if debug >= 2:
            _debug_log(debug, ply, f"{role} {COLOR[turn]} terminal => {_fmt_score(terminal)}")
        return terminal

    # 2. DEPTH LIMIT — run quiescence search instead of raw static eval
    if depth == 0:

        _LAST_SEARCH_STATS.leaf_evals += 1
        score = _quiescence(chess_board, alpha, beta, root_color, turn,
                            depth=4, deadline=deadline)
        
        if debug >= 2:
            _debug_log(debug, ply, f"{role} {COLOR[turn]} leaf eval => {_fmt_score(score)}")
        return score

    # Gather legal moves for side to move
    all_moves = []
    for piece in chess_board.players[turn].pieces:
        for move in piece.moves:
            target_tile = chess_board._get_tile(move)
            if target_tile and target_tile.piece and target_tile.piece.color == piece.color:
                continue
            if target_tile and target_tile.piece and target_tile.piece.name == "K":
                continue

            order_score = move_order_score(
                chess_board,
                piece,
                move,
                color=turn,
                repertoire_name=repertoire_name
            )

            if order_score is None:
                raise ValueError(
                    f"move_order_score returned None for {piece} {piece.location}->{move}"
                )

            if not isinstance(order_score, (int, float)):
                raise TypeError(
                    f"move_order_score returned non-numeric score {order_score!r} "
                    f"for {piece} {piece.location}->{move}"
                )
            
            all_moves.append((piece, move, order_score))

    all_moves.sort(key=lambda pm: pm[2], reverse=True)

    candidate_cap = 20

    if len(all_moves) > candidate_cap:
        all_moves = all_moves[:candidate_cap]

    # No legal moves — stalemate or checkmate
    if not all_moves:
        if not chess_board.players[turn].checked:
            if debug >= 2:
                _debug_log(debug, ply, f"{role} {COLOR[turn]} stalemate => 0.00")
            return 0.0
        mate_score = float('-inf') if turn == root_color else float('inf')
        if debug >= 2:
            _debug_log(debug, ply, f"{role} {COLOR[turn]} no legal moves => {_fmt_score(mate_score)}")
        return mate_score

    if debug >= 2:
        _debug_log(
            debug,
            ply,
            f"{role} {COLOR[turn]} depth={depth} alpha={_fmt_score(alpha)} beta={_fmt_score(beta)}"
        )

    shown_count = len(all_moves)
    if debug >= 2 and debug_max_children is not None:
        shown_count = min(len(all_moves), debug_max_children)

    best = float('-inf') if maximizing else float('inf')
    found_legal_child = False

    for idx, (piece, move, order_score) in enumerate(all_moves):
        will_show = debug >= 2 and idx < shown_count
        is_last_shown = will_show and (idx == shown_count - 1)
        from_sq = piece.location

        if will_show:
            _debug_log(
                debug,
                ply + 1,
                f"{piece.name} {from_sq}->{move} order={order_score:.2f}",
                is_last=is_last_shown
            )

        snap = chess_board._snapshot_state()

        try:
            is_forcing = _should_extend(piece, move, chess_board)

            chess_board._move_piece(piece, move, simulate=True)
            chess_board._fast_update_tiles()

            # If moving side's king is now in check, this was an illegal move. Skip it.
            if chess_board._test_check(turn):
                continue

            if chess_board.players[next_turn].checked:
                is_forcing = True

            extension = 1 if (depth == 1 and is_forcing) else 0

            if will_show and extension:
                _debug_log(debug, ply + 2, "forcing extension +1")

            score = minimax(
                chess_board,
                depth - 1 + extension,
                next_turn,
                root_color,
                alpha,
                beta,
                repertoire_name=repertoire_name,
                ply=ply + 2,
                debug=debug,
                debug_max_children=debug_max_children,
                deadline=deadline
            )

            if score is None:
                raise ValueError(
                    f"minimax returned None at ply={ply} "
                    f"turn={turn} piece={piece} from={from_sq} to={move} "
                    f"depth={depth} next_turn={next_turn}"
                )

            found_legal_child = True

            if will_show:
                _debug_log(debug, ply + 2, f"result => {_fmt_score(score)}")

        except ValueError as e:
            if "kings cannot be captured" in str(e):
                if will_show:
                    _debug_log(debug, ply + 2, "skipped illegal king-capture branch")
                continue
            raise
        finally:
            chess_board._restore_state(snap)

        if maximizing:
            if score > best:
                best = score
                if will_show:
                    _debug_log(debug, ply + 2, f"new best MAX => {_fmt_score(best)}")
            alpha = max(alpha, best)
        else:
            if score < best:
                best = score
                if will_show:
                    _debug_log(debug, ply + 2, f"new best MIN => {_fmt_score(best)}")
            beta = min(beta, best)

        if beta <= alpha:
            _LAST_SEARCH_STATS.cutoffs += 1
            if will_show:
                _debug_log(
                    debug,
                    ply + 2,
                    f"PRUNE alpha={_fmt_score(alpha)} beta={_fmt_score(beta)}"
                )
            break

    if debug >= 2:
        _debug_log(debug, ply, f"{role} {COLOR[turn]} returns {_fmt_score(best)}")

    if not found_legal_child:
        if chess_board.players[turn].checked:
            return float('-inf') if turn == root_color else float('inf')
        return 0.0

    return best


def best_move(chess_board, color, depth=2, repertoire_name="balanced",
              use_opening_book=True, debug: int = 0,
              debug_max_children: int | None = 4,
              time_budget: int=None):
    """
    debug levels:
      0 = off
      1 = root-only summary
      2 = full cascading tree

    debug_max_children:
      limits how many children are shown in debug tree only;
      it does NOT change the actual search unless you change the search caps below.
    """
    _reset_search_stats()
    t_search_start = time.perf_counter()

    try:

        deadline = None if time_budget is None else time.time() + time_budget
        history_len = len(getattr(chess_board, "actions", []))

        if use_opening_book and history_len <= MAX_BOOK_PLIES:
            weighted_book = os.environ.get("CHESS_BOOK_WEIGHTED", "1") != "0"
            book_choice = choose_book_move(
                chess_board,
                color,
                repertoire_name=repertoire_name,
                weighted=weighted_book,
                deterministic_top=not weighted_book,
            )
            if book_choice is not None:
                from_sq, to_sq, meta = book_choice
                book_piece = next((p for p in chess_board.players[color].pieces if p.location == from_sq), None)
                if book_piece is not None and _passes_opening_sanity(chess_board, book_piece, to_sq):
                    if debug >= 1:
                        opening_name = meta.get("name") or meta.get("opening") or "book"
                        _debug_log(debug, 0, f"BOOK {COLOR[color]} chooses {from_sq}->{to_sq} ({opening_name})")
                    return (from_sq, to_sq)

        best_score = float('-inf')
        chosen = None

        alpha = float('-inf')
        beta  = float('inf')

        next_turn = BLACK if color == WHITE else WHITE
        candidate_moves = []

        for from_sq, move in list(chess_board.players[color].possible_moves):
            piece = next(
                (p for p in chess_board.players[color].pieces if p.location == from_sq),
                None
            )
            if piece is None:
                continue

            target_tile = chess_board._get_tile(move)

            # Reject stale same-color move immediately
            if target_tile and target_tile.piece and target_tile.piece.color == piece.color:
                continue

            if target_tile and target_tile.piece and target_tile.piece.name == "K":
                continue

            order_score = move_order_score(
                chess_board,
                piece,
                move,
                color=color,
                repertoire_name=repertoire_name
            )

            if order_score is None:
                raise ValueError(
                    f"move_order_score returned None for {piece} {piece.location}->{move}"
                )

            if not isinstance(order_score, (int, float)):
                raise TypeError(
                    f"move_order_score returned non-numeric score {order_score!r} "
                    f"for {piece} {piece.location}->{move}"
                )

            candidate_moves.append((piece, move, order_score))

        # Add search depth for limited move list and reduced piece counts
        num_moves = len(candidate_moves)
        total_pieces = len(chess_board.players[WHITE].pieces) + len(chess_board.players[BLACK].pieces)
        approx_king_safety_gap = abs(
            _king_safety(chess_board, WHITE) - _king_safety(chess_board, BLACK)
        )

        candidate_moves.sort(key=lambda pm: pm[2], reverse=True)

        root_capture_count = 0
        for piece, move, _ in candidate_moves:
            target_tile = chess_board._get_tile(move)

            # Guard against stale moves after restore
            if target_tile and target_tile.piece and target_tile.piece.color == piece.color:
                continue
            if target_tile and target_tile.piece and target_tile.piece.name == "K":
                continue

            if target_tile and target_tile.piece and target_tile.piece.color != piece.color:
                root_capture_count += 1

        root_tactical = _is_tactical_position(chess_board, color, candidate_moves, root_capture_count)
        search_depth = _complexity_adjusted_depth(
            depth,
            num_moves,
            total_pieces,
            chess_board.players[color].checked,
            root_tactical,
            approx_king_safety_gap,
        )

        root_cap = 20

        if chess_board.players[color].checked:
            root_cap = 24
        elif root_tactical:
            root_cap = 22

        if len(candidate_moves) > root_cap and total_pieces > 10:
            candidate_moves = candidate_moves[:root_cap]

        if debug >= 1:
            _debug_log(
                debug,
                0,
                f"ROOT {COLOR[color]} search_depth={search_depth} candidates={len(candidate_moves)}"
            )


        fallback = None

        for idx, (piece, move, order_score) in enumerate(candidate_moves):
            is_last = (idx == len(candidate_moves) - 1)
            from_sq = piece.location
            snap = chess_board._snapshot_state()

            if debug >= 1:
                _debug_log(
                    debug,
                    1,
                    f"{piece.name} {from_sq}->{move} order={order_score:.2f}",
                    is_last=is_last if debug >= 2 else None
                )

            try:
                chess_board._move_piece(piece, move, simulate=True)
                chess_board._refresh_search_state_for_turn(next_turn)

                # Return mated opponent move immediately
                if chess_board.players[next_turn].checked:
                    raw_moves = [m for p in chess_board.players[next_turn].pieces for m in p.moves]
                    if not raw_moves:
                        return (from_sq, move)
                
                if fallback is None:
                    fallback = (from_sq, move)

                if deadline is not None and time.time() >= deadline:
                    return chosen or fallback

                score = minimax(
                    chess_board,
                    search_depth - 1,
                    next_turn,
                    color,
                    alpha,
                    beta,
                    repertoire_name=repertoire_name,
                    ply=2,
                    debug=debug,
                    debug_max_children=debug_max_children,
                    deadline=deadline
                )

                if score is None:
                    raise ValueError(
                        f"root minimax returned None for {piece} {from_sq}->{move}"
                    )

                if debug >= 1:
                    _debug_log(debug, 2 if debug >= 2 else 1, f"root result => {_fmt_score(score)}")

            except ValueError as e:
                if "kings cannot be captured" in str(e):
                    if debug >= 1:
                        _debug_log(debug, 2 if debug >= 2 else 1, "skipped illegal king-capture branch")
                    continue
                raise
            finally:
                chess_board._restore_state(snap)

            if score > best_score:
                best_score = score
                chosen = (from_sq, move)
                if debug >= 1:
                    _debug_log(debug, 2 if debug >= 2 else 1, f"{COLOR[color]} new best => {chosen} score={_fmt_score(best_score)}")

            if deadline is not None and time.time() >= deadline:
                return chosen or fallback

            alpha = max(alpha, best_score)

        if chosen is not None:
            if chosen not in set(chess_board.players[color].possible_moves):
                raise ValueError(f"best_move selected stale/illegal move: {chosen}")

        if chosen is not None and debug >= 1:
            chosen_piece = chess_board._get_tile(chosen[0]).piece
            piece_name = chosen_piece.name if chosen_piece else "?"
            _debug_log(
                debug,
                0,
                f"CHOSEN {COLOR[color]}: {piece_name} {chosen[0]}->{chosen[1]} score={_fmt_score(best_score)}"
            )

        return chosen

    finally:
        _LAST_SEARCH_STATS.elapsed = time.perf_counter() - t_search_start
        if _LAST_SEARCH_STATS.elapsed > 0:
            _LAST_SEARCH_STATS.nps = _LAST_SEARCH_STATS.total_nodes / _LAST_SEARCH_STATS.elapsed

        _LAST_SEARCH_STATS.refresh_time = chess_board.refresh_time
        chess_board.refresh_time = 0.0  # reset for next search


def main():

    print(f"MODEL LOADED? {model is not None} PATH={MODEL_PATH}")

    print("Enter the following infromation exactly in place:\n")
    info = input("num_games depth debug \n")
    games_str, depth_str, debug_str = info.split()

    try:
        games = int(games_str)
        depth = int(depth_str)
        debug = int(debug_str)

        avg_time = 0
        total_time = 0
        avg_num_moves = 0
        total_moves = 0
        total_castles = 0
        total_promotions = 0
        white_wins = 0
        black_wins = 0

        num_moves = 0 
        num_castles = 0        
        num_promo = 0

        start_time = time.time()

        for game in range(games):
            print(f"GAME {game}: ")
            chess_board = ChessBoard()
            running = True
            turn = WHITE
            game_start_time = time.time()
            game_end_time = None

            phase = "EARLY"
            print(f"GAME PHASE: {phase}")

            white_last_piece_moves = 0
            black_last_piece_moves = 0

            white_win = "1/2"
            black_win = "1/2"

            try:
                while running:

                    if len(chess_board.players[turn].possible_moves) == 0:
                        if chess_board.players[turn].checked:
                            running = False
                            game_end_time = time.time()
                            if turn != WHITE:
                                white_win = "1"
                                black_win = "0"
                            elif turn == WHITE:
                                white_win = "0"
                                black_win = "1"
                        else:
                            running = False
                            game_end_time = time.time()
                            white_win = "1/2"
                            black_win = "1/2"
                    elif black_last_piece_moves >= 20 or white_last_piece_moves >= 20:
                        running = False
                        game_end_time = time.time()
                        white_win = "1/2"
                        black_win = "1/2"

                    else:
                        move = best_move(chess_board, turn, depth=depth, debug=debug, time_budget=90)

                        if move is None:
                            # Treat this as a terminal/search failure instead of silently skipping the turn
                            print(f"ERROR: best_move returned None for {COLOR[turn]}")
                            print(f"Legal moves were: {chess_board.players[turn].possible_moves}")
                            print(f"Player {COLOR[turn]}    checked: {chess_board.players[turn].checked}    mated: {len(chess_board.players[turn].mated)}")
                            running = False
                            game_end_time = time.time()

                        if move:
                            from_sq, to_sq = move
                            piece = next(p for p in chess_board.players[turn].pieces 
                                        if p.location == from_sq)
                            chess_board._move_piece(piece, to_sq)
                            chess_board._update_tiles()
                            print(chess_board.actions[-1])

                            if len(chess_board.actions) > 40:
                                if chess_board.players[turn].actions[-1].piece_id == chess_board.players[turn].actions[-2].piece_id:
                                    if turn == WHITE:
                                        white_last_piece_moves += 1
                                    elif turn == BLACK:
                                        black_last_piece_moves += 1

                            if chess_board.actions[-1].captured != None:
                                current_phase = game_phase(chess_board)
                                if phase != current_phase:
                                    phase = current_phase
                                    print(f"GAME PHASE: {phase}")

                    turn = BLACK if turn == WHITE else WHITE

            except Exception as game_err:
                print(f"[ERROR] Game {game} crashed during play: {game_err}")
                game_end_time = game_end_time or time.time()
                continue

            game_time = fmt_time(game_end_time - game_start_time)
            num_moves = len(chess_board.actions)
            total_moves += num_moves
            num_castles = 0
            for action in chess_board.actions:
                if action.castle != None:
                    num_castles+=1
            total_castles+=num_castles
            num_promo = 0
            for action in chess_board.actions:
                if action.promotion != None:
                    num_promo+=1
            total_promotions+=num_promo

            if white_win != "1/2":
                if white_win == "1":
                    white_wins += 1
                if black_win == "1":
                    black_wins += 1

            result = f"{white_win}-{black_win}"

            print(f"GAME {game} COMPLETE\nRESULT: {result}\nTIME: {game_time}\nNUMBER OF MOVES: {num_moves}\nNUMBER OF CASTLES: {num_castles}\nNUMBER OF PROMOTIONS: {num_promo}")

            # Load PGN
            path = export_game_to_pgn(chess_board, output_path=f"data/bot_games/{MODEL_NAME}/{depth}", model_path=MODEL_PATH, result=f"{white_win}-{black_win}")
            print(f"Saved PGN to: {path}")


        end_time = time.time()
        total_time = fmt_time(end_time - start_time)
        avg_time = fmt_time((end_time - start_time)/games)
        avg_num_moves = total_moves/(game+1)

        print(f"{games} GAME EVAL COMPLETE\nWINS:  WHITE: {white_wins}  BLACK: {black_wins}  \nTIME: {total_time}  AVG GAME TIME {avg_time}  \nNUMBER OF MOVES: {num_moves} AVERAGE NUMBER OF MOVES: {avg_num_moves}  \nNUMBER OF CASTLES: {total_castles}   NUMBER OF PROMOTIONS: {total_promotions}")
    
    except ValueError as e:
        print(f"Input parse failed:\n{e}")
    except Exception as e:
        print(f"Game generation failed:\n{e}")

if __name__ == '__main__':
    main()