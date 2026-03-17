from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
import random

WHITE = 'W'
BLACK = 'B'

BALANCED = "balanced"
AGRESSIVE = "aggressive"
SOLID = "solid"
TACTICAL = "tactical"

UCI = str  # simple from_sq + to_sq like e2e4


@dataclass(frozen=True)
class BookMove:
    move: UCI
    weight: float = 1.0


@dataclass(frozen=True)
class OpeningNode:
    name: str
    eco: str
    continuations: Tuple[BookMove, ...]
    style_tags: Tuple[str, ...] = field(default_factory=tuple)


DEFAULT_REPERTOIRE = {
    "name": "balanced",
    "white": {"allow": set()},
    "black_vs_e4": {"allow": set()},
    "black_vs_d4": {"allow": set()},
    "black_other": {"allow": set()},
}

REPERTOIRES = {
    "balanced": DEFAULT_REPERTOIRE,
    "aggressive": {
        "name": "aggressive",
        "white": {"allow": {"Italian Game", "Open Sicilian", "Queen's Gambit", "English Opening"}},
        "black_vs_e4": {"allow": {"Sicilian Defense", "Open Game", "Pirc Defense"}},
        "black_vs_d4": {"allow": {"King's Indian Defense", "Dutch Defense"}},
        "black_other": {"allow": set()},
    },
    "solid": {
        "name": "solid",
        "white": {"allow": {"Italian Game", "London System", "Queen's Gambit"}},
        "black_vs_e4": {"allow": {"Caro-Kann Defense", "French Defense", "Open Game"}},
        "black_vs_d4": {"allow": {"Queen's Gambit Declined", "Slav Defense", "Nimzo-Indian Defense"}},
        "black_other": {"allow": set()},
    },
    "tactical": {
        "name": "tactical",
        "white": {"allow": {"Open Sicilian", "Italian Game", "King's Gambit"}},
        "black_vs_e4": {"allow": {"Sicilian Defense", "Pirc Defense", "Alekhine Defense"}},
        "black_vs_d4": {"allow": {"King's Indian Defense", "Dutch Defense"}},
        "black_other": {"allow": set()},
    },
}

