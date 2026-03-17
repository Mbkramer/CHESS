import sys
import random
from chess_board import ChessBoard
from bot import best_move
from opening_book import REPERTOIRES, BALANCED, SOLID, AGRESSIVE, TACTICAL

ROWS = ["1", "2", "3", "4", "5", "6", "7", "8"]
COLUMNS = ["a", "b", "c", "d", "e", "f", "g", "h"]

COLORS = {"W": "White", "B": "Black"}

WHITE = 'W'
BLACK = 'B'

def player_menu(chess_board, turn) -> bool:

    opp = BLACK if turn == WHITE else WHITE

    #TODO TEMP FOR SHOWING ALL LIVE GAMES print("\033c", end="", flush=True)
    print(f"{COLORS[turn]} turn.\n")

    chess_board._draw_ascii_board()

    if len(chess_board.players[opp].actions) > 0:
        print(f"\n{opp} {chess_board.players[opp].actions[-1]}\n")

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
    chess_board.players[turn]._show_moves(chess_board)

    while True:
        user_input = input("Type your move below: \n").strip()

        if user_input.lower() == "exit":
            return False

        try:
            from_tile, to_tile = user_input.split()
        except ValueError:
            print("Invalid input format. Please enter moves in the format 'e2 e4'.")
            continue

        for piece in chess_board.players[turn].pieces:
            if piece.location == from_tile and to_tile in piece.moves:
                print(f"Moving {piece} from {from_tile} to {to_tile}")
                try:
                    chess_board._move_piece(piece, to_tile)
                    chess_board._update_tiles()
                except Exception as e:
                    print(f"POST-MOVE ERROR: {e}")
                    raise
                return True

        print(f"Move from {from_tile} to {to_tile} is not valid for {COLORS[turn]}.")
        print("Invalid move. Please select a valid move from the list.")


def game_loop(chess_board: ChessBoard, game_input):

    running = True
    turn = WHITE

    if game_input[0] == 'bot':
        bot_oppening = random.randint(0, 3)
        repertoire = BALANCED

        if bot_oppening == 0:
            repertoire = BALANCED
        elif bot_oppening == 1:
            repertoire = SOLID
        elif bot_oppening == 2:
            repertoire = AGRESSIVE
        elif bot_oppening == 3:
            repertoire = TACTICAL

        bot_color = BLACK if game_input[1] == WHITE else WHITE

        print(f"TEMP: BOT REP: {repertoire}")

    # 2p Game
    if game_input[0] == '2p':
        while running:
            running = player_menu(chess_board, turn)
            turn = BLACK if turn == WHITE else WHITE

    # Player Vs Bot Game
    elif game_input[0] == 'bot':


        while running:
            
            # If player turn show game menu
            if game_input[1] == turn:
                running = player_menu(chess_board, turn)

            # Bot Turn
            else:

                if len(chess_board.players[bot_color].possible_moves) == 0:
                    print(f"MATED: {COLORS[bot_color]} has been mated...\n")
                    print("GAME OVER")
                    running = False
                    return
                
                print("Waiting on bot move..\n")

                move = best_move(chess_board, bot_color, repertoire_name=repertoire, depth=3)
                if move:
                    from_sq, to_sq = move
                    piece = next(p for p in chess_board.players[turn].pieces 
                                if p.location == from_sq)
                    chess_board._move_piece(piece, to_sq)
                    chess_board._update_tiles()

            turn = BLACK if turn == WHITE else WHITE


def start_game():
    print("Welcome to the Chess Engine!\n")

    chess_board = ChessBoard()

    game_input = []

    while len(game_input) != 2:

        if len(game_input) == 0:
            print("Would you like to play 2P or against a bot?")
            user_input = str.lower(input("Type '2P' below for 2 Player pass and play. \nType 'bot' to play against a bot.\nType 'exit' at anytime to leave the game.\n")).strip()

            if user_input == '2p':
                game_input.append(user_input)
            elif user_input == 'bot':
                game_input.append(user_input)

        elif len(game_input) == 1:
            print(f"\nGreat! Its a {game_input[0]} game.\n")
            print(f"Would you like to play as White, Black, or Random?")
            user_input = str.lower(input("Type 'w' below for White.\nType 'b below for Black\nType 'r' below for Random\nType 'exit' at anytime to leave the game.\n"))

            if user_input == 'w':
                game_input.append(WHITE)
            elif user_input == 'b':
                game_input.append(BLACK)
            elif user_input == 'r':
                
                rand = random.randint(0, 1)
                if rand == 0:
                    game_input.append(WHITE)
                else:
                    game_input.append(BLACK)

        if user_input == 'exit':
            print("GAME OVER\n")
            return

    
    print(f"\nAlright! This is a {game_input[0]} game.. you will be playing as {COLORS[game_input[1].upper()]}")
    hold = str.lower(input("\nEnter anything other than exit in terminal to start the game"))
    if hold == 'exit':
        print("GAME OVER\n")
        return 

    print("Game Started!")
    game_loop(chess_board, game_input)
        