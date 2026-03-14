import sys
from chess_board import ChessBoard

ROWS = ["1", "2", "3", "4", "5", "6", "7", "8"]
COLUMNS = ["a", "b", "c", "d", "e", "f", "g", "h"]

COLORS = {"W": "White", "B": "Black"}

WHITE = 'W'
BLACK = 'B'

def player_menu(chess_board, turn) -> bool:

    print("\033c", end="", flush=True)
    print(f"{COLORS[turn]} turn.\n")

    chess_board._draw_ascii_board()

    print("\nSelect a move from the list below")
    print("Type: 'e2 e4' (without quotes) and press Enter to log a move.")
    print("Type: 'exit'  (without quotes) and press Enter to quit the game.")

    if chess_board.players[turn].mated:
        print(f"MATED: {COLORS[turn]} has been mated...\n")
        print("GAME OVER")
        return False
    
    elif chess_board.players[turn].checked:
        print(f"CHECKED: {COLORS[turn]} protect your king...")

    print("\nAvailable moves:")
    chess_board.players[turn]._show_moves()

    need_input = True

    while need_input:

        user_input = input("Type your move below: \n")

        if user_input.lower() == 'exit':
            return False
        
        try:
            user_input = user_input.strip()
            from_tile, to_tile = user_input.split(' ')

            for piece in chess_board.players[turn].pieces:
                if piece.location == from_tile and to_tile in piece.moves:
                    print(f"Moving {piece} from {from_tile} to {to_tile}")
                    chess_board._move_piece(piece, to_tile)
                    chess_board._update_tiles()
                    return True
            
            print(f"Move from {from_tile} to {to_tile} is not valid for {COLORS[turn]}.")
            print ("Invalid move. Please select a valid move from the list.")
            
        except ValueError:
            print("Invalid input format. Please enter moves in the format 'e2 e4'.")
        
    return True


def game_loop(chess_board: ChessBoard):

    running = True
    turn = WHITE

    while running:
        running = player_menu(chess_board, turn)
        turn = BLACK if turn == WHITE else WHITE


def start_game():
    print("Welcome to the Chess Engine!")

    print("Chess Board")
    chess_board = ChessBoard()

    result = str.lower(input("Type start to begin the game: "))
    while result != 'start':
        result = str.lower(input("Press Enter to start the game..."))

    if result == 'start':
        print("Game Started!")
        game_loop(chess_board)
        