# Tree keyed by full move history in simple UCI move strings.
# This is intentionally compact. It is enough to improve early play and give
# the engine repertoire control without creating a brittle giant opening book.
OPENING_BOOK: Dict[Tuple[UCI, ...], OpeningNode] = {
    tuple(): OpeningNode(
        name="Start Position",
        eco="",
        continuations=(
            BookMove("e2e4", 4.0),
            BookMove("d2d4", 3.0),
            BookMove("c2c4", 1.5),
            BookMove("g1f3", 1.0),
        ),
        style_tags=("universal",),
    ),

    # 1. e4 trees
    ("e2e4",): OpeningNode(
        name="King Pawn Opening",
        eco="B00-C99",
        continuations=(
            BookMove("c7c5", 4.0),  # Sicilian
            BookMove("e7e5", 3.5),  # Open Game
            BookMove("c7c6", 1.5),  # Caro
            BookMove("e7e6", 1.4),  # French
            BookMove("d7d5", 1.0),  # Scandinavian
            BookMove("d7d6", 0.8),  # Pirc/Modern shell
            BookMove("g8f6", 0.5),  # Alekhine
        ),
        style_tags=("open",),
    ),
    ("e2e4", "e7e5"): OpeningNode(
        name="Open Game",
        eco="C20-C59",
        continuations=(
            BookMove("g1f3", 5.0),
            BookMove("f2f4", 0.8),
            BookMove("f1c4", 0.8),
        ),
        style_tags=("classical",),
    ),
    ("e2e4", "e7e5", "g1f3"): OpeningNode(
        name="King Knight Opening",
        eco="C40-C59",
        continuations=(
            BookMove("b8c6", 4.0),
            BookMove("d7d6", 1.0),
            BookMove("g8f6", 1.0),
        ),
        style_tags=("classical",),
    ),
    ("e2e4", "e7e5", "g1f3", "b8c6"): OpeningNode(
        name="Open Game",
        eco="C44-C59",
        continuations=(
            BookMove("f1c4", 2.2),  # Italian
            BookMove("f1b5", 2.0),  # Ruy Lopez
            BookMove("d2d4", 0.6),  # Scotch
        ),
        style_tags=("open",),
    ),
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4"): OpeningNode(
        name="Italian Game",
        eco="C50-C54",
        continuations=(
            BookMove("f8c5", 3.5),
            BookMove("g8f6", 2.0),
            BookMove("f8e7", 0.8),
        ),
        style_tags=("classical", "tactical"),
    ),
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"): OpeningNode(
        name="Italian Game",
        eco="C50-C54",
        continuations=(
            BookMove("c2c3", 2.0),
            BookMove("d2d3", 1.6),
            BookMove("b1c3", 1.0),
        ),
        style_tags=("development",),
    ),
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5"): OpeningNode(
        name="Ruy Lopez",
        eco="C60-C99",
        continuations=(
            BookMove("a7a6", 3.5),
            BookMove("g8f6", 2.0),
        ),
        style_tags=("classical", "solid"),
    ),
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"): OpeningNode(
        name="Ruy Lopez",
        eco="C60-C99",
        continuations=(
            BookMove("b5a4", 3.0),
            BookMove("b5c6", 0.7),
        ),
        style_tags=("classical",),
    ),

    # Sicilian
    ("e2e4", "c7c5"): OpeningNode(
        name="Sicilian Defense",
        eco="B20-B99",
        continuations=(
            BookMove("g1f3", 4.0),
            BookMove("b1c3", 1.0),
            BookMove("c2c3", 0.8),
        ),
        style_tags=("sharp",),
    ),
    ("e2e4", "c7c5", "g1f3"): OpeningNode(
        name="Open Sicilian",
        eco="B20-B99",
        continuations=(
            BookMove("d7d6", 2.5),
            BookMove("b8c6", 2.0),
            BookMove("e7e6", 1.5),
        ),
        style_tags=("sharp",),
    ),
    ("e2e4", "c7c5", "g1f3", "d7d6"): OpeningNode(
        name="Sicilian Defense",
        eco="B50-B99",
        continuations=(
            BookMove("d2d4", 4.0),
            BookMove("f1b5", 0.6),
            BookMove("c2c3", 0.5),
        ),
        style_tags=("mainline",),
    ),
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4"): OpeningNode(
        name="Open Sicilian",
        eco="B50-B99",
        continuations=(BookMove("c5d4", 5.0),),
        style_tags=("open",),
    ),
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4"): OpeningNode(
        name="Open Sicilian",
        eco="B50-B99",
        continuations=(BookMove("f3d4", 5.0),),
        style_tags=("open",),
    ),
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4"): OpeningNode(
        name="Open Sicilian",
        eco="B50-B99",
        continuations=(
            BookMove("g8f6", 2.5),
            BookMove("b8c6", 2.0),
            BookMove("a7a6", 1.0),
        ),
        style_tags=("sharp",),
    ),

    # Caro-Kann / French / Scandinavian / Pirc / Alekhine
    ("e2e4", "c7c6"): OpeningNode(
        name="Caro-Kann Defense",
        eco="B10-B19",
        continuations=(BookMove("d2d4", 4.0), BookMove("g1f3", 0.6)),
        style_tags=("solid",),
    ),
    ("e2e4", "e7e6"): OpeningNode(
        name="French Defense",
        eco="C00-C19",
        continuations=(BookMove("d2d4", 4.0), BookMove("g1f3", 0.8)),
        style_tags=("solid",),
    ),
    ("e2e4", "d7d5"): OpeningNode(
        name="Scandinavian Defense",
        eco="B01",
        continuations=(BookMove("e4d5", 5.0),),
        style_tags=("direct",),
    ),
    ("e2e4", "d7d6"): OpeningNode(
        name="Pirc Defense",
        eco="B07-B09",
        continuations=(BookMove("d2d4", 4.0), BookMove("g1f3", 1.0)),
        style_tags=("flexible",),
    ),
    ("e2e4", "g8f6"): OpeningNode(
        name="Alekhine Defense",
        eco="B02-B05",
        continuations=(BookMove("e4e5", 3.0), BookMove("b1c3", 0.8)),
        style_tags=("provocative",),
    ),

    # 1. d4 trees
    ("d2d4",): OpeningNode(
        name="Queen Pawn Opening",
        eco="A40-D99",
        continuations=(
            BookMove("d7d5", 4.0),
            BookMove("g8f6", 3.0),
            BookMove("f7f5", 0.7),
        ),
        style_tags=("closed",),
    ),
    ("d2d4", "d7d5"): OpeningNode(
        name="Queen Pawn Game",
        eco="D00-D69",
        continuations=(
            BookMove("c2c4", 4.0),
            BookMove("g1f3", 1.2),
            BookMove("c1f4", 1.0),
        ),
        style_tags=("classical",),
    ),
    ("d2d4", "d7d5", "c2c4"): OpeningNode(
        name="Queen's Gambit",
        eco="D06-D69",
        continuations=(
            BookMove("e7e6", 2.8),  # QGD
            BookMove("c7c6", 2.0),  # Slav
            BookMove("d5c4", 0.8),  # QGA
        ),
        style_tags=("classical",),
    ),
    ("d2d4", "d7d5", "c2c4", "e7e6"): OpeningNode(
        name="Queen's Gambit Declined",
        eco="D30-D69",
        continuations=(
            BookMove("b1c3", 2.0),
            BookMove("g1f3", 2.0),
        ),
        style_tags=("solid",),
    ),
    ("d2d4", "d7d5", "c2c4", "c7c6"): OpeningNode(
        name="Slav Defense",
        eco="D10-D29",
        continuations=(
            BookMove("g1f3", 2.5),
            BookMove("b1c3", 2.0),
        ),
        style_tags=("solid",),
    ),
    ("d2d4", "d7d5", "g1f3"): OpeningNode(
        name="Queen Pawn Game",
        eco="D00",
        continuations=(
            BookMove("g8f6", 2.0),
            BookMove("e7e6", 1.6),
            BookMove("c7c6", 1.2),
        ),
        style_tags=("flexible",),
    ),
    ("d2d4", "d7d5", "g1f3", "g8f6"): OpeningNode(
        name="London System",
        eco="D02",
        continuations=(BookMove("c1f4", 4.0), BookMove("c2c4", 1.0)),
        style_tags=("solid",),
    ),
    ("d2d4", "d7d5", "g1f3", "g8f6", "c1f4"): OpeningNode(
        name="London System",
        eco="D02",
        continuations=(
            BookMove("e7e6", 2.0),
            BookMove("c7c5", 1.5),
            BookMove("c8f5", 1.0),
        ),
        style_tags=("solid",),
    ),

    # Indian / Dutch / English
    ("d2d4", "g8f6"): OpeningNode(
        name="Indian Defense",
        eco="A45-E99",
        continuations=(
            BookMove("c2c4", 4.0),
            BookMove("g1f3", 1.0),
            BookMove("c1f4", 0.8),
        ),
        style_tags=("flexible",),
    ),
    ("d2d4", "g8f6", "c2c4"): OpeningNode(
        name="Indian Defense",
        eco="A45-E99",
        continuations=(
            BookMove("e7e6", 2.5),
            BookMove("g7g6", 2.0),
        ),
        style_tags=("flexible",),
    ),
    ("d2d4", "g8f6", "c2c4", "e7e6"): OpeningNode(
        name="Indian Defense",
        eco="E00-E59",
        continuations=(
            BookMove("b1c3", 3.0),
            BookMove("g1f3", 2.0),
        ),
        style_tags=("classical",),
    ),
    ("d2d4", "g8f6", "c2c4", "e7e6", "b1c3"): OpeningNode(
        name="Nimzo-Indian Defense",
        eco="E20-E59",
        continuations=(BookMove("f8b4", 4.0),),
        style_tags=("solid", "strategic"),
    ),
    ("d2d4", "g8f6", "c2c4", "g7g6"): OpeningNode(
        name="King's Indian Defense",
        eco="E60-E99",
        continuations=(
            BookMove("b1c3", 2.0),
            BookMove("g1f3", 2.0),
        ),
        style_tags=("sharp",),
    ),
    ("d2d4", "f7f5"): OpeningNode(
        name="Dutch Defense",
        eco="A80-A99",
        continuations=(BookMove("g2g3", 1.5), BookMove("c2c4", 1.5), BookMove("g1f3", 1.0)),
        style_tags=("fighting",),
    ),
    ("c2c4",): OpeningNode(
        name="English Opening",
        eco="A10-A39",
        continuations=(
            BookMove("e7e5", 2.0),
            BookMove("c7c5", 1.8),
            BookMove("g8f6", 2.0),
            BookMove("e7e6", 1.2),
        ),
        style_tags=("flank",),
    ),
}


