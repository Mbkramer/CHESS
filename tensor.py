import numpy as np

WHITE = 'W'
BLACK = 'B'

COLUMNS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
ROWS    = ['1', '2', '3', '4', '5', '6', '7', '8']

# 12 planes — one per piece type per color and color
# Plane index:  0=WP  1=WN  2=WB  3=WR  4=WQ  5=WK
#               6=BP  7=BN  8=BB  9=BR 10=BQ 11=BK
PIECE_PLANE = {
    ('W', 'P'): 0,  ('W', 'N'): 1,  ('W', 'B'): 2,
    ('W', 'R'): 3,  ('W', 'Q'): 4,  ('W', 'K'): 5,
    ('B', 'P'): 6,  ('B', 'N'): 7,  ('B', 'B'): 8,
    ('B', 'R'): 9,  ('B', 'Q'): 10, ('B', 'K'): 11,
}


def square_to_index(location: str):
    """Convert 'e4' → (row, col) indices into an 8x8 grid.
    Row 0 = rank 1 (white's back rank), row 7 = rank 8."""
    col = COLUMNS.index(location[0])
    row = ROWS.index(location[1])
    return row, col


def board_to_tensor(chess_board, turn: str = WHITE) -> np.ndarray:
    """
    Returns a (13, 8, 8) tensor.
    Planes 0-11: piece occupancy (unchanged).
    Plane 12:    all 1.0 if it is White's turn, all 0.0 if Black's turn.
    """
    tensor = np.zeros((13, 8, 8), dtype=np.float32)

    for color in (WHITE, BLACK):
        for piece in chess_board.players[color].pieces:
            plane = PIECE_PLANE.get((piece.color, piece.name))
            if plane is not None:
                row, col = square_to_index(piece.location)
                tensor[plane][row][col] = 1.0

    if turn == WHITE:
        tensor[12, :, :] = 1.0

    return tensor


def tensor_to_board_display(tensor: np.ndarray) -> str:
    """Debug helper — print a human-readable version of the tensor."""
    piece_chars = {
        0: 'P', 1: 'N', 2: 'B', 3: 'R', 4: 'Q', 5: 'K',
        6: 'p', 7: 'n', 8: 'b', 9: 'r', 10: 'q', 11: 'k',
    }
    grid = [['.' for _ in range(8)] for _ in range(8)]
    for plane, char in piece_chars.items():
        for row in range(8):
            for col in range(8):
                if tensor[plane][row][col] == 1.0:
                    grid[row][col] = char

    lines = []
    for row in reversed(range(8)):
        rank = ROWS[row]
        lines.append(f"{rank} " + " ".join(grid[row]))
    lines.append("  " + " ".join(COLUMNS))
    return "\n".join(lines)


if __name__ == "__main__":
    # Quick sanity check
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from chess_board import ChessBoard

    b = ChessBoard()
    t = board_to_tensor(b)

    print(f"Tensor shape: {t.shape}")
    print(f"Non-zero values: {np.count_nonzero(t)} (should be 32)")
    print()
    print(tensor_to_board_display(t))