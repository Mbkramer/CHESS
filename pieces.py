from ascii_art import *

COLOR = {"W": "White", "B": "Black"}

WHITE = 'W'
BLACK = 'B'

PIECES = {
    "P": "Pawn",
    "N": "Knight",
    "B": "Bishop",
    "R": "Rook",
    "Q": "Queen",
    "K": "King",
}

def _lookup_tile(board, tile_id: str):
    if hasattr(board, "tile_map"):
        return board.tile_map.get(tile_id)

    for row in board:
        for tile in row:
            if tile.id == tile_id:
                return tile
    return None


def _check_tile_piece(board, tile_id: str):
    tile = _lookup_tile(board, tile_id)
    return tile.piece if tile is not None else None


def _check_tile_occupied(board, tile_id: str) -> bool:
    tile = _lookup_tile(board, tile_id)
    return tile is not None and tile._is_occupied()


def _check_tile_occupied_by_opponent(board, tile_id: str, color: str) -> bool:
    tile = _lookup_tile(board, tile_id)
    return (
        tile is not None
        and tile._is_occupied()
        and tile.piece is not None
        and tile.piece.color != color
    )

def _square_attacked_by(board, square: str, by_color: str) -> bool:
    """Check if `square` is attacked by any piece of `by_color`.
    Uses already-generated raw moves — call after update_moves."""
    for piece in board.players[by_color].pieces:
        if square in piece.moves:
            return True
    return False

class Piece:
    def __init__(self, color: str, name: str, value: int, location: str, id: str):
        self.color = color
        self.name = name
        self.id = id
        self.ascii = ASCII_PIECES.get(f"{color}{name}")  # e.g. "WN", "BK"
        self.value = value
        self.location = location
        self.moves = []
        self.taken = False

    def __str__(self):
        return f"{self.color}{self.name}"
    
    def get_moves(self):
        return self.moves
        

def _parse_last_action(opp_actions):
    """Safely parse last action regardless of whether it's a PlayerAction or legacy string."""
    last = opp_actions[-1]
    if hasattr(last, 'from_tile'):
        return last.from_tile, last.to_tile
    else:
        parts = last.split(' ')
        return parts[0], parts[2] if len(parts) >= 3 else parts[1]

    
class Pawn(Piece):
    def __init__(self, color: str, location: str, i: int):
        id = f'{color}P{i+1}'
        self.starting_location = location

        super().__init__(color, "P", 1, location, id)

    def set_moves(self, board, opp_actions) -> None:

        self.moves = []

        col  = self.location[0]
        row  = int(self.location[1])
        col_i = ord(col)  # 97='a' .. 104='h'

        direction  = 1 if self.color == WHITE else -1
        ep_row     = 5 if self.color == WHITE else 4  # rank where en passant is possible
        cap_row    = row + direction                   # rank of diagonal capture / ep target

        # ── Forward moves ────────────────────────────────────────────────────
        step_one = f"{col}{row + direction}"
        if not _check_tile_occupied(board, step_one):
            self.moves.append(step_one)

            if self.location == self.starting_location:
                step_two = f"{col}{row + 2 * direction}"
                if not _check_tile_occupied(board, step_two):
                    self.moves.append(step_two)

        # ── Diagonal captures ────────────────────────────────────────────────
        if col_i > 97:  # has a file to the left
            take_left = f"{chr(col_i - 1)}{cap_row}"
            if _check_tile_occupied_by_opponent(board, take_left, self.color):
                self.moves.append(take_left)

        if col_i < 104:  # has a file to the right
            take_right = f"{chr(col_i + 1)}{cap_row}"
            if _check_tile_occupied_by_opponent(board, take_right, self.color):
                self.moves.append(take_right)

        # ── En passant ───────────────────────────────────────────────────────
        # Only possible when this pawn is on the en-passant rank and there
        # was a previous move to examine.
        if row == ep_row and opp_actions:
            last  = opp_actions[-1]
            start = last.from_tile
            jump  = last.to_tile

            for delta in (-1, 1):
                if not (97 <= col_i + delta <= 104):
                    continue  # off the board

                target_sq = f"{chr(col_i + delta)}{row}"
                target_pawn = _check_tile_piece(board, target_sq)

                if (
                    target_pawn is not None
                    and target_pawn.name == "P"
                    and target_pawn.color != self.color
                    and jump == target_sq                          # that pawn is the one that just moved
                    and abs(int(jump[1]) - int(start[1])) == 2    # and it was a two-square advance
                ):
                    ep_capture = f"{chr(col_i + delta)}{cap_row}"
                    self.moves.append(ep_capture)


