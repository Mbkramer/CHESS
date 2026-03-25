"""
texel_tuner.py

Offline evaluation parameter optimizer using the Texel tuning method.

Usage:
    python3 texel_tuner.py --pgn data/filtered.pgn --games 200000 --output tuned_params.json
    python3 texel_tuner.py --pgn data/filtered.pgn --games 200000 --load tuned_params.json
"""

import os, sys, json, math, time, copy, argparse
sys.path.insert(0, os.path.dirname(__file__))

from chess_board import ChessBoard
from bot import EvalParams, evaluate, evaluate_fast, EVAL_PARAMS
from pgn_replay import iter_pgn_data   # ← reuse your existing pipeline

# ── Constants ─────────────────────────────────────────────────────────────────

K_FACTOR = 0.5   # Sigmoid scaling constant. Tune this first (see Phase 3)

# ── Sigmoid ───────────────────────────────────────────────────────────────────

def sigmoid(score: float, K: float = K_FACTOR) -> float:
    """Map eval score to win probability [0, 1]."""
    return 1.0 / (1.0 + math.pow(10.0, -K * score / 400.0))

# ── MSE ───────────────────────────────────────────────────────────────────────

def compute_mse(positions: list, params: EvalParams, k: float = K_FACTOR) -> float:
    """
    positions: list of (ChessBoard snapshot, result_float) tuples
    result_float: already normalized to [0,1] where 1.0=white win
    """

    total_error = 0.0
    for board, result in positions:
        score = evaluate_fast(board, p=params)
        predicted = sigmoid(score, K=k)
        total_error += (predicted - result) ** 2
    return total_error / len(positions)

# ── Param serialization ───────────────────────────────────────────────────────

def params_to_dict(p: EvalParams) -> dict:
    import dataclasses
    return dataclasses.asdict(p)

def dict_to_params(d: dict) -> EvalParams:
    return EvalParams(**d)

def save_params(p: EvalParams, path: str):
    with open(path, 'w') as f:
        json.dump(params_to_dict(p), f, indent=2)
    print(f"Saved params to {path}")

def load_params(path: str) -> EvalParams:
    with open(path) as f:
        d = json.load(f)
    return dict_to_params(d)

# ── Flat param access (needed for coordinate descent) ─────────────────────────

def get_flat_params(p: EvalParams) -> list:
    """
    Returns list of (path, value) where path is a tuple like
    ('pawn_table', 12) or ('mobility_weight',)
    """
    flat = []
    import dataclasses
    for f in dataclasses.fields(p):
        val = getattr(p, f.name)
        if isinstance(val, list):
            for i, v in enumerate(val):
                flat.append(((f.name, i), v))
        else:
            flat.append(((f.name,), val))
    return flat

def set_param(p: EvalParams, path: tuple, value: float) -> EvalParams:
    """Return a NEW EvalParams with one value changed. Non-destructive."""
    p2 = copy.deepcopy(p)
    if len(path) == 1:
        setattr(p2, path[0], value)
    else:
        lst = list(getattr(p2, path[0]))
        lst[path[1]] = value
        setattr(p2, path[0], lst)
    return p2

# ── Data Loading ──────────────────────────────────────────────────────────────

import pickle

def load_or_cache(pgn_path, cache_path, max_games, stride):
    if os.path.exists(cache_path):
        print(f"Loading cached positions from {cache_path}...")
        with open(cache_path, 'rb') as f:
            return pickle.load(f)

    print("Replaying games (first time only)...")
    positions = load_board_positions(pgn_path, max_games=max_games, stride=stride)

    with open(cache_path, 'wb') as f:
        pickle.dump(positions, f)
    print(f"Cached {len(positions)} positions to {cache_path}")
    return positions


def load_positions(pgn_path: str, max_games: int = 100000) -> list:
    """
    Load quiet positions from PGN using your existing pgn_replay pipeline.
    Returns list of (board, normalized_result) tuples.

    NOTE: This is the slow step. Run once, cache to disk.
    """
    from pgn_replay import iter_pgn_data
    # iter_pgn_data yields (tensor, result) but we need (board, result)
    # We need a board-aware version — see load_board_positions() below
    raise NotImplementedError("Use load_board_positions() instead")

