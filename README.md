# ♟ Chess Engine

A from-scratch Python chess engine with a terminal ASCII interface, a classical alpha-beta search bot, two trained neural networks (a general positional model and a tactical "kill bot"), an opening book, Texel parameter tuning, and a full unit-test suite.

---

## Overview

The engine implements the complete rules of chess — including castling, en passant, pawn promotion, and check/checkmate detection — on top of a custom board representation. A minimax search with alpha-beta pruning, quiescence search, and move-ordering heuristics powers the bot. Two PyTorch convolutional networks are blended with the classical evaluation to improve positional judgment and tactical awareness. Games can be exported as standard PGN files.

---

## Goals

- **Correctness first** — every legal move, edge case, and special rule is handled and unit-tested.
- **Hybrid evaluation** — blend a hand-crafted classical eval (material, PST, pawn structure, king safety, mobility) with two neural nets so each component covers the other's weaknesses.
- **Tuneable** — evaluation parameters can be optimized offline against a large PGN corpus via Texel tuning.
- **Playable** — three interactive modes: 2-player, player vs bot, and bot-aided play, all from the terminal.

---

## File Structure

```
.
├── main.py             # Entry point — launches start_game()
├── chess_engine.py     # Game loop, player menus, PGN export (human-facing)
├── chess_board.py      # Board state, tile/piece management, move legality, snapshot/restore
├── player.py           # Player class, piece initialisation, PlayerAction log
├── pieces.py           # Piece classes (Pawn, Knight, Bishop, Rook, Queen, King) + move generation
├── bot.py              # Search (minimax, alpha-beta, quiescence), evaluation, SEE, move ordering
├── opening_book.py     # Hard-coded UCI opening tree with repertoire support
├── model.py            # ChessNet CNN architecture + save/load helpers
├── tensor.py           # Board → (13, 8, 8) tensor conversion for the neural networks
├── ascii_art.py        # ASCII art piece/tile definitions for the terminal board display
├── texel_tuner.py      # Offline Texel tuning pipeline for EvalParams
├── test_chess.py       # Comprehensive unittest suite (board, moves, captures, castling, SEE, bot)
└── __init__.py
```

### Key directories (created at runtime)

| Path | Contents |
|---|---|
| `check_points/` | Saved model weights (`.pt`) and Texel tuning checkpoints (`.json`) |
| `data/played_games/` | PGN files of human games (`2p/`, `bot/`, `aid/`) |
| `data/bot_games/` | PGN files from bot self-play runs |

---

## Modes

| Mode | Description |
|---|---|
| `2p` | Two-player pass-and-play in the terminal |
| `bot` | Human vs the bot (choose side, optional shot clock) |
| `aid` | Human plays a real opponent while the bot suggests moves each turn |

All modes support an optional **shot clock** (in minutes) and a **debug flag** (`debug` / `DEBUG`) that prints the search tree. 

---

## Quick Start

### 1. Install dependencies

```bash
pip install torch numpy python-chess
```

### 2. Run the engine

```bash
python main.py
```

Follow the prompts to choose game mode, colour, and shot clock.

### 3. Run bot self-play (from `bot.py`)

```bash
python bot.py
# Enter: <num_games> <depth> <debug_level>
# e.g.:  1 2 0
```

### 4. Run the test suite

```bash
python -m unittest test_chess.py -v
```

### 5. Texel tuning (requires a PGN corpus)

```bash
# First run — replay and cache positions, then tune
python texel_tuner.py \
  --pgn data/filtered.pgn \
  --games 50000 \
  --output check_points/tuned_params.json

# Resume from a checkpoint
python texel_tuner.py \
  --pgn data/filtered.pgn \
  --games 50000 \
  --load check_points/tuned_params.json

# Print tuned tables as Python code to paste back into bot.py
python texel_tuner.py \
  --load check_points/tuned_params.json \
  --apply

# Cache replayed positions for faster subsequent runs
python texel_tuner.py \
  --pgn data/filtered.pgn \
  --games 50000 \
  --cache check_points/cache_50k.pkl \
  --output check_points/tuned_params.json
```

### 6. Model paths (environment variables)

```bash
# Override default model checkpoints
export CHESS_MODEL_PATH=check_points/my_model.pt
export MATE_BOT_PATH=check_points/my_kill_bot.pt
export CHESS_KILL_MODEL_PATH=check_points/my_kill_bot.pt   # used by tests
```

---

## Neural Networks
**NOTE** - The this project does not include a large dataset of PGN chess games to train these neural networks. A strong resource is Lichness or Chess.com's public chess datasets that host massive datasets of games from varrying players. Load 40000 - 200000 games locally for the best --pgn model training experience. 

Two separate `ChessNet` CNNs (3 conv layers + 3 FC layers, `tanh` output bounded `[-1, 1]`) are loaded at startup:

| Model | Variable | Role |
|---|---|---|
| General positional model | `CHESS_MODEL_PATH` | Blended into eval for natural piece activity; weighted most heavily in the opening |
| Tactical "kill bot" | `MATE_BOT_PATH` | Blended into eval in the middle/late game; weighted more heavily under check |

If no checkpoint is found the engine falls back to the pure classical evaluation.

---

## Bot Search

- **Algorithm** — Negamax-style minimax with alpha-beta pruning
- **Quiescence search** — resolves capture sequences at leaf nodes (depth 4)
- **Move ordering** — MVV-LVA, SEE filtering, PST delta, castling/promotion bonuses, opening-book bonus, backtrack penalties
- **Opening book** — UCI move tree covering ~60 common lines across four repertoire styles (`balanced`, `aggressive`, `solid`, `tactical`)
- **Depth** — default depth 2, auto-extended by ±1 in tactical/endgame positions; configurable via `best_move(..., depth=N)`

---

## Requirements File

See `requirements.txt` .