class Knight(Piece):
    def __init__(self, color: str, location: str, i: int):
        id = f'{color}N{i+1}'
        super().__init__(color, "N", 3, location, id)

    def set_moves(self, board, opp_actions):
        
        self.moves = []

        # Get location
        ascii_col = ord(self.location[0])
        row = int(self.location[1])

        # Generate possible moves
        # There are 8 total possible moves
        # Can be 1 or 2 columns left or right, and 2 or 1 rows up or down
        # Is not impacted by peices in path, only by pieces on the destination tile
        if ascii_col - 1 >= 97:
            if row + 2 <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col - 1)}{row + 2}")
                if spot is None or spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - 1)}{row + 2}")
            if row - 2 >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col - 1)}{row - 2}")
                if spot is None or spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - 1)}{row - 2}")
            if ascii_col - 2 >= 97:
                if row + 1 <= 8:
                    spot = _check_tile_piece(board, f"{chr(ascii_col - 2)}{row + 1}")
                    if spot is None or spot.color != self.color:
                        self.moves.append(f"{chr(ascii_col - 2)}{row + 1}")
                if row - 1 >= 1:
                    spot = _check_tile_piece(board, f"{chr(ascii_col - 2)}{row - 1}")
                    if spot is None or spot.color != self.color:
                        self.moves.append(f"{chr(ascii_col - 2)}{row - 1}")

        if ascii_col + 1 <= 104:
            if row + 2 <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col + 1)}{row + 2}")
                if spot is None or spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + 1)}{row + 2}")
            if row - 2 >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col + 1)}{row - 2}")
                if spot is None or spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + 1)}{row - 2}")
            if ascii_col + 2 <= 104:
                if row + 1 <= 8:
                    spot = _check_tile_piece(board, f"{chr(ascii_col + 2)}{row + 1}")
                    if spot is None or spot.color != self.color:
                        self.moves.append(f"{chr(ascii_col + 2)}{row + 1}")
                if row - 1 >= 1:
                    spot = _check_tile_piece(board, f"{chr(ascii_col + 2)}{row - 1}")
                    if spot is None or spot.color != self.color:
                        self.moves.append(f"{chr(ascii_col + 2)}{row - 1}")


class Bishop(Piece):
    def __init__(self, color: str, location: str, i: int):
        id = f'{color}B{i+1}'      
        super().__init__(color, "B", 3, location, id)

    def set_moves(self, board, opp_actions):

        self.moves = []

        # Get location
        ascii_col = ord(self.location[0])
        row = int(self.location[1])

        # Generate possible moves
        # There are 4 total possible directions
        # Can be 1 or more columns left or right, and 1 or more rows up or down
        # Is impacted by pieces in path, and pieces on the destination tile
        # Seperate 4 diagonals into 4 loops, and break if piece in path, add move and break if opponent piece on destination tile
        # Seperating diagonals and compute

        # Left Up Diagonal
        for i in range(1, 8):
            if ascii_col - i >= 97 and row - i >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col - i)}{row - i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col - i)}{row - i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - i)}{row - i}")
                    break
                else:
                    break
            else:
                break

        # Left Down Diagonal
        for i in range(1, 8):
            if ascii_col - i >= 97 and row + i <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col - i)}{row + i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col - i)}{row + i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - i)}{row + i}")
                    break
                else:
                    break
            else:
                break

        # Right Up Diagonal
        for i in range(1, 8):
            if ascii_col + i <= 104 and row - i >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col + i)}{row - i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col + i)}{row - i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + i)}{row - i}")
                    break
                else:
                    break
            else:
                break

        # Right Down Diagonal
        for i in range(1, 8):
            if ascii_col + i <= 104 and row + i <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col + i)}{row + i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col + i)}{row + i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + i)}{row + i}")
                    break
                else:
                    break
            else:
                break
    