def load_board_positions(pgn_path: str, max_games: int = 100000,
                          stride: int = 12, verbose: bool = True) -> list:
    """
    Replay PGN games through your engine and collect board snapshots.
    Returns list of (ChessBoard, normalized_result).

    stride=6: sample every 6th position (balance coverage vs speed)
    """
    import chess
    import chess.pgn
    from pgn_replay import RESULT_MAP, PROMOTION_MAP

    positions = []
    count = 0
    skipped = 0
    start = time.time()

    with open(pgn_path, 'r', encoding='utf-8', errors='ignore') as f:
        while count < max_games:
            game = chess.pgn.read_game(f)
            if game is None:
                break

            result_str = game.headers.get('Result', '*')
            result = RESULT_MAP.get(result_str)
            if result is None:
                skipped += 1
                continue

            # Normalize result to [0, 1]
            normalized = (result + 1.0) / 2.0

            try:
                moves = list(game.mainline_moves())
            except Exception:
                skipped += 1
                continue

            if len(moves) < 10:
                skipped += 1
                continue

            board = ChessBoard()
            ref_board = chess.Board()
            turn = 'W'
            game_positions = []

            try:
                for i, move in enumerate(moves):
                    from_sq = chess.square_name(move.from_square)
                    to_sq   = chess.square_name(move.to_square)
                    promo   = PROMOTION_MAP.get(move.promotion)

                    piece = next(
                        (p for p in board.players[turn].pieces if p.location == from_sq),
                        None
                    )
                    if piece is None or to_sq not in piece.moves:
                        break

                    # Sample positions at stride intervals and late game
                    is_late = i >= len(moves) - 12
                    is_capture = ref_board.is_capture(move)
                    if i % stride == 0 or is_late:
                        # IMPORTANT: only keep quiet positions
                        # Skip positions where the side to move is in check
                        # or has obvious hanging pieces (reduces noise)
                        if not board.players[turn].checked:
                            game_positions.append((copy.deepcopy(board), normalized))

                    board._move_piece(piece, to_sq, simulate=False, promotion=promo)
                    board._update_tiles()
                    ref_board.push(move)

                    turn = 'B' if turn == 'W' else 'W'

            except Exception:
                skipped += 1
                continue

            positions.extend(game_positions)
            count += 1

            if verbose and count % 500 == 0:
                elapsed = time.time() - start
                print(f"  {count}/{max_games} games | "
                      f"{len(positions)} positions | "
                      f"elapsed={elapsed:.0f}s")

    print(f"Loaded {len(positions)} positions from {count} games ({skipped} skipped)")
    return positions

# ── K-Factor Calibration ──────────────────────────────────────────────────────

def calibrate_k(positions: list, params: EvalParams,
                k_range=(0.1, 50.0), steps=40) -> float:
    """
    Find the K value that minimizes MSE on your current eval.
    Run this ONCE before tuning — it sets the scale for the sigmoid.
    """
    best_k = K_FACTOR
    best_mse = float('inf')

    for i in range(steps + 1):
        k = k_range[0] + (k_range[1] - k_range[0]) * i / steps
        total = sum(
            (1.0 / (1.0 + math.pow(10.0, -k * evaluate(b, 'W', p=params) / 400.0)) - r) ** 2
            for b, r in positions
        )
        mse = total / len(positions)
        if mse < best_mse:
            best_mse = mse
            best_k = k

    print(f"Best K = {best_k:.3f}  (MSE = {best_mse:.6f})")
    return best_k

# ── Local Coordinate Descent ──────────────────────────────────────────────────

