from pieces import Piece, Pawn, Knight, Bishop, Rook, Queen, King

NUM_PAWNS: int = 8
NUM_KNIGHTS: int = 2
NUM_BISHOPS: int = 2
NUM_ROOKS: int = 2
NUM_QUEENS: int = 1
NUM_KINGS: int = 1

ROWS = ["1", "2", "3", "4", "5", "6", "7", "8"]
COLUMNS = ["a", "b", "c", "d", "e", "f", "g", "h"]

COLOR = {"W": "White", "B": "Black"}

WHITE = 'W'
BLACK = 'B'

class PlayerAction:
    def __init__(self, from_tile: str, to_tile: str, piece: Piece, 
                 captured: Piece = None, castle: str = None, promotion: str = None):
        
        self.from_tile  = from_tile
        self.to_tile    = to_tile
        self.piece_id   = piece.id       
        self.piece_name = piece.name
        self.captured   = captured.id if captured else None
        self.castle     = castle
        self.promotion  = promotion       

    def __str__(self):
        base = f"{self.piece_id} {self.from_tile} to {self.to_tile}"
        if self.captured:
            base += f" takes {self.captured}"
        if self.castle:
            base += f" castle {self.castle}"
        if self.promotion:
            base += f" promoted to {self.promotion}"
        return base

class Player: 
    def __init__(self, color: str):
        self.color = color
        self.actions = []
        self.pieces = []
        self.taken_pieces = []
        self.taken_pieces_str = ""
        self.points = 0

        self.possible_moves = []
        self.checked = False
        self.mated = False

        self._init_pieces()

    def __str__(self):
        return f"{COLOR[self.color]} Pieces: {[str(piece) for piece in self.pieces]} taken_pieces: {[str(piece) for piece in self.taken_pieces]}"
    
    def take_piece(self, piece: Piece, simulate: bool = True):
        if simulate:
            return
        self.taken_pieces.append(piece)
        self.taken_pieces_str += f" {piece.name}"
        self.points += piece.value
    
    def _log_action(self, action: str):
        self.actions.append(action)

    def _clear_actions(self):
        for piece in self.pieces:
            piece.atackers = set()
            piece.attacking = set()
            piece.defenders = set()

    def update_moves(self, chess_board, opp_actions) -> None:
        # Generate raw pseudo-legal moves only
        for piece in self.pieces:
            piece.set_moves(chess_board, opp_actions)

        # Rebuild aggregate move list from raw per-piece moves
        self.possible_moves = []
        for piece in self.pieces:
            for move in piece.moves:
                self.possible_moves.append((piece.location, move))


    def _show_moves(self, chess_board) -> None:

        for piece in self.pieces:
            if len(piece.moves) > 0:
                moves_str = ""
                for move in piece.moves:
                    if move == chess_board.black_king_location or move == chess_board.white_king_location:
                        continue
                    moves_str += f"{move} "
                print(f"{COLOR[self.color]} {piece.name} at {piece.location} can move to: {moves_str}")

    def _init_pieces(self) -> None:

        for i in range(NUM_PAWNS):
            pawn = Pawn(self.color, f"{COLUMNS[i]}{'2' if self.color == WHITE else '7'}", i)
            self.pieces.append(pawn)
        
        for i in range(NUM_KNIGHTS):
            knight = Knight(self.color, f"{COLUMNS[1 + 5*i]}{'1' if self.color == WHITE else '8'}", i)
            self.pieces.append(knight)
        
        for i in range(NUM_BISHOPS):
            bishop = Bishop(self.color, f"{COLUMNS[2 + 3*i]}{'1' if self.color == WHITE else '8'}", i)
            self.pieces.append(bishop)
        
        for i in range(NUM_ROOKS):
            rook = Rook(self.color, f"{COLUMNS[0 + 7*i]}{'1' if self.color == WHITE else '8'}", i)
            self.pieces.append(rook)

        queen = Queen(self.color, f"{COLUMNS[3]}{'1' if self.color == WHITE else '8'}", i=0)
        king = King(self.color, f"{COLUMNS[4]}{'1' if self.color == WHITE else '8'}", i=0)

        self.pieces.append(queen)
        self.pieces.append(king)