def board_move_history(board) -> Tuple[UCI, ...]:
    history: List[UCI] = []
    for action in getattr(board, "actions", []):
        history.append(f"{action.from_tile}{action.to_tile}")
    return tuple(history)


def current_opening_node(board) -> Optional[OpeningNode]:
    return OPENING_BOOK.get(board_move_history(board))


def current_opening_name(board) -> Optional[str]:
    node = current_opening_node(board)
    return node.name if node else None


def classify_black_reply_family(history: Sequence[UCI]) -> str:
    if len(history) < 1:
        return "black_other"
    white_first = history[0]
    if white_first == "e2e4":
        return "black_vs_e4"
    if white_first == "d2d4":
        return "black_vs_d4"
    return "black_other"


def _repertoire_allow_set(color: str, repertoire_name: str, history: Sequence[UCI]) -> set:
    rep = REPERTOIRES.get(repertoire_name, DEFAULT_REPERTOIRE)
    if color == WHITE:
        return set(rep.get("white", {}).get("allow", set()))
    bucket = classify_black_reply_family(history)
    return set(rep.get(bucket, {}).get("allow", set()))


def legal_book_moves(board, color: str, repertoire_name: str = "balanced") -> List[Tuple[UCI, float, str]]:
    history = board_move_history(board)
    node = OPENING_BOOK.get(history)
    if node is None:
        return []

    allow = _repertoire_allow_set(color, repertoire_name, history)
    legal_pairs = set(getattr(board.players[color], "possible_moves", []))

    out: List[Tuple[UCI, float, str]] = []
    for entry in node.continuations:
        move = entry.move
        if len(move) != 4:
            continue
        from_sq, to_sq = move[:2], move[2:]
        if (from_sq, to_sq) not in legal_pairs:
            continue
        child = OPENING_BOOK.get(history + (move,))
        child_name = child.name if child else node.name
        if allow and child_name not in allow and node.name not in allow:
            continue
        out.append((move, entry.weight, child_name))
    return out


def choose_book_move(board, color: str, repertoire_name: str = "balanced", weighted: bool = True) -> Optional[Tuple[str, str, Dict[str, str]]]:
    candidates = legal_book_moves(board, color, repertoire_name=repertoire_name)
    if not candidates:
        return None

    moves = [m for m, _w, _name in candidates]
    weights = [w for _m, w, _name in candidates]
    chosen = random.choices(moves, weights=weights, k=1)[0] if weighted else moves[0]

    chosen_name = None
    for move, _weight, name in candidates:
        if move == chosen:
            chosen_name = name
            break

    return chosen[:2], chosen[2:], {
        "source": "opening_book",
        "repertoire": repertoire_name,
        "opening": chosen_name or "Unknown",
        "history_len": str(len(board_move_history(board))),
    }


def book_move_bonus(board, piece, move, color: str, repertoire_name: str = "balanced") -> float:
    uci = f"{piece.location}{move}"
    candidates = legal_book_moves(board, color, repertoire_name=repertoire_name)
    for cand_move, weight, _name in candidates:
        if cand_move == uci:
            return 2.0 + 0.15 * weight
    return 0.0
