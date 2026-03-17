import os
import torch
from model import load_model
from tensor import board_to_tensor
from opening_book import choose_book_move, book_move_bonus

# for now use generic path
MODEL_PATH = "check_points/chess_model.pt"

model = None
if os.path.exists(MODEL_PATH):
    try:
        model = load_model(MODEL_PATH)
    except Exception:
        model = None

WHITE = 'W'
BLACK = 'B'

PIECE_VALUES = {'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 0}
CENTI_PAWNS = {'P': 100, 'N': 300, 'B': 325, 'R': 500, 'Q': 900, 'K': float('inf')}

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


def _pawn_structure(board, color) -> float:
    """
    Returns a score (from color's perspective) for pawn structure.
    Penalties: doubled pawns, isolated pawns.
    Bonuses:   passed pawns, connected pawns.
    """
    opponent = BLACK if color == WHITE else WHITE
    my_pawns    = [p for p in board.players[color].pieces    if p.name == 'P']
    opp_pawns   = [p for p in board.players[opponent].pieces if p.name == 'P']

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


def _mobility(board) -> float:
    """Legal move count difference: positive = white has more mobility."""
    white_moves = sum(len(p.moves) for p in board.players[WHITE].pieces)
    black_moves = sum(len(p.moves) for p in board.players[BLACK].pieces)
    return 0.05 * (white_moves - black_moves)


def _king_safety(board, color) -> float:
    """
    Dynamic king safety based on:
      - Pawn shield in front of the king (+)
      - Open/semi-open files near the king (-)
      - Enemy piece proximity to the king (-)
    """
    opponent = BLACK if color == WHITE else WHITE
    king_pieces = [p for p in board.players[color].pieces if p.name == 'K']
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
        p.location for p in board.players[color].pieces if p.name == 'P'
    }
    for f in shield_files:
        sq = f + str(shield_row)
        if 1 <= shield_row <= 8 and sq in friendly_pawns:
            score += 0.15

    # ── Open file penalty ─────────────────────────────────────────────────
    all_pawn_files = {
        p.location[0]
        for side in (WHITE, BLACK)
        for p in board.players[side].pieces
        if p.name == 'P'
    }
    for f in shield_files:
        if f not in all_pawn_files:          # fully open file near king
            score -= 0.25
        elif f not in {p.location[0] for p in board.players[color].pieces if p.name == 'P'}:
            score -= 0.1                     # semi-open (opponent pawn only)

    # ── Enemy attacker proximity ──────────────────────────────────────────
    for piece in board.players[opponent].pieces:
        if piece.name in ('K', 'P'):
            continue
        opp_col = COLUMNS.index(piece.location[0])
        opp_row = int(piece.location[1])
        dist = max(abs(opp_col - king_col_idx), abs(opp_row - king_row))
        if dist <= 2:
            score -= 0.15 * PIECE_VALUES[piece.name] / 5.0

    return score


def _bishop_pair(board, color) -> float:
    bishops = [p for p in board.players[color].pieces if p.name == 'B']
    return 0.3 if len(bishops) >= 2 else 0.0


def _rook_on_open_file(board, color) -> float:
    """Bonus for rooks on open or semi-open files."""
    score = 0.0
    all_pawn_files = {
        p.location[0]
        for side in (WHITE, BLACK)
        for p in board.players[side].pieces
        if p.name == 'P'
    }
    friendly_pawn_files = {
        p.location[0] for p in board.players[color].pieces if p.name == 'P'
    }
    for piece in board.players[color].pieces:
        if piece.name != 'R':
            continue
        f = piece.location[0]
        if f not in all_pawn_files:
            score += 0.25       # fully open file
        elif f not in friendly_pawn_files:
            score += 0.1        # semi-open (no friendly pawn)
    return score


def evaluate_terminal(board, color, depth):
    opponent = BLACK if color == WHITE else WHITE

    if board.players[opponent].mated:
        return MATE_SCORE - depth

    if board.players[color].mated:
        return -MATE_SCORE + depth

    if len(board.players[opponent].possible_moves) == 0:
        return 0  

    return None

def evaluate(board, color) -> float:

    model_score = 0.0
    if model is not None:
        tensor = board_to_tensor(board)
        x = torch.tensor(tensor).unsqueeze(0).float()
        with torch.no_grad():
            model_score = model(x).item()

    classical = 0.0
    for piece in board.players[WHITE].pieces:
        classical += PIECE_VALUES[piece.name] + get_position_bonus(piece)
    for piece in board.players[BLACK].pieces:
        classical -= PIECE_VALUES[piece.name] + get_position_bonus(piece)

    classical += _pawn_structure(board, WHITE)
    classical -= _pawn_structure(board, BLACK)

    classical += _mobility(board)

    classical += _king_safety(board, WHITE)
    classical -= _king_safety(board, BLACK)

    classical += _bishop_pair(board, WHITE)
    classical -= _bishop_pair(board, BLACK)

    classical += _rook_on_open_file(board, WHITE)
    classical -= _rook_on_open_file(board, BLACK)

    score = 0.4 * model_score + 0.6 * classical

    return score if color == WHITE else -score

# ── Minimax with Alpha-Beta Pruning ───────────────────────────────────────────
# alpha = best score the maximizing player is guaranteed so far
# beta  = best score the minimizing player is guaranteed so far
# If beta <= alpha we can stop searching this branch — the opponent
# already has a better option elsewhere and will never allow this line

