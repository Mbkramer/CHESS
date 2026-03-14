import copy
from pieces import Piece, Pawn, Knight, Bishop, Rook, Queen, King
from ascii_art import ASCII_PIECES
from player import Player

ROWS = ["1", "2", "3", "4", "5", "6", "7", "8"]
COLUMNS = ["a", "b", "c", "d", "e", "f", "g", "h"]

TYLE_COLORS = {"W": "White", "B": "Black"}

WHITE = 'W'
BLACK = 'B'

COLORS = [WHITE, BLACK]

class Tile:
    def __init__(self, column: str, color: str, row: str):
        self.id = f"{column}{row}"
        self.color = color

        if self.color == BLACK:
            self.ascii = ASCII_PIECES['EMPTY_DARK']
        elif self.color == WHITE:
            self.ascii = ASCII_PIECES['EMPTY_LIGHT']

        self.piece = None
    
    def __str__(self):
        if self.piece:
            return str(self.piece)
        else:
            return self.id
    
    def is_occupied(self):
        return self.piece is not None
    
    def place_piece(self, piece: Piece):
        self.piece = piece
        self.ascii = piece.ascii

    def remove_piece(self):
        self.piece = None

        if self.color == BLACK:
            self.ascii = ASCII_PIECES['EMPTY_DARK']
        elif self.color == WHITE:
            self.ascii = ASCII_PIECES['EMPTY_LIGHT']

