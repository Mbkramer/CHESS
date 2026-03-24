import os
import time
from opening_book import choose_book_move, book_move_bonus

try:
    import torch
except Exception:
    torch = None

try:
    from model import load_model
    from tensor import board_to_tensor
except Exception:
    load_model = None
    board_to_tensor = None

MODEL_PATH = os.environ.get("CHESS_MODEL_PATH", "check_points/pgn_2000_2400_v4.pt")

model = None
if load_model is not None and os.path.exists(MODEL_PATH):
    try:
        model = load_model(MODEL_PATH)
        model.eval()
        print(f"Bot model loaded from {MODEL_PATH}")
    except Exception as e:
        print(f"Warning: failed to load bot model from {MODEL_PATH}: {e}")
        model = None

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

def export_game_to_pgn(chess_board, model_path: str, result: str = "*"):
    """
    Converts your engine's action log into a valid PGN file
    and saves it under data/bot_games/<model_name>/.

    result:
        "1-0", "0-1", "1/2-1/2", or "*"
    """

    if chess is None:
        raise RuntimeError("python-chess is required for PGN export")

    board = chess.Board()
    game = chess.pgn.Game()

    # --- Headers ---
    model_name = os.path.basename(model_path).replace(".pt", "")

    game.headers["Event"] = "Bot Self-Play"
    game.headers["Site"] = "Local"
    game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
    game.headers["White"] = model_name
    game.headers["Black"] = model_name
    game.headers["Result"] = result

    node = game

    # --- Replay moves ---
    for action in chess_board.actions:

        move_uci = action.from_tile + action.to_tile

        # Handle promotion
        if action.promotion:
            move_uci += action.promotion.lower()

        move = chess.Move.from_uci(move_uci)

        if move not in board.legal_moves:
            raise ValueError(f"Illegal move during PGN export: {move_uci}")

        board.push(move)
        node = node.add_variation(move)

    # --- Final result ---
    game.headers["Result"] = result

    # --- Build output path ---
    save_dir = os.path.join("data", "bot_games", model_name)
    os.makedirs(save_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"game_{timestamp}.pgn"
    filepath = os.path.join(save_dir, filename)

    # --- Write PGN ---
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
    return f"{x:.4f}"   # was .2f — use 4 decimal places

def _search_log(msg: str):
    if DEBUG_SEARCH:
        print(msg)

# ── Piece-Square Tables ───────────────────────────────────────────────────────
# Each table is 64 values, index 0 = a1, index 63 = h8 (white's perspective)
# Values are fractional to keep them below material value thresholds
# Black's tables are mirrored automatically in get_position_bonus()

PAWN_TABLE = [
    0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,
    0.5,  0.5,  0.5,  0.5,  0.5,  0.5,  0.5,  0.5,
    0.1,  0.1,  0.2,  0.3,  0.3,  0.2,  0.1,  0.1,
    0.05, 0.05, 0.1,  0.25, 0.25, 0.1,  0.05, 0.05,
    0.0,  0.0,  0.0,  0.2,  0.2,  0.0,  0.0,  0.0,
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
    -0.1,  0.05, 0.05, 0.1,  0.1,  0.05, 0.05,-0.1,
    -0.1,  0.0,  0.1,  0.1,  0.1,  0.1,  0.0, -0.1,
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
    -0.3, -0.4, -0.4, -0.5, -0.5, -0.4, -0.4, -0.3,
    -0.3, -0.4, -0.4, -0.5, -0.5, -0.4, -0.4, -0.3,
    -0.3, -0.4, -0.4, -0.5, -0.5, -0.4, -0.4, -0.3,
    -0.3, -0.4, -0.4, -0.5, -0.5, -0.4, -0.4, -0.3,
    -0.2, -0.3, -0.3, -0.4, -0.4, -0.3, -0.3, -0.2,
    -0.1, -0.2, -0.2, -0.2, -0.2, -0.2, -0.2, -0.1,
    0.15, 0.20, 0.05, -0.05, -0.05, 0.05, 0.20, 0.15,
    0.20, 0.35, 0.15, -0.10, -0.10, 0.15, 0.35, 0.20,
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
    doubled_pawn_penalty:   float = 0.30
    isolated_pawn_penalty:  float = 0.35
    connected_pawn_bonus:   float = 0.10
    passed_pawn_base:       float = 0.15
    passed_pawn_advance:    float = 0.10

    # ── Mobility ──
    mobility_weight: float = 0.05

    # ── King safety ──
    castle_bonus:          float = 0.75
    pawn_shield_bonus:     float = 0.15
    open_file_penalty:     float = 0.25
    semi_open_file_penalty: float = 0.10
    attacker_proximity_weight: float = 0.15

    # ── Piece bonuses ──
    bishop_pair_bonus:       float = 0.30
    rook_open_file_bonus:    float = 0.25
    rook_semi_open_bonus:    float = 0.10

    # ── Hanging pieces ──
    hanging_outnumbered_weight: float = 0.18
    hanging_undefended_weight:  float = 0.10

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
        return row * 8 + col        # rank 1 row=0 → index 0..7
    else:
        return (7 - row) * 8 + col  # rank 8 row=7 → index 0..7 (mirrored)


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

# ── Evaluation ────────────────────────────────────────────────────────────────

MATE_SCORE = 100000


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
            score -= 0.35

        # ── Connected pawn bonus ──────────────────────────────────────────
        # A pawn is "connected" if a friendly pawn guards it (diagonally adjacent)
        if left_file and left_file in my_files:
            left_pawns = [p for p in my_pawns if p.location[0] == left_file]
            if any(abs(int(p.location[1]) - row) == 1 for p in left_pawns):
                score += 0.1
        if right_file and right_file in my_files:
            right_pawns = [p for p in my_pawns if p.location[0] == right_file]
            if any(abs(int(p.location[1]) - row) == 1 for p in right_pawns):
                score += 0.1

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
            score += 0.15 + 0.1 * advancement

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
    row = 1 if color == WHITE else 8

    piece = chess_board._get_tile(f"d{row}").piece
    if piece is not None and piece.name == 'R' and piece.color == color and king.location == f"c{row}":
        score += .75

    piece = chess_board._get_tile(f"f{row}").piece
    if piece is not None and piece.name == 'R' and piece.color == color and king.location == f"g{row}":
        score += .75


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
            score += 0.15

    # ── Open file penalty ─────────────────────────────────────────────────
    all_pawn_files = {
        p.location[0]
        for side in (WHITE, BLACK)
        for p in chess_board.players[side].pieces
        if p.name == 'P'
    }
    for f in shield_files:
        if f not in all_pawn_files:          # fully open file near king
            score -= 0.25
        elif f not in {p.location[0] for p in chess_board.players[color].pieces if p.name == 'P'}:
            score -= 0.1                     # semi-open (opponent pawn only)

    # ── Enemy attacker proximity ──────────────────────────────────────────
    for piece in chess_board.players[opponent].pieces:
        if piece.name in ('K', 'P'):
            continue
        opp_col = COLUMNS.index(piece.location[0])
        opp_row = int(piece.location[1])
        dist = max(abs(opp_col - king_col_idx), abs(opp_row - king_row))
        if dist <= 2:
            score -= 0.15 * PIECE_VALUES[piece.name] / 5.0

    return score


def _bishop_pair(chess_board, color) -> float:
    bishops = [p for p in chess_board.players[color].pieces if p.name == 'B']
    return 0.3 if len(bishops) >= 2 else 0.0


def _rook_on_open_file(chess_board, color) -> float:
    """Bonus for rooks on open or semi-open files."""
    score = 0.0
    all_pawn_files = {
        p.location[0]
        for side in (WHITE, BLACK)
        for p in chess_board.players[side].pieces
        if p.name == 'P'
    }
    friendly_pawn_files = {
        p.location[0] for p in chess_board.players[color].pieces if p.name == 'P'
    }
    for piece in chess_board.players[color].pieces:
        if piece.name != 'R':
            continue
        f = piece.location[0]
        if f not in all_pawn_files:
            score += 0.25       # fully open file
        elif f not in friendly_pawn_files:
            score += 0.1        # semi-open (no friendly pawn)
    return score


# --- Search depth handling ----------------------------------------------

def _square_pressure(board, square: str, color: str) -> tuple[int, int]:
    """Return (attackers, defenders) for `color` pieces if moved to `square`."""
    opp = BLACK if color == WHITE else WHITE
    attackers = 0
    defenders = 0

    for piece in board.players[opp].pieces:
        if square in piece.moves:
            attackers += 1

    for piece in board.players[color].pieces:
        if square in piece.moves:
            defenders += 1

    return attackers, defenders

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


def _hanging_pieces(chess_board, color: str) -> float:
    """Penalty for loose/hanging pieces from color perspective."""
    score = 0.0
    for piece in chess_board.players[color].pieces:
        if piece.name == "K":
            continue
        attackers, defenders = _square_pressure(chess_board, piece.location, color)
        if attackers == 0:
            continue

        piece_weight = PIECE_VALUES[piece.name]
        if attackers > defenders:
            score -= 0.18 * piece_weight
        elif defenders == 0:
            score -= 0.1 * piece_weight
    return score


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
            if dfn >= atk:
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

# --- Evaluatations -----------------------------------------------------------

def evaluate_terminal(chess_board, turn: str, root_color: str, depth: int, repertoire_name="balanced"):
    # Don't score moves — just count them
    has_moves = any(
        True
        for piece in chess_board.players[turn].pieces
        for move in piece.moves
        if not (chess_board._get_tile(move) and
                chess_board._get_tile(move).piece and
                chess_board._get_tile(move).piece.name == "K")
    )
    in_check = chess_board.players[turn].checked

    if not has_moves:
        if in_check:
            return -MATE_SCORE + depth if turn == root_color else MATE_SCORE - depth
        return 0.0
    return None

def evaluate(chess_board, color, p=None) -> float:

    if p is None:
        p = EVAL_PARAMS

    model_score = 0.0
    if model is not None and torch is not None and board_to_tensor is not None:
        tensor = board_to_tensor(chess_board, turn=color)
        x = torch.tensor(tensor).unsqueeze(0).float()
        with torch.no_grad():
            model_score = model(x).item()

    classical = 0.0
    for piece in chess_board.players[WHITE].pieces:
        # Fixed — passes p through so tuner candidate params are actually used:
        classical += _piece_value(piece.name, p) + get_position_bonus(piece, p)
    for piece in chess_board.players[BLACK].pieces:
        classical -= _piece_value(piece.name, p) + get_position_bonus(piece, p)

    classical += _pawn_structure(chess_board, WHITE)
    classical -= _pawn_structure(chess_board, BLACK)

    classical += _mobility(chess_board)

    classical += _king_safety(chess_board, WHITE)
    classical -= _king_safety(chess_board, BLACK)

    classical += _bishop_pair(chess_board, WHITE)
    classical -= _bishop_pair(chess_board, BLACK)

    classical += _rook_on_open_file(chess_board, WHITE)
    classical -= _rook_on_open_file(chess_board, BLACK)

    classical += _hanging_pieces(chess_board, WHITE)
    classical -= _hanging_pieces(chess_board, BLACK)

    classical += _development_score(chess_board, WHITE)
    classical -= _development_score(chess_board, BLACK)

    # Phase Signals

    phase = game_phase(chess_board)

    model_scaled = model_score * 5

    # Clamp model influence (important)
    model_scaled = max(min(model_scaled, 3), -3)

    # Phase weights — model is strongest early (trained on human openings, suppresses
    # positional blunders), tapers as game becomes tactical (classical eval more reliable).
    # Also use ply count for a sharper early-game boost independent of piece count.
    ply_count = len(getattr(chess_board, "actions", []))
    if ply_count <= 10:
        # Deep opening: model has strongest signal, classical can misread piece activity
        model_weight = 0.35
    elif phase == EARLY:
        model_weight = 0.25
    elif phase == MIDDLE:
        model_weight = 0.15
    else:  # LATE
        model_weight = 0.08

    classical_weight = 1 - model_weight

    score = model_weight * model_scaled + classical_weight * classical

    return score if color == WHITE else -score

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

        # Raw move generation is enough for attack maps
        board.players[mover].update_moves(board, board.players[opp].actions)
        board.players[opp].update_moves(board, board.players[mover].actions)

        return board._test_check(opp)

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

def _is_quiet_backtrack(board, piece, move: str) -> bool:
    """
    Penalize a side moving the same piece straight back to the square
    it came from on its previous turn.

    Example:
      White: Bc3 -> d2
      ...
      White: Bd2 -> c3   <-- penalize
    """
    actions = getattr(board, "actions", [])
    if len(actions) < 2:
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

    # only penalize quiet shuffles
    if is_capture or is_promotion or is_castle:
        return False

    # same side's previous move is 2 plies ago
    prev_own_action = actions[-2]

    return (
        getattr(prev_own_action, "piece_id", None) == piece.id and
        getattr(prev_own_action, "to_tile", None) == piece.location and
        getattr(prev_own_action, "from_tile", None) == move
    )


def _see(board, square: str, color: str) -> float:
    """
    Static Exchange Evaluation (SEE).

    Simulates the full capture sequence on `square` assuming `color` is
    the side that just moved a piece there, and returns the net material
    gain (positive = profitable for `color`, negative = losing).

    Uses the cheapest-attacker heuristic: each side always recaptures
    with its least valuable piece.  This is an approximation — it ignores
    pins and discovered attacks — but it is fast (no board simulation) and
    accurate enough to filter clearly losing moves at order time.

    Example: White bishop moves to d2, Black queen on a5 can take for free.
      _see(board, 'd2', WHITE) → roughly -3  (White loses a bishop)
    """
    opp = BLACK if color == WHITE else WHITE

    # Value of the piece that just arrived on `square`
    tile = board._get_tile(square)
    if tile is None or tile.piece is None:
        return 0.0
    target_val = PIECE_VALUES[tile.piece.name]

    # Find the cheapest opponent attacker
    cheapest_val = float('inf')
    for p in board.players[opp].pieces:
        if square in p.moves and p.name != 'K':
            val = PIECE_VALUES[p.name]
            if val < cheapest_val:
                cheapest_val = val

    if cheapest_val == float('inf'):
        # Nobody can take — square is safe
        return 0.0

    # Opponent captures: they gain `target_val`, then we recapture
    # Find our cheapest recapture after the exchange
    recapture_val = float('inf')
    for p in board.players[color].pieces:
        if p.location != square and square in p.moves and p.name != 'K':
            val = PIECE_VALUES[p.name]
            if val < recapture_val:
                recapture_val = val

    if recapture_val == float('inf'):
        # Opponent takes for free — pure loss of target piece
        return -target_val

    # Opponent gains target_val, we recapture gaining cheapest_val,
    # net from color's perspective: we lose target, gain back cheapest_attacker
    # (simplified one-recapture SEE — accurate for the common cases)
    return cheapest_val - target_val


def _passes_opening_sanity(board, piece, move: str) -> bool:
    """Reject legal moves that are positionally/safety suspect."""
    target_tile = board._get_tile(move)
    is_capture = (
        target_tile is not None and
        target_tile.piece is not None and
        target_tile.piece.color != piece.color
    )

    in_opening = _opening_phase(board)

    if in_opening:
        # Avoid early flank pawn pushes unless tactical.
        if piece.name == "P" and move[0] in ("a", "h") and len(getattr(board, "actions", [])) <= 8 and not is_capture:
            return False

        # Avoid early queen wandering unless tactical.
        if piece.name == "Q" and len(getattr(board, "actions", [])) <= 8 and not is_capture:
            return False

    # --- SEE filter: reject any move that drops material for free ---
    # Simulate placing the piece on the target square, then run SEE.
    # We check this always (not just opening) since walking into a free
    # capture is never correct regardless of phase.
    if not is_capture:
        # For quiet moves: temporarily place piece on target, check SEE
        snap = board._snapshot_state()
        try:
            board._move_piece(piece, move, simulate=True)
            board._sync_board()
            see_score = _see(board, move, piece.color)
        except Exception:
            see_score = 0.0
        finally:
            board._restore_state(snap)

        # Reject if clearly losing (losing more than a pawn's worth for free)
        if see_score < -1.0:
            return False

    if in_opening:
        # Avoid moving into obvious pressure without compensation (count-based fallback).
        to_attackers, to_defenders = _square_pressure(board, move, piece.color)
        if to_attackers > to_defenders + 1 and not is_capture:
            return False

    return True

def move_order_score(board, piece, move, color=None, repertoire_name="balanced"):
    score = 0.0
    target_tile = board._get_tile(move)

    # 1. Captures: strong MVV-LVA
    if target_tile and target_tile.piece and target_tile.piece.color != piece.color:
        victim = target_tile.piece
        attacker_val = PIECE_VALUES[piece.name]
        victim_val = PIECE_VALUES[victim.name]

        # Stronger separation than your current formula
        score += 2 * victim_val - attacker_val

        # Prefer clearly favorable captures even more
        if victim_val > attacker_val:
            score += 3.0
        elif victim_val == attacker_val:
            score += 1.0

    # 2. Promotions
    if piece.name == 'P' and ((piece.color == WHITE and move[1] == '8') or
                              (piece.color == BLACK and move[1] == '1')):
        score += 20.0

    # 3. Checks 
    if _could_plausibly_give_check(board, piece, move):
        score+=4

    # 4. If castle available prioritize
    if piece.color == WHITE and piece.name == "K":
        if piece.location == piece.starting_location and (move == "c1" or move == "g1"):
            score += 10.0
    elif piece.color == BLACK and piece.name == "K":
        if piece.location == piece.starting_location and (move == "c8" or move == "g8"):
            score += 10.0

    # 5. Center / development only early
    history_len = len(getattr(board, "actions", []))
    if history_len <= 12:
        center_bonus = {
            'd4': 0.8, 'e4': 0.8, 'd5': 0.8, 'e5': 0.8,
            'c3': 0.3, 'd3': 0.3, 'e3': 0.3, 'f3': 0.3,
            'c4': 0.3, 'f4': 0.3, 'c5': 0.3, 'f5': 0.3,
            'c6': 0.3, 'd6': 0.3, 'e6': 0.3, 'f6': 0.3,
        }
        score += center_bonus.get(move, 0.0)
        score += _early_opening_safety_bonus(board, piece, move)

    # 6. Book bonus only when relevant
    if color is not None and history_len <= 16:
        score += book_move_bonus(
            board, piece, move,
            color=color,
            repertoire_name=repertoire_name
        )

    # 7. Quiet backtrack penalty
    if _is_quiet_backtrack(board, piece, move):
        score -= 0.30

    # 8. SEE-based safety signal.
    # For quiet moves: simulate placing the piece on the target square and
    # run a one-recapture Static Exchange Evaluation.  A clearly losing
    # exchange gets a heavy penalty; a safe square gets a small bonus.
    # For captures: MVV-LVA already handles ordering, but penalise losing
    # captures (e.g. NxQ where the queen is defended) to push them below
    # safe moves.
    piece_val = PIECE_VALUES[piece.name]
    is_quiet = not (target_tile and target_tile.piece and target_tile.piece.color != piece.color)

    if is_quiet:
        snap = board._snapshot_state()
        try:
            board._move_piece(piece, move, simulate=True)
            board._sync_board()
            see_score = _see(board, move, piece.color)
        except Exception:
            see_score = 0.0
        finally:
            board._restore_state(snap)

        if see_score < -0.5:
            # Losing material for free — strong penalty scaled by loss magnitude
            score -= 3.0 + abs(see_score)
        elif see_score == 0.0:
            # Neutral exchange — small escape bonus if piece was already under attack
            from_attackers, from_defenders = _square_pressure(board, piece.location, piece.color)
            if from_attackers > from_defenders:
                score += 0.4
    else:
        # Capture: penalise if we're losing the exchange (e.g. BxN where N is defended by P)
        victim_val = PIECE_VALUES[target_tile.piece.name]
        if piece_val > victim_val:
            to_attackers, to_defenders = _square_pressure(board, move, piece.color)
            if to_attackers > 0:
                # We're capturing with a more valuable piece into a defended square
                score -= 1.5 * (piece_val - victim_val)

    return score


def _quiescence(chess_board, alpha: float, beta: float, root_color: str,
                turn: str, depth: int = 4, deadline: float = None) -> float:
    """
    Internal quiescence worker with explicit turn tracking.
    """
    if deadline is not None and time.time() >= deadline:
        return evaluate(chess_board, root_color)

    maximizing = (turn == root_color)
    next_turn = BLACK if turn == WHITE else WHITE

    stand_pat = evaluate(chess_board, root_color)

    DELTA = 9.5

    if maximizing:
        if stand_pat >= beta:
            return stand_pat
        if stand_pat < alpha - DELTA:
            return stand_pat
        alpha = max(alpha, stand_pat)
    else:
        if stand_pat <= alpha:
            return stand_pat
        if stand_pat > beta + DELTA:
            return stand_pat
        beta = min(beta, stand_pat)

    if depth == 0:
        return stand_pat

    # Collect captures only (skip king-capture moves)
    captures = []
    for piece in chess_board.players[turn].pieces:
        for move in piece.moves:
            target_tile = chess_board._get_tile(move)
            if target_tile and target_tile.piece and target_tile.piece.color != piece.color:
                if target_tile.piece.name == "K":
                    continue
                victim_val = PIECE_VALUES[target_tile.piece.name]
                attacker_val = PIECE_VALUES[piece.name]
                # MVV-LVA score: prefer capturing high-value pieces with low-value attackers
                order = victim_val * 10 - attacker_val
                captures.append((piece, move, order))

    if not captures:
        return stand_pat

    captures.sort(key=lambda x: x[2], reverse=True)

    best = stand_pat
    for piece, move, _ in captures[:8]:  # cap at 8 captures per node
        snap = chess_board._snapshot_state()
        try:
            chess_board._move_piece(piece, move, simulate=True)
            chess_board._refresh_search_state_for_turn(next_turn)

            score = _quiescence(chess_board, alpha, beta, root_color, next_turn, depth - 1, deadline)
        except ValueError as e:
            if "kings cannot be captured" in str(e):
                chess_board._restore_state(snap)
                continue
            chess_board._restore_state(snap)
            raise
        finally:
            chess_board._restore_state(snap)

        if maximizing:
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        else:
            if score < best:
                best = score
            if score < beta:
                beta = score
            if beta <= alpha:
                break

    return best


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

    maximizing = (turn == root_color)
    role = "MAX" if maximizing else "MIN"
    next_turn = BLACK if turn == WHITE else WHITE

    if deadline is not None and time.time() >= deadline:
        return evaluate(chess_board, root_color)

    # 1. TERMINAL CHECK — FIRST
    terminal = evaluate_terminal(chess_board, turn, root_color, depth)
    if terminal is not None:
        if debug >= 2:
            _debug_log(debug, ply, f"{role} {COLOR[turn]} terminal => {_fmt_score(terminal)}")
        return terminal

    # 2. DEPTH LIMIT — run quiescence search instead of raw static eval
    if depth == 0:
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
            if target_tile and target_tile.piece and target_tile.piece.name == "K":
                continue

            order_score = move_order_score(
                chess_board,
                piece,
                move,
                color=turn,
                repertoire_name=repertoire_name
            )
            all_moves.append((piece, move, order_score))

    all_moves.sort(key=lambda pm: pm[2], reverse=True)
    history_len = len(getattr(chess_board, "actions", []))
    total_pieces = len(chess_board.players[WHITE].pieces) + len(chess_board.players[BLACK].pieces)

    candidate_cap = len(all_moves)

    # widen in tactical / endgame spots
    if chess_board.players[turn].checked:
        candidate_cap = min(candidate_cap, 20)

    # depth-based cap: deeper = narrower, shallower = wider
    if depth >= 4:
        candidate_cap = min(candidate_cap, 14 if history_len > 10 else 16)  # was 8/10
    elif depth == 3:
        candidate_cap = min(candidate_cap, 16 if history_len > 10 else 18)  # was 10/12
    elif depth == 2:
        candidate_cap = min(candidate_cap, 14)
    else:
        candidate_cap = min(candidate_cap, 18)

    # widen in endgames
    if total_pieces <= 10:
        candidate_cap = max(candidate_cap, min(len(all_moves), 18))

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
            
            # If moving side's king is now in check, this was an illegal move. Skip it.
            chess_board._sync_board()
            if chess_board._test_check(turn):   # turn = the side that just moved
                chess_board._restore_state(snap)
                continue

            chess_board._refresh_search_state_for_turn(WHITE)
            chess_board._refresh_search_state_for_turn(BLACK)

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
            if will_show:
                _debug_log(
                    debug,
                    ply + 2,
                    f"PRUNE alpha={_fmt_score(alpha)} beta={_fmt_score(beta)}"
                )
            break

    if debug >= 2:
        _debug_log(debug, ply, f"{role} {COLOR[turn]} returns {_fmt_score(best)}")

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
        if target_tile and target_tile.piece and target_tile.piece.name == "K":
            continue

        order_score = move_order_score(
            chess_board,
            piece,
            move,
            color=color,
            repertoire_name=repertoire_name
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
    root_cap = 18
    if chess_board.players[color].checked:
        root_cap = 22
    elif root_tactical:
        root_cap = 20
    elif history_len > 10:
        root_cap = 16
    else:
        root_cap = 14

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
            opp_moves = _search_legal_moves(chess_board, next_turn, repertoire_name=repertoire_name)
            if len(opp_moves) == 0 and chess_board.players[next_turn].checked:
                if debug >= 1:
                    _debug_log(debug, 2 if debug >= 2 else 1, "immediate mate found")
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
                float('-inf'),   # fresh window per root move
                float('inf'),
                repertoire_name=repertoire_name,
                ply=2,
                debug=debug,
                debug_max_children=debug_max_children,
                deadline=deadline
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
                _debug_log(debug, 2 if debug >= 2 else 1, f"ROOT new best => {chosen} score={_fmt_score(best_score)}")

        if deadline is not None and time.time() >= deadline:
            return chosen or fallback

        alpha = max(alpha, best_score)

    if chosen is not None and debug >= 1:
        chosen_piece = chess_board._get_tile(chosen[0]).piece
        piece_name = chosen_piece.name if chosen_piece else "?"
        _debug_log(
            debug,
            0,
            f"CHOSEN {COLOR[color]}: {piece_name} {chosen[0]}->{chosen[1]} score={_fmt_score(best_score)}"
        )

    return chosen


"""
Run x number of self play games and print outcomes
"""

def main():
    from chess_board import ChessBoard
    import time

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
        total_castles = 0
        total_promotions = 0
        white_wins = 0
        black_wins = 0

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

            while running:

                if len(chess_board.players[turn].possible_moves) == 0:
                    if chess_board.players[turn].checked:
                        running = False
                        game_end_time = time.time()
                        if turn != WHITE:
                            white_win = 1
                            black_win = 0
                            white_wins+=1
                        elif turn == WHITE:
                            white_win = 0
                            black_win = 1
                            black_wins+=1
                    else:
                        running = False
                        game_end_time = time.time()
                        white_win = 1/2
                        black_win = 1/2

                else:
                    move = best_move(chess_board, turn, depth=depth, debug=debug, time_budget=120)
                    if move:
                        from_sq, to_sq = move
                        piece = next(p for p in chess_board.players[turn].pieces 
                                    if p.location == from_sq)
                        chess_board._move_piece(piece, to_sq)
                        chess_board._update_tiles()
                        print(chess_board.actions[-1])
                        if chess_board.actions[-1].captured != None:
                            current_phase = game_phase(chess_board)
                            if phase != current_phase:
                                phase = current_phase
                                print(f"GAME PHASE: {phase}")

                turn = BLACK if turn == WHITE else WHITE

            game_time = fmt_time(game_end_time - game_start_time)
            num_moves = len(chess_board.actions)
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

            print(f"GAME {game} COMPLETE, {COLOR[turn]} WINS: TIME: {game_time}  NUMBER OF MOVES: {num_moves}  NUMBER OF CASTLES: {num_castles}  NUMBER OF PROMOTIONS: {num_promo}")

            # Load PGN
            path = export_game_to_pgn(chess_board, model_path=MODEL_PATH, result=f"{white_win}-{black_win}")
            print(f"Saved PGN to: {path}")


        end_time = time.time()
        total_time = fmt_time(end_time - start_time)
        avg_time = fmt_time((end_time - start_time)/games)
        avg_num_moves = avg_num_moves/games

        print(f"{games} GAMES EVAL COMPLETE, {COLOR[turn]}  WINS:  WHITE: {white_wins}  BLACK{black_wins}  TIME: {total_time}  AVG GAME TIME {avg_time}  NUMBER OF MOVES: {num_moves} AVERAGE NUMBER OF MOVES: {avg_num_moves}  NUMBER OF CASTLES: {num_castles}   NUMBER OF PROMOTIONS: {num_promo}")
    
    except Exception as e:
        print(f"NOT INT FAILE TO GENERATE GAMES:\n{e}")

if __name__ == '__main__':
    main()