def move_order_score(board, piece, move, color=None, repertoire_name="balanced"):
    score = 0.0
    target_tile = board._get_tile(move)

    # Captures first: Most Valuable Victim - Least Valuable Attacker
    if target_tile and target_tile.piece and target_tile.piece.color != piece.color:
        victim = target_tile.piece
        score += 10 * PIECE_VALUES[victim.name] - PIECE_VALUES[piece.name]

    # Promotions
    if piece.name == 'P' and ((piece.color == WHITE and move[1] == '8') or
                              (piece.color == BLACK and move[1] == '1')):
        score += 8.0

    # Centralization bias
    center_bonus = {
        'd4': 0.5, 'e4': 0.5, 'd5': 0.5, 'e5': 0.5,
        'c3': 0.2, 'd3': 0.2, 'e3': 0.2, 'f3': 0.2,
        'c4': 0.2, 'f4': 0.2, 'c5': 0.2, 'f5': 0.2,
        'c6': 0.2, 'd6': 0.2, 'e6': 0.2, 'f6': 0.2,
    }
    score += center_bonus.get(move, 0.0)

    if color is not None:
        score += book_move_bonus(board, piece, move, color=color, repertoire_name=repertoire_name)

    return score

def minimax(board, depth: int, turn: str, root_color: str,
            alpha=float('-inf'), beta=float('inf'),
            repertoire_name="balanced") -> float:

    # 1. TERMINAL CHECK — FIRST
    terminal = evaluate_terminal(board, root_color, depth)
    if terminal is not None:
        return terminal

    # 2. DEPTH LIMIT
    if depth == 0:
        return evaluate(board, root_color)

    maximizing = (turn == root_color)
    next_turn = BLACK if turn == WHITE else WHITE

    # Gather legal moves for side to move
    all_moves = []
    for piece in board.players[turn].pieces:
        for move in piece.moves:
            target_tile = board._get_tile(move)
            if target_tile and target_tile.piece and target_tile.piece.name == "K":
                continue
            all_moves.append((piece, move))

    all_moves.sort(
        key=lambda pm: move_order_score(
            board,
            pm[0],
            pm[1],
            color=turn,
            repertoire_name=repertoire_name
        ),
        reverse=True
    )

    # No legal moves — stalemate or checkmate
    if not all_moves:
        if not board.players[turn].checked:
            return 0.0  # stalemate
        # side to move is mated
        return float('-inf') if turn == root_color else float('inf')

    if maximizing:
        best = float('-inf')

        for piece, move in all_moves:
            snap = board._snapshot_state()

            try:
                board._move_piece(piece, move, simulate=True)
                board._sync_board()

                board.players[WHITE].update_moves(board.board, board.players[BLACK].actions)
                board.players[BLACK].update_moves(board.board, board.players[WHITE].actions)

                board.players[WHITE].checked = board._test_check(WHITE)
                board.players[BLACK].checked = board._test_check(BLACK)

                score = minimax(
                    board,
                    depth - 1,
                    next_turn,
                    root_color,
                    alpha,
                    beta,
                    repertoire_name=repertoire_name
                )
            except ValueError as e:
                if "kings cannot be captured" in str(e):
                    continue
                raise
            finally:
                board._restore_state(snap)

            best = max(best, score)
            alpha = max(alpha, best)

            if beta <= alpha:
                break

        return best

    else:
        best = float('inf')

        for piece, move in all_moves:
            snap = board._snapshot_state()

            try:
                board._move_piece(piece, move, simulate=True)
                board._sync_board()

                board.players[WHITE].update_moves(board.board, board.players[BLACK].actions)
                board.players[BLACK].update_moves(board.board, board.players[WHITE].actions)

                board.players[WHITE].checked = board._test_check(WHITE)
                board.players[BLACK].checked = board._test_check(BLACK)

                score = minimax(
                    board,
                    depth - 1,
                    next_turn,
                    root_color,
                    alpha,
                    beta,
                    repertoire_name=repertoire_name
                )
            except ValueError as e:
                if "kings cannot be captured" in str(e):
                    continue
                raise
            finally:
                board._restore_state(snap)

            best = min(best, score)
            beta = min(beta, best)

            if beta <= alpha:
                break

        return best

# ── Best Move ────────────────────────────────────────────────────────────────


def best_move(board, color, depth=4, repertoire_name="balanced", use_opening_book=True):

    if use_opening_book:
        book_choice = choose_book_move(board, color, repertoire_name=repertoire_name)
        if book_choice is not None:
            from_sq, to_sq, _meta = book_choice
            return (from_sq, to_sq)

    best_score = float('-inf')
    chosen = None

    alpha = float('-inf')
    beta  = float('inf')

    opponent = BLACK if color == WHITE else WHITE

    candidate_moves = []
    for piece in board.players[color].pieces:
        for move in list(piece.moves):
            target_tile = board._get_tile(move)
            if target_tile and target_tile.piece and target_tile.piece.name == "K":
                continue
            candidate_moves.append((piece, move))

    candidate_moves.sort(
        key=lambda pm: move_order_score(
            board,
            pm[0],
            pm[1],
            color=color,
            repertoire_name=repertoire_name
        ),
        reverse=True
    )

    for piece, move in candidate_moves:
        target_tile = board._get_tile(move)
        if target_tile and target_tile.piece and target_tile.piece.name == "K":
            continue

        from_sq = piece.location
        snap = board._snapshot_state()

        try:
            board._move_piece(piece, move, simulate=True)
            board._sync_board()

            board.players[WHITE].update_moves(board.board, board.players[BLACK].actions)
            board.players[BLACK].update_moves(board.board, board.players[WHITE].actions)

            board.players[WHITE].checked = board._test_check(WHITE)
            board.players[BLACK].checked = board._test_check(BLACK)

            score = minimax(
                board,
                depth - 1,
                opponent,
                color,
                alpha,
                beta,
                repertoire_name=repertoire_name
            )
        finally:
            board._restore_state(snap)

        if score > best_score:
            best_score = score
            chosen = (from_sq, move)

        alpha = max(alpha, best_score)

    return chosen