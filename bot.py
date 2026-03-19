import os
import torch
import time
from model import load_model
from tensor import board_to_tensor
from opening_book import choose_book_move, book_move_bonus

# for now use generic path
from model import load_model

MODEL_PATH = os.environ.get("CHESS_MODEL_PATH", "check_points/best_pgn_v2.pt")

model = None
if os.path.exists(MODEL_PATH):
    try:
        model = load_model(MODEL_PATH)
        print(f"Bot model loaded from {MODEL_PATH}")
    except Exception as e:
        print(f"Warning: failed to load bot model from {MODEL_PATH}: {e}")
        model = None

WHITE = 'W'
BLACK = 'B'

COLOR = {"W": "White", "B": "Black"}

PIECE_VALUES = {'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 0}

MAX_BOOK_PLIES = 12

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
    if x == float("inf"):
        return "inf"
    if x == float("-inf"):
        return "-inf"
    return f"{x:.2f}"

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
     0.2,  0.2,  0.0,  0.0,  0.0,  0.0,  0.2,  0.2,
     0.2,  0.3,  0.1,  0.0,  0.0,  0.1,  0.3,  0.2,
]

PIECE_TABLES = {
    'P': PAWN_TABLE,
    'N': KNIGHT_TABLE,
    'B': BISHOP_TABLE,
    'R': ROOK_TABLE,
    'Q': QUEEN_TABLE,
    'K': KING_TABLE,
}

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


def get_position_bonus(piece) -> float:
    table = PIECE_TABLES.get(piece.name)
    if table is None:
        return 0.0
    return table[_square_index(piece.location, piece.color)]

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
            score -= 0.3

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


def evaluate_terminal(chess_board, turn: str, root_color: str, depth: int):
    legal_moves = chess_board.players[turn].possible_moves
    in_check = chess_board.players[turn].checked

    if len(legal_moves) == 0:
        if in_check:
            return -MATE_SCORE + depth if turn == root_color else MATE_SCORE - depth
        return 0.0

    return None

def _should_extend(piece, move, chess_board):
    target_tile = chess_board._get_tile(move)
    is_capture = target_tile and target_tile.piece and target_tile.piece.color != piece.color

    if is_capture:
        victim = target_tile.piece.name

    return is_capture and PIECE_VALUES[victim] >= PIECE_VALUES[piece.name]

def _adjusted_depth(base_depth, num_moves, total_pieces):
    d = base_depth

    if num_moves <= 8:
        d += 1
    elif total_pieces <= 16:
        d += 1

    return min(d, base_depth + 1)

def _opening_candidate_cap(board, default_cap: int) -> int:
    history_len = len(getattr(board, "actions", []))
    if history_len <= 8:
        return max(default_cap, 16)  # do not strangle development choices
    return default_cap

def evaluate(chess_board, color) -> float:

    model_score = 0.0
    if model is not None:
        tensor = board_to_tensor(chess_board)
        x = torch.tensor(tensor).unsqueeze(0).float()
        with torch.no_grad():
            model_score = model(x).item()

    classical = 0.0
    for piece in chess_board.players[WHITE].pieces:
        classical += PIECE_VALUES[piece.name] + get_position_bonus(piece)
    for piece in chess_board.players[BLACK].pieces:
        classical -= PIECE_VALUES[piece.name] + get_position_bonus(piece)

    classical += _pawn_structure(chess_board, WHITE)
    classical -= _pawn_structure(chess_board, BLACK)

    classical += _mobility(chess_board)

    classical += _king_safety(chess_board, WHITE)
    classical -= _king_safety(chess_board, BLACK)

    classical += _bishop_pair(chess_board, WHITE)
    classical -= _bishop_pair(chess_board, BLACK)

    classical += _rook_on_open_file(chess_board, WHITE)
    classical -= _rook_on_open_file(chess_board, BLACK)

    score = 0.4 * model_score + 0.6 * classical

    return score if color == WHITE else -score

# ── Minimax with Alpha-Beta Pruning ───────────────────────────────────────────
# alpha = best score the maximizing player is guaranteed so far
# beta  = best score the minimizing player is guaranteed so far
# If beta <= alpha we can stop searching this branch — the opponent
# already has a better option elsewhere and will never allow this line

