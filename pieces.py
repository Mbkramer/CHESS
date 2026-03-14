from ascii_art import *

COLOR = {"W": "White", "B": "Black"}

WHITE = 'W'
BLACK = 'B'


PIECES = {
    "P": {"Pawn", 1},
    "N": {"Knight", 3},
    "B": {"Bishop", 3},
    "R": {"Rook", 5},
    "Q": {"Queen", 9},
    "K": {"King", 0},
}

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
        
def _check_tile_occupied(board, tile_id: str) -> bool:
    for row in board:
        for tile in row:
            if tile.id == tile_id:
                return tile.is_occupied()
    return False

def _check_tile_occupied_by_opponent(board, tile_id: str, player_color: str) -> bool:
    for row in board:
        for tile in row:
            if tile.id == tile_id and tile.is_occupied() and tile.piece.color != player_color:
                return True
    return False

def _check_tile_piece(board , tile_id: str) -> Piece:
    for row in board:
        for tile in row:
            if tile.id == tile_id and tile.is_occupied():
                return tile.piece
    return None
    
class Pawn(Piece):
    def __init__(self, color: str, location: str, i: int):
        if i > 0:
            id = f'{color}P{i}'
        else:
            id = f''
        self.starting_location = location

        super().__init__(color, "P", 1, location, id)

    def set_moves(self, board, opp_actions) -> None:

        self.moves: str = []

        # generate possible moves for pawn based on color and location
        # Pawns can move 1 or 2 spaces forward on their first move, and 1 space forward on subsequent moves
        # Pawns can capture diagonally, but cannot move forward if the tile is occupied by any piece
        # TODO Special case for en passant, but will not implement for now
        
        # White Pawn
        if self.color == WHITE:

            # Step Forward
            if self.location == self.starting_location and not _check_tile_occupied(board, f"{self.location[0]}{int(self.location[1]) + 2}"):
                self.moves.append(f"{self.location[0]}{int(self.location[1]) + 2}")
            if not _check_tile_occupied(board, f"{self.location[0]}{int(self.location[1]) + 1}"):
                self.moves.append(f"{self.location[0]}{int(self.location[1]) + 1}")

            # Capture Diagonally
            ascii_value = ord(self.location[0])
            row = int(self.location[1])

            take_left = f"{chr(ascii_value - 1)}{row + 1}"
            take_right = f"{chr(ascii_value + 1)}{row + 1}"

            if ascii_value == 104:
                if _check_tile_occupied_by_opponent(board, take_left, self.color):
                    self.moves.append(take_left)
            elif ascii_value == 97:
                if _check_tile_occupied_by_opponent(board, take_right, self.color):
                    self.moves.append(take_right)
            else:
                if _check_tile_occupied_by_opponent(board, take_left, self.color):
                    self.moves.append(take_left)
                if _check_tile_occupied_by_opponent(board, take_right, self.color):
                    self.moves.append(take_right)

            # En Passant
            if row != 5:
                pass
            else:

                if ascii_value == 104:
                    target_left = f"{chr(ascii_value - 1)}{row}"
                    target_pawn = _check_tile_piece(board, target_left)
                    if target_pawn != None:
                        if target_pawn.name == "P" and opp_actions:
                            parts = opp_actions[-1].split(' ')
                            start, jump = parts[0], parts[-1]
                            if target_pawn.color != self.color and (int(start[1]) - int(jump[1]) == 2):
                                self.moves.append(take_left)

                elif ascii_value == 97:
                    target_right = f"{chr(ascii_value - 1)}{row}"
                    target_pawn = _check_tile_piece(board, target_right)
                    if target_pawn != None:
                        if target_pawn.name == "P" and opp_actions:
                            parts = opp_actions[-1].split(' ')
                            start, jump = parts[0], parts[-1]
                            if target_pawn.color != self.color and (int(start[1]) - int(jump[1]) == 2):
                                self.moves.append(take_right)
                else:
                    
                    target_left = f"{chr(ascii_value - 1)}{row}"
                    target_pawn = _check_tile_piece(board, target_left)
                    if target_pawn != None:
                        if target_pawn.name == "P" and opp_actions:
                            parts = opp_actions[-1].split(' ')
                            start, jump = parts[0], parts[-1]
                            if target_pawn.color != self.color and (int(start[1]) - int(jump[1]) == 2):
                                self.moves.append(take_left)
                            
                    target_right = f"{chr(ascii_value - 1)}{row}"
                    target_pawn = _check_tile_piece(board, target_right)
                    if target_pawn != None:
                        if target_pawn.name == "P" and opp_actions:
                            parts = opp_actions[-1].split(' ')
                            start, jump = parts[0], parts[-1]
                            if target_pawn.color != self.color and (int(start[1]) - int(jump[1]) == 2):
                                self.moves.append(take_right)

                
        # Black Pawn
        elif self.color == BLACK:
            if self.location == self.starting_location and not _check_tile_occupied(board, f"{self.location[0]}{int(self.location[1]) - 2}"):
                self.moves.append(f"{self.location[0]}{int(self.location[1]) - 2}")
            if not _check_tile_occupied(board, f"{self.location[0]}{int(self.location[1]) - 1}"):
                self.moves.append(f"{self.location[0]}{int(self.location[1]) - 1}")
            
            # Capture Diagonally
            ascii_value = ord(self.location[0])
            row = int(self.location[1])

            take_left = f"{chr(ascii_value - 1)}{row - 1}"
            take_right = f"{chr(ascii_value + 1)}{row - 1}"

            if ascii_value == 104:
                if _check_tile_occupied_by_opponent(board, take_left, self.color):
                    self.moves.append(take_left)
            elif ascii_value == 97:
                if _check_tile_occupied_by_opponent(board, take_right, self.color):
                    self.moves.append(take_right)
            else:
                if _check_tile_occupied_by_opponent(board, take_left, self.color):
                    self.moves.append(take_left)
                if _check_tile_occupied_by_opponent(board, take_right, self.color):
                    self.moves.append(take_right)
            
            # En Passant
            if row != 4:
                pass
            else:
                if ascii_value == 104:
                    target_left = f"{chr(ascii_value - 1)}{row}"
                    target_pawn = _check_tile_piece(board, target_left)
                    if target_pawn != None:
                        if target_pawn.name == "P" and opp_actions:
                            parts = opp_actions[-1].split(' ')
                            start, jump = parts[0], parts[-1]
                            if target_pawn.color != self.color and (int(jump[1]) - int(start[1]) == 2):
                                self.moves.append(take_left)

                elif ascii_value == 97:
                    target_right = f"{chr(ascii_value - 1)}{row}"
                    target_pawn = _check_tile_piece(board, target_right)
                    if target_pawn != None:
                        if target_pawn.name == "P" and opp_actions:
                            parts = opp_actions[-1].split(' ')
                            start, jump = parts[0], parts[-1]
                            if target_pawn.color != self.color and (int(jump[1]) - int(start[1]) == 2):
                                self.moves.append(take_right)
                else:
                    
                    target_left = f"{chr(ascii_value - 1)}{row}"
                    target_pawn = _check_tile_piece(board, target_left)
                    if target_pawn != None:
                        if target_pawn.name == "P" and opp_actions:
                            parts = opp_actions[-1].split(' ')
                            start, jump = parts[0], parts[-1]
                            if target_pawn.color != self.color and (int(jump[1]) - int(start[1]) == 2):
                                self.moves.append(take_left)
                            
                    target_right = f"{chr(ascii_value - 1)}{row}"
                    target_pawn = _check_tile_piece(board, target_right)
                    if target_pawn != None:
                        if target_pawn.name == "P" and opp_actions:
                            parts = opp_actions[-1].split(' ')
                            start, jump = parts[0], parts[-1]
                            if target_pawn.color != self.color and (int(jump[1]) - int(start[1]) == 2):
                                self.moves.append(take_right)