class ChessBoard:

    """
    Chess Board

    """

    # Initialize chess board with 8x8 tiles and starting piece positions for both players
    def __init__(self):
        
        self.board = []
        self._init_board_tiles()

        self.players = {
            WHITE: Player(WHITE),
            BLACK: Player(BLACK)
        }

        self._update_tiles()
        self.players[WHITE].update_moves(self.board, [])
        self.players[BLACK].update_moves(self.board, [])


    # Initialize board tiles with alternating colors and unique IDs
    def _init_board_tiles(self) -> None:

        for row in ROWS:
            board_row = []
            for column in COLUMNS:
                color = "W" if (ROWS.index(row) + COLUMNS.index(column)) % 2 == 0 else "B"
                board_row.append(Tile(column, color, row))
            self.board.append(board_row)


    """
    Print Board
    
    """

    # Display current board state with pieces and tile IDs
    def _show_board(self):
        print("     CURRENT BOARD     ")
        for row in self.board:
            print(" ".join([str(tile) for tile in row]))

    # Ascii helper
    def _print_side_by_side(self, *pieces, sep="     ", index=""):
        rows = [piece.split("\n") for piece in pieces]
        for i, lines in enumerate(zip(*rows)):
            lines = list(lines)
            if i == 2:
                lines.insert(0, f"  {index}  ")
            else:
                lines.insert(0, f"     ")
            print(sep.join(lines))

    # Display current board state with ascii art 
    def _draw_ascii_board(self):
        print(f"\n          WHITE          POINTS: {self.players[WHITE].points}          PIECES TAKEN: {self.players[WHITE].taken_pieces_str}            ")
        print("            a         b         c         d         e         f         g         h         \n")
        for row in self.board:
            rank = row[0].id[1]
            self._print_side_by_side(*[tile.ascii for tile in row], index=rank)
        print(f"\n          BLACK          POINTS: {self.players[BLACK].points}          PIECES TAKEN: {self.players[BLACK].taken_pieces_str}            ")

    
    """
    Assess Board and player moves

    """

    # Check if board tile is occupied by a piece
    def _check_tile_occupied(self, tile_id: str) -> bool:
        for row in self.board:
            for tile in row:
                if tile.id == tile_id:
                    return tile.is_occupied()
        return False

    # Update board tiles with all current piece locations
    def _update_tiles(self) -> None:
        for piece in self.players[WHITE].pieces + self.players[BLACK].pieces:
            for row in self.board:
                for tile in row:
                    if tile.id == piece.location:
                        tile.place_piece(piece)
                    elif tile.piece and tile.piece.location != tile.id:
                        tile.remove_piece()

        # Update All Moves
        for color in COLORS:
            opp = BLACK if color == WHITE else WHITE
            self.players[color].update_moves(self.board, self.players[opp].actions)

        # Update ALL moves first before testing check
        for color in COLORS:
            self._cut_illegal_moves(color)   

        # Reset and check mates
        for color in COLORS:
            self.players[color].checked = False   
            self.players[color].mated = False
            if self._test_check(color):
                self.players[color].checked = True
                self.players[color].possible_moves = self._checked(color)
                if len(self.players[color].possible_moves) == 0:
                    self.players[color].mated = True

    # Remove any move that leaves own king in check.
    def _cut_illegal_moves(self, color) -> None:
        opp = BLACK if color == WHITE else WHITE

        for piece in self.players[color].pieces:
            legal = []
            for move in piece.moves:
                test_board = copy.deepcopy(self)
                test_piece = next(p for p in test_board.players[color].pieces
                                if p.location == piece.location)
                test_board._move_piece(test_piece, move, simulate=True)
                test_board.players[opp].update_moves(test_board.board, self.players[opp].actions)

                if not test_board._test_check(color):
                    legal.append(move)

            piece.moves = legal

    # Handle Check and Check Mate
    def _test_check(self, color) -> bool:

        if color == WHITE:
            opp_color = BLACK
        elif color == BLACK:
            opp_color = WHITE

        for piece in self.players[color].pieces:
            if piece.name == "K":
                for opp_piece in self.players[opp_color].pieces:
                    if piece.location in opp_piece.moves:
                        piece.check = True
                        return True
                return False
                    
        return False

    def _checked(self, color) -> list:
        moves_out = []
        opp = BLACK if color == WHITE else WHITE

        for piece in self.players[color].pieces:
            for move in piece.moves:
                test_board = copy.deepcopy(self)
                test_piece = next(p for p in test_board.players[color].pieces
                                if p.location == piece.location)

                test_board._move_piece(test_piece, move, simulate=True)
                test_board.players[opp].update_moves(test_board.board, self.players[opp].actions)

                if not test_board._test_check(color):
                    moves_out.append((piece.location, move)) 

        return moves_out



    """
    Manipulate the board
    
    """

    # Move piece from one tile to another, updating piece location and board state
    def _move_piece(self, piece: Piece, to_tile_id: str, simulate: bool = False) -> None:

        from_tile_id = piece.location

        for row in self.board:
            for tile in row:
                if tile.id == from_tile_id:
                    tile.remove_piece()
                elif tile.id == to_tile_id:

                    # Castle
                    if not tile.is_occupied() and piece.name == "K":

                        # Castle King Side
                        if piece.castle == "KS":
                            piece.starting_location == None # No more castling
                            if piece.color == BLACK:
                                self.board[7][5].place_piece(self.board[7][7].piece)
                                self.board[7][7].remove_piece()
                                self.board[7][5].piece.location = self.board[7][5].id
                                self.board[7][6].place_piece(piece)
                                piece.location = to_tile_id
                            if piece.color == WHITE:
                                self.board[0][5].place_piece(self.board[0][7].piece)
                                self.board[0][7].remove_piece
                                self.board[0][5].piece.location = self.board[0][5].id
                                self.board[0][6].place_piece(piece)
                                piece.location = to_tile_id
                                
                        # Castle Queen Side
                        if piece.castle == "QS":
                            piece.starting_location == None # No more castling
                            if piece.color == BLACK:
                                self.board[7][4].place_piece(self.board[7][0].piece)
                                self.board[7][0].remove_piece
                                self.board[7][4].piece.location = self.board[7][3].id
                                self.board[7][3].place_piece(piece)
                                piece.location = to_tile_id
                            if piece.color == WHITE:
                                self.board[0][4].place_piece(self.board[0][0].piece)
                                self.board[0][0].remove_piece
                                self.board[0][4].piece.location = self.board[0][3].id
                                self.board[0][3].place_piece(piece)
                                piece.location = to_tile_id
                        
                        # Just Moving King
                        if piece.castle == "":
                            piece.starting_location == None # No more castling
                            self.players[piece.color]._log_action(f"{from_tile_id} {to_tile_id}")
                            tile.place_piece(piece)
                            piece.location = to_tile_id

                    # Pawn Special Case (Promotion)
                    elif piece.name == "P" and ((piece.color == WHITE and to_tile_id[1] == "8") or (piece.color == BLACK and to_tile_id[1] == "1")):

                        if simulate:
                            # During simulation just move the pawn, no promotion
                            tile.place_piece(piece)
                            piece.location = to_tile_id
                            return

                        # In case of capture before promotion
                        if tile.is_occupied() and tile.piece.color != piece.color:
                            captured_piece = tile.piece
                            opponent_color = BLACK if piece.color == WHITE else WHITE
                            self.players[piece.color].take_piece(captured_piece)
                            self.players[opponent_color].pieces.remove(captured_piece)

                        # Promote pawn to Q, R, N, or B
                        # Inheret piece moves
                        promtions = ['Q', 'R', 'N', 'B']
                        promotion = ''
                        while promotion not in promtions:
                            promotion = str.upper(input("Promoted Pawn: \nType 'Q' for Queen \nType 'R' for Rook \nType 'N' for Night \nType 'B' for Bishop \n").strip())

                        # Inherit Queen
                        if promotion == 'Q':
                            self.players[piece.color]._log_action(f"{from_tile_id} {to_tile_id}")
                            queen = Queen(piece.color, to_tile_id, 0)
                            queen.id = piece.id # Still pawn id tracking
                            queen.value = piece.id # Still pawn point value
                            tile.place_piece(queen)
                            self.players[piece.color].pieces.append(queen) # Add Queen
                            self.players[piece.color].pieces.remove(piece) # Remove Pawn

                        # Inherit Rook
                        elif promotion == 'R':
                            self.players[piece.color]._log_action(f"{from_tile_id} {to_tile_id}")
                            rook = Rook(piece.color, to_tile_id, 0)
                            rook.id = piece.id # Still pawn id tracking
                            rook.value = piece.id # Still pawn point value
                            tile.place_piece(rook)
                            self.players[piece.color].pieces.append(rook) # Add Rook
                            self.players[piece.color].pieces.remove(piece) # Remove Pawn

                        # Inherit Knight
                        elif promotion == 'K':
                            self.players[piece.color]._log_action(f"{from_tile_id} {to_tile_id} {promotion}")
                            knight = Knight(piece.color, to_tile_id, 0)
                            knight.id = piece.id # Still pawn id tracking
                            knight.value = piece.id # Still pawn point value
                            tile.place_piece(knight)
                            self.players[piece.color].pieces.append(knight) # Add Knight
                            self.players[piece.color].pieces.remove(piece) # Remove Pawn

                        # Inherit Bishop
                        elif promotion == 'B':
                            self.players[piece.color]._log_action(f"{from_tile_id} {to_tile_id} {promotion}")
                            bishop = Bishop(piece.color, to_tile_id, 0)
                            bishop.id = piece.id # Still pawn id tracking
                            bishop.value = piece.id # Still pawn point value
                            tile.place_piece(bishop)
                            self.players[piece.color].pieces.append(bishop) # Add Bishop
                            self.players[piece.color].pieces.remove(piece) # Remove Pawn


                    # Standard Capture
                    elif tile.is_occupied() and tile.piece.color != piece.color:
                        captured_piece = tile.piece
                        opponent_color = BLACK if piece.color == WHITE else WHITE
                        self.players[piece.color].take_piece(captured_piece)
                        self.players[opponent_color].pieces.remove(captured_piece)
                        self.players[piece.color]._log_action(f"{from_tile_id} {to_tile_id} {captured_piece.color}{captured_piece.name}")

                        tile.place_piece(piece)
                        piece.location = to_tile_id

                    # Standard Open Space Move
                    else:
                        self.players[piece.color]._log_action(f"{from_tile_id} {to_tile_id}")
                        tile.place_piece(piece)
                        piece.location = to_tile_id