class Rook(Piece):
    def __init__(self, color: str, location: str, i: int):
        id = f'{color}R{i+1}'
        self.starting_location = location
        super().__init__(color, "R", 5, location, id)

    def set_moves(self, board, opp_actions):
        self.moves = []

        ascii_col = ord(self.location[0])
        row = int(self.location[1])

        # Generate possible moves
        # There are 4 total possible directions
        # Can be 1 or more columns left or right, and 1 or more rows up or down
        # Is impacted by pieces in path, and pieces on the destination tile

        # Left
        for i in range(1, 8):
            if ascii_col - i >= 97:
                spot = _check_tile_piece(board, f"{chr(ascii_col - i)}{row}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col - i)}{row}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - i)}{row}")
                    break
                else:
                    break
        
        # Right
        for i in range(1, 8):
            if ascii_col + i <= 104:
                spot = _check_tile_piece(board, f"{chr(ascii_col + i)}{row}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col + i)}{row}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + i)}{row}")
                    break
                else:
                    break
        
        # Up
        for i in range(1, 8):
            if row - i >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col)}{row - i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col)}{row - i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col)}{row - i}")
                    break
                else:
                    break

        # Down
        for i in range(1, 8):
            if row + i <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col)}{row + i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col)}{row + i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col)}{row + i}")
                    break
                else:
                    break

    
class Queen(Piece):
    def __init__(self, color: str, location: str, i: int):
        if i > 0:
            id = f'{color}Q{i}'
        else:
            id = f'{color}Q'        
        super().__init__(color, "Q", 9, location, id)

    def set_moves(self, board, opp_actions):
        self.moves = []

        ascii_col = ord(self.location[0])
        row = int(self.location[1])

        # Generate possible moves
        # There are 8 total possible directions
        # Can move in a straight line in any direction
        # Is impacted by pieces in path, and pieces on the destination tile

        # Left Up Diagonal
        for i in range(1, 8):
            if ascii_col - i >= 97 and row - i >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col - i)}{row - i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col - i)}{row - i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - i)}{row - i}")
                    break
                else:
                    break
            else:
                break

        # Left Down Diagonal
        for i in range(1, 8):
            if ascii_col - i >= 97 and row + i <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col - i)}{row + i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col - i)}{row + i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - i)}{row + i}")
                    break
                else:
                    break
            else:
                break

        # Right Up Diagonal
        for i in range(1, 8):
            if ascii_col + i <= 104 and row - i >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col + i)}{row - i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col + i)}{row - i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + i)}{row - i}")
                    break
                else:
                    break
            else:
                break

        # Right Down Diagonal
        for i in range(1, 8):
            if ascii_col + i <= 104 and row + i <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col + i)}{row + i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col + i)}{row + i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + i)}{row + i}")
                    break
                else:
                    break
            else:
                break

        # Left
        for i in range(1, 8):
            if ascii_col - i >= 97:
                spot = _check_tile_piece(board, f"{chr(ascii_col - i)}{row}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col - i)}{row}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - i)}{row}")
                    break
                else:
                    break
        
        # Right
        for i in range(1, 8):
            if ascii_col + i <= 104:
                spot = _check_tile_piece(board, f"{chr(ascii_col + i)}{row}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col + i)}{row}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + i)}{row}")
                    break
                else:
                    break
        
        # Up
        for i in range(1, 8):
            if row - i >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col)}{row - i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col)}{row - i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col)}{row - i}")
                    break
                else:
                    break

        # Down
        for i in range(1, 8):
            if row + i <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col)}{row + i}")
                if spot is None:
                    self.moves.append(f"{chr(ascii_col)}{row + i}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col)}{row + i}")
                    break
                else:
                    break