def _opening_phase(board) -> bool:
    return len(getattr(board, "actions", [])) <= 10  # first 5 moves each side


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


def move_order_score(board, piece, move, color=None, repertoire_name="balanced"):
    score = 0.0
    target_tile = board._get_tile(move)

    # 1. Captures: strong MVV-LVA
    if target_tile and target_tile.piece and target_tile.piece.color != piece.color:
        victim = target_tile.piece
        attacker_val = PIECE_VALUES[piece.name]
        victim_val = PIECE_VALUES[victim.name]

        # Stronger separation than your current formula
        score += 10.0 * victim_val - attacker_val

        # Prefer clearly favorable captures even more
        if victim_val > attacker_val:
            score += 3.0
        elif victim_val == attacker_val:
            score += 1.0

    # 2. Promotions
    if piece.name == 'P' and ((piece.color == WHITE and move[1] == '8') or
                              (piece.color == BLACK and move[1] == '1')):
        score += 20.0

    # 3. Center / development only early
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

    # 4. Book bonus only when relevant
    if color is not None and history_len <= 16:
        score += book_move_bonus(
            board, piece, move,
            color=color,
            repertoire_name=repertoire_name
        )

    return score


def minimax(chess_board, depth: int, turn: str, root_color: str,
            alpha=float('-inf'), beta=float('inf'),
            repertoire_name="balanced",
            ply: int = 0,
            debug: int = 0,
            debug_max_children: int | None = None,
            deadline=None) -> float:
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

    # 2. DEPTH LIMIT
    if depth == 0:
        score = evaluate(chess_board, root_color)
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

    if depth >= 2:
        all_moves = all_moves[:_opening_candidate_cap(chess_board, 8)]

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

    shown_moves = all_moves
    if debug >= 2 and debug_max_children is not None:
        shown_moves = all_moves[:debug_max_children]

    if len(shown_moves) > 20:
        shown_moves = shown_moves[:12]

    best = float('-inf') if maximizing else float('inf')

    for idx, (piece, move, order_score) in enumerate(shown_moves):
        is_last = (idx == len(shown_moves) - 1)
        from_sq = piece.location

        if debug >= 2:
            _debug_log(
                debug,
                ply + 1,
                f"{piece.name} {from_sq}->{move} order={order_score:.2f}",
                is_last=is_last
            )

        snap = chess_board._snapshot_state()

        try:
            is_forcing = _should_extend(piece, move, chess_board)

            chess_board._move_piece(piece, move, simulate=True)
            chess_board._refresh_search_state_for_turn(next_turn)

            if chess_board.players[next_turn].checked:
                is_forcing = True

            extension = 1 if (depth == 1 and is_forcing) else 0

            if debug >= 2 and extension:
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
                deadline=None
            )

            if debug >= 2:
                _debug_log(debug, ply + 2, f"result => {_fmt_score(score)}")

        except ValueError as e:
            if "kings cannot be captured" in str(e):
                if debug >= 2:
                    _debug_log(debug, ply + 2, "skipped illegal king-capture branch")
                continue
            raise
        finally:
            chess_board._restore_state(snap)

        if maximizing:
            if score > best:
                best = score
                if debug >= 2:
                    _debug_log(debug, ply + 2, f"new best MAX => {_fmt_score(best)}")
            alpha = max(alpha, best)
        else:
            if score < best:
                best = score
                if debug >= 2:
                    _debug_log(debug, ply + 2, f"new best MIN => {_fmt_score(best)}")
            beta = min(beta, best)

        if beta <= alpha:
            if debug >= 2:
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
        book_choice = choose_book_move(chess_board, color, repertoire_name=repertoire_name)
        if book_choice is not None:
            from_sq, to_sq, meta = book_choice
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

    for piece in chess_board.players[color].pieces:
        for move in list(piece.moves):
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
    search_depth = _adjusted_depth(depth, num_moves, total_pieces)

    candidate_moves.sort(key=lambda pm: pm[2], reverse=True)
    candidate_moves = candidate_moves[:10]

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
            if len(chess_board.players[next_turn].possible_moves) == 0 and chess_board.players[next_turn].checked:
                if debug >= 1:
                    _debug_log(debug, 2 if debug >= 2 else 1, "immediate mate found")
                return (from_sq, move)
            
            if fallback is None:
                fallback = (piece.location, move)

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