class Knight(Piece):
    def __init__(self, color: str, location: str, i: int):
        if i > 0:
            id = f'{color}N{i}'
        else:
            id = f''
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
        if i > 0:
            id = f'{color}B{i}'
        else:
            id = f''        
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
        if i > 0:
            id = f'{color}R{i}'
        else:
            id = f''
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
        if i > 0:
            id = f'{color}K{i}'
        else:
            id = f'{color}K'
        self.starting_location = location
        self.check = False
        self.castle = ""

        super().__init__(color, "K", 0, location, id)

    def set_moves(self, board, opp_actions):

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
            if spot is None or spot.color != self.color:
                self.moves.append(f"{chr(ascii_col)}{row - 1}")

        # Check Down
        if row + 1 <= 8:
            spot = _check_tile_piece(board, f"{chr(ascii_col)}{row + 1}")
            if spot is None or spot.color != self.color:
                self.moves.append(f"{chr(ascii_col)}{row + 1}")

        # Check all spots to the left
        if ascii_col - 1 >= 97:

            # Straight left
            spot = _check_tile_piece(board, f"{chr(ascii_col - 1)}{row}")
            if spot is None or spot.color != self.color:
                self.moves.append(f"{chr(ascii_col - 1)}{row}")

            # Diagonal Left Down
            if row + 1 <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col - 1)}{row + 1}")
                if spot is None or spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - 1)}{row + 1}")

            # Diagonal Left Up
            if row - 1 >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col - 1)}{row - 1}")
                if spot is None or spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col - 1)}{row - 1}")

        # Check all spots to the right
        if ascii_col + 1 <= 104:

            # Straight Right
            spot = _check_tile_piece(board, f"{chr(ascii_col + 1)}{row}")
            if spot is None or spot.color != self.color:
                self.moves.append(f"{chr(ascii_col + 1)}{row}")

            # Diagonal Right Down
            if row + 1 <= 8:
                spot = _check_tile_piece(board, f"{chr(ascii_col + 1)}{row + 1}")
                if spot is None or spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + 1)}{row + 1}")

            # Diagonal Right Up
            if row - 1 >= 1:
                spot = _check_tile_piece(board, f"{chr(ascii_col + 1)}{row - 1}")
                if spot is None or spot.color != self.color:
                    self.moves.append(f"{chr(ascii_col + 1)}{row - 1}")


            # Castling
            if self.location == self.starting_location:
                # Check for Kingside Castling
                if _check_tile_piece(board, f"{chr(ascii_col + 1)}{row}") is None and _check_tile_piece(board, f"{chr(ascii_col + 2)}{row}") is None:
                    rook = _check_tile_piece(board, f"{chr(ascii_col + 3)}{row}")
                    if rook is not None and rook.name == "R" and rook.color == self.color:
                        self.moves.append(f"{chr(ascii_col + 2)}{row}")
                        self.castle = "KS"

                # Check for Queenside Castling
                if _check_tile_piece(board, f"{chr(ascii_col - 1)}{row}") is None and _check_tile_piece(board, f"{chr(ascii_col - 2)}{row}") is None and _check_tile_piece(board, f"{chr(ascii_col - 3)}{row}") is None:
                    rook = _check_tile_piece(board, f"{chr(ascii_col - 4)}{row}")
                    if rook is not None and rook.name == "R" and rook.color == self.color:
                        self.moves.append(f"{chr(ascii_col - 2)}{row}")
                        self.castle = "QS"