class King(Piece):

    def __init__(self, color: str, location: str, i: int):
        id = f'{color}K'
        self.starting_location = location
        self.check = False
        self.castle = ""

        super().__init__(color, "K", 0, location, id)

    def set_moves(self, board, opp_actions):

        opp_color = WHITE if self.color == BLACK else BLACK
        self.moves = []
        self.castle = ""

        ascii_col = ord(self.location[0])
        row = int(self.location[1])

        # Generate possible moves
        # There are 8 total possible moves
        # Can move 1 space in any direction
        # Is impacted by pieces on the destination tile
        # Specical Case for Castling

        # Check up
        if row - 1 >= 1:
            spot = _check_tile_piece(board, f"{chr(ascii_col)}{row - 1}")
            if spot is None: 
                self.moves.append(f"{chr(ascii_col)}{row - 1}")
            elif spot.color != self.color:
                self.moves.append(f"{chr(ascii_col)}{row - 1}")

        # Check Down
        if row + 1 <= 8:
            spot = _check_tile_piece(board, f"{chr(ascii_col)}{row + 1}")
            if spot is None: 
                self.moves.append(f"{chr(ascii_col)}{row + 1}")
            elif spot.color != self.color:
                self.moves.append(f"{chr(ascii_col)}{row + 1}")

        # Check all spots to the left
        if ascii_col - 1 >= 97:

            # Straight left
            spot = _check_tile_piece(board, f"{chr(ascii_col - 1)}{row}")
            if spot is None: 
                self.moves.append(f"{chr(ascii_col - 1)}{row}")
            elif spot.color != self.color:
                self.moves.append(f"{chr(ascii_col - 1)}{row}")

            # Diagonal Left Down
            if row + 1 <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col - 1)}{row + 1}")
                if spot is None: 
                    self.moves.append(f"{chr(ascii_col - 1)}{row + 1}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - 1)}{row + 1}")

            # Diagonal Left Up
            if row - 1 >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col - 1)}{row - 1}")
                if spot is None: 
                    self.moves.append(f"{chr(ascii_col - 1)}{row - 1}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - 1)}{row - 1}")

        # Check all spots to the right
        if ascii_col + 1 <= 104:

            # Straight Right
            spot = _check_tile_piece(board, f"{chr(ascii_col + 1)}{row}")
            if spot is None: 
                self.moves.append(f"{chr(ascii_col + 1)}{row}")
            elif spot.color != self.color:
                self.moves.append(f"{chr(ascii_col + 1)}{row}")

            # Diagonal Right Down
            if row + 1 <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col + 1)}{row + 1}")
                if spot is None: 
                    self.moves.append(f"{chr(ascii_col + 1)}{row + 1}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + 1)}{row + 1}")

            # Diagonal Right Up
            if row - 1 >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col + 1)}{row - 1}")
                if spot is None: 
                    self.moves.append(f"{chr(ascii_col + 1)}{row - 1}")
                elif spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + 1)}{row - 1}")


        # Castling
        if self.location == self.starting_location and self.check == False:
            opp_color = BLACK if self.color == WHITE else WHITE

            # Kingside
            if (
                _check_tile_piece(board, f"{chr(ascii_col + 1)}{row}") is None
                and _check_tile_piece(board, f"{chr(ascii_col + 2)}{row}") is None
            ):
                rook = _check_tile_piece(board, f"{chr(ascii_col + 3)}{row}")
                if (
                    rook is not None
                    and rook.name == "R"
                    and rook.color == self.color
                    and rook.starting_location is not None
                ):
                    # NEW: also check king doesn't pass through an attacked square
                    transit_ks = f"{chr(ascii_col + 1)}{row}"
                    if not _square_attacked_by(board, transit_ks, opp_color):
                        self.moves.append(f"{chr(ascii_col + 2)}{row}")
                        self.castle += "KS"

            # Queenside
            if (
                ascii_col - 4 >= 97
                and _check_tile_piece(board, f"{chr(ascii_col - 1)}{row}") is None
                and _check_tile_piece(board, f"{chr(ascii_col - 2)}{row}") is None
                and _check_tile_piece(board, f"{chr(ascii_col - 3)}{row}") is None
            ):
                rook = _check_tile_piece(board, f"{chr(ascii_col - 4)}{row}")
                if (
                    rook is not None
                    and rook.name == "R"
                    and rook.color == self.color
                    and rook.starting_location is not None
                ):
                    # NEW: also check king doesn't pass through an attacked square
                    transit_qs = f"{chr(ascii_col - 1)}{row}"
                    if not _square_attacked_by(board, transit_qs, opp_color):
                        self.moves.append(f"{chr(ascii_col - 2)}{row}")
                        self.castle += "QS"