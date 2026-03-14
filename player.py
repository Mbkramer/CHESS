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
    
    def take_piece(self, piece: Piece):
        self.taken_pieces.append(piece)
        self.taken_pieces_str += f" {piece.name}"
        self.points += piece.value
    
    def _log_action(self, action: str):
        self.actions.append(action)

    def update_moves(self, board, opp_actions) -> None:
        if self.checked:
            # Build a set of (piece_location, move) pairs
            valid = set(self.possible_moves)
            for piece in self.pieces:
                piece.set_moves(board, opp_actions)
                piece.moves = [move for move in piece.moves
                            if (piece.location, move) in valid]  # ← filter by pair
        else:
            self.possible_moves = []
            for piece in self.pieces:
                piece.set_moves(board, opp_actions)
                self.possible_moves += piece.moves


    def _show_moves(self) -> None:
        for piece in self.pieces:
            if len(piece.moves) > 0:
                print(f"{COLOR[self.color]} {piece.name} at {piece.location} can move to: {piece.moves}")

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