def tune(positions: list, params: EvalParams,
         delta: float = 0.01,
         max_passes: int = 20,
         save_path: str = "tuned_params.json",
         verbose: bool = True) -> EvalParams:
    """
    Core Texel tuning loop.

    For each parameter:
      1. Try param + delta
      2. Try param - delta
      3. Keep whichever lowers MSE, or leave unchanged

    Repeat until a full pass makes no improvement.
    """

    best_mse = compute_mse(positions, params)
    print(f"Initial MSE: {best_mse:.6f}")

    flat = get_flat_params(params)
    # CRITICAL: skip pawn table index 0 and pawn value itself
    # Anchor pawn = 1.0 to prevent weight collapse

    for pass_num in range(max_passes):
        improved = 0
        pass_start = time.time()

        for param_idx, (path, current_val) in enumerate(flat):
            # Never tune pawn material value — it's the anchor
            if path == ('pawn_value',):
                continue

            # Try +delta
            p_plus = set_param(params, path, current_val + delta)
            mse_plus = compute_mse(positions, p_plus)

            if mse_plus < best_mse:
                params = p_plus
                best_mse = mse_plus
                current_val = current_val + delta
                improved += 1
                continue

            # Try -delta
            p_minus = set_param(params, path, current_val - delta)
            mse_minus = compute_mse(positions, p_minus)

            if param_idx % 10 == 0:
                print(f"  param {param_idx}/{len(flat)}  current MSE: {best_mse:.6f}")

            if mse_minus < best_mse:
                params = p_minus
                best_mse = mse_minus
                current_val = current_val - delta
                improved += 1
            

        pass_time = time.time() - pass_start
        if verbose:
            print(f"Pass {pass_num+1}/{max_passes} | "
                  f"improved={improved} | "
                  f"MSE={best_mse:.6f} | "
                  f"time={pass_time:.1f}s")

        # Auto-save after each pass
        save_params(params, save_path)

        # Early termination if no improvement
        if improved == 0:
            print(f"Converged after {pass_num+1} passes")
            break

    return params

# ── Apply Tuned Params Back to bot.py ─────────────────────────────────────────

def apply_params_to_bot(params: EvalParams, bot_path: str = "bot.py"):
    """
    Generate the Python code for the tuned tables and print it.
    You copy-paste this back into bot.py to bake in the results.
    """
    lines = ["# ── Tuned Parameters (generated by texel_tuner.py) ──\n"]

    def fmt_table(name, values):
        lines.append(f"{name} = [")
        for i in range(0, 64, 8):
            row = values[i:i+8]
            lines.append("    " + ", ".join(f"{v:6.3f}" for v in row) + ",")
        lines.append("]\n")

    fmt_table("PAWN_TABLE",   params.pawn_table)
    fmt_table("KNIGHT_TABLE", params.knight_table)
    fmt_table("BISHOP_TABLE", params.bishop_table)
    fmt_table("ROOK_TABLE",   params.rook_table)
    fmt_table("QUEEN_TABLE",  params.queen_table)
    fmt_table("KING_TABLE",   params.king_table)

    lines.append(f"PIECE_VALUES = {{'P': 1.0, 'N': {params.knight_value:.3f}, "
                 f"'B': {params.bishop_value:.3f}, 'R': {params.rook_value:.3f}, "
                 f"'Q': {params.queen_value:.3f}, 'K': 0.0}}\n")

    print("\n".join(lines))

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--pgn',    required=True, help='Path to filtered PGN file')
    parser.add_argument('--games',  type=int, default=50000)
    parser.add_argument('--delta',  type=float, default=0.01)
    parser.add_argument('--passes', type=int, default=20)
    parser.add_argument('--output', default='check_points/tuned_params.json')
    parser.add_argument('--load',   default=None, help='Resume from saved params')
    parser.add_argument('--calibrate-k', action='store_true')
    parser.add_argument('--apply',  action='store_true',
                        help='Print tuned params as Python code to paste into bot.py')
    parser.add_argument('--cache', default=None,
                    help='Path to cache replayed positions (e.g. check_points/cache_5k.pkl). '
                         'Loads from disk if exists, saves there after first replay.')
    args = parser.parse_args()

    # Load or initialize params
    if args.load and os.path.exists(args.load):
        params = load_params(args.load)
        print(f"Resumed from {args.load}")
    else:
        params = EvalParams()
        print("Starting from default params")

    if args.apply:
        apply_params_to_bot(params)
        exit(0)

    # Load positions
    if args.cache:
        positions = load_or_cache(args.pgn, args.cache, max_games=args.games, stride=10)
    else:
        print(f"Loading positions from {args.pgn}...")
        positions = load_board_positions(args.pgn, max_games=args.games, stride=10)

    if not positions:
        print("No positions loaded. Check your PGN path.")
        exit(1)

    # Tune
    print(f"\nTuning {len(get_flat_params(params))} parameters "
          f"over {len(positions)} positions...")

    # Calibrate K
    if args.calibrate_k:
        best_k = calibrate_k(positions, params)
        K_FACTOR = best_k 

    tuned = tune(
        positions, params,
        delta=args.delta,
        max_passes=args.passes,
        save_path=args.output,
    )

    print("\nDone! Apply tuned params with:")
    print(f"  python3 texel_tuner.py --load {args.output} --apply")