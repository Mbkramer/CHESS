import sys
import time
import random
from chess_board import ChessBoard
from bot import best_move
from opening_book import REPERTOIRES, BALANCED, SOLID, AGRESSIVE, TACTICAL
import copy

ROWS = ["1", "2", "3", "4", "5", "6", "7", "8"]
COLUMNS = ["a", "b", "c", "d", "e", "f", "g", "h"]

COLORS = {"W": "White", "B": "Black"}

WHITE = 'W'
BLACK = 'B'

def fmt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60

    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    parts.append(f"{s:.1f}s")

    return " ".join(parts)

def player_menu(chess_board, move_times, turn) -> bool:

    opp = BLACK if turn == WHITE else WHITE

    chess_board._draw_ascii_board()

    if len(chess_board.players[opp].actions) > 0:
        print(f"\nLAST MOVE: {COLORS[opp]} {chess_board.players[opp].actions[-1]}")
        print(f"WHITE        POINTS: {chess_board.players[WHITE].points}        PIECES TAKEN: {chess_board.players[WHITE].taken_pieces_str}")
        print(f"BLACK        POINTS: {chess_board.players[BLACK].points}        PIECES TAKEN: {chess_board.players[BLACK].taken_pieces_str}")
        print(f"TIME:        {COLORS[WHITE]}: {fmt_time(move_times[WHITE])}        {COLORS[BLACK]}: {fmt_time(move_times[BLACK])}\n")

    print(f"{COLORS[turn]} select a move from the list below")
    print("Type: 'from_tile to_tile' (without quotes) and press Enter to log a move. example: e2 e4")
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

    white_move_time = 0
    black_move_time = 0
    last_move_times = {
        WHITE: white_move_time, 
        BLACK: black_move_time
    }

    if game_input[2] != None:
        white_shot_clock = game_input[2]
        black_shot_clock = game_input[2]
        shot_clocks = {
            WHITE: white_shot_clock, 
            BLACK: black_shot_clock
        }

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

    # 2p Game
    if game_input[0] == '2p':

        while running:

            start_time = time.time()
            if game_input[2] == None:
                running = player_menu(chess_board, last_move_times, turn)
            elif game_input[2] != None:
                running = player_menu(chess_board, shot_clocks, turn)

            end_time = time.time()

            # Capture move times
            if turn == WHITE:
                last_move_times[WHITE] = end_time - start_time
            elif turn == BLACK:
                last_move_times[BLACK] = end_time - start_time

            if turn == WHITE and game_input[2] != None:
                shot_clocks[WHITE] -= last_move_times[WHITE]
            elif turn == BLACK and game_input[2] != None:
                shot_clocks[BLACK] -= last_move_times[BLACK]

            if game_input[2] != None:
                if shot_clocks[WHITE] <= 0 or shot_clocks[BLACK] <= 0:
                    running = False
                    if shot_clocks[WHITE]<=0:
                        print(f"White is out of time. \nWHITE SHOT CLOCK: {fmt_time(shot_clocks[WHITE])}")
                    elif shot_clocks[BLACK]<=0:
                        print(f"White is out of time. \nBLACK SHOT CLOCK: {fmt_time(shot_clocks[BLACK])}")
                    print(f"GAME OVER")

            turn = BLACK if turn == WHITE else WHITE

    # Player Vs Bot Game
    elif game_input[0] == 'bot':

        while running:
            
            # If player turn show game menu
            if game_input[1] == turn:
                start_time = time.time()

                if len(game_input) == 3:
                    print("\033c", end="", flush=True)
                elif len(game_input) == 4:
                    if game_input[3] == 'debug':
                        pass
                    elif game_input[3] == 'DEBUG':
                        pass
                    else:
                        print("\033c", end="", flush=True)


                if game_input[2] == None:
                    running = player_menu(chess_board, last_move_times, turn)
                elif game_input[2] != None:
                    running = player_menu(chess_board, shot_clocks, turn)


                end_time = time.time()

                # Capture move times
                if turn == WHITE:
                    last_move_times[WHITE] = end_time - start_time
                elif turn == BLACK:
                    last_move_times[BLACK] = end_time - start_time
                if turn == WHITE and game_input[2] != None:
                    shot_clocks[WHITE] -= last_move_times[WHITE]
                elif turn == BLACK and game_input[2] != None:
                    shot_clocks[BLACK] -= last_move_times[BLACK]

            # Bot Turn
            else:

                if len(chess_board.players[bot_color].possible_moves) == 0:
                    print(f"MATED: {COLORS[bot_color]} has been mated...\n")
                    print("GAME OVER")
                    running = False
                    return
                
                print("Waiting on bot move..\n")

                # Cap bot decions making time
                move_budget = 120 # Generouse 2 minutes
                depth = 3

                # Under a shot clock
                if game_input[2] != None:
                    move_budget = min(60.0, max(5.0, shot_clocks[turn] / 10))
                    if shot_clocks[turn] < .60 * game_input[2]:
                        move_budget = min(move_budget, max(3.0, shot_clocks[turn] / 8))
                    if shot_clocks[turn] < .2 * game_input[2]:
                        depth = 2

                start_time = time.time()

                if len(game_input) == 4: # Debug mode
                    if game_input[3] == "debug":
                        move = best_move(chess_board, turn, depth=depth, debug=1, time_budget=move_budget)
                    elif game_input[3] == "DEBUG":
                        move = best_move(chess_board, turn, depth=depth, debug=2, debug_max_children=4, time_budget=move_budget)
                    else:
                        move = best_move(chess_board, turn, depth=depth, time_budget=move_budget)
                else:  # not debug normal mode
                    move = best_move(chess_board, turn, depth=depth, time_budget=move_budget)

                if move:
                    from_sq, to_sq = move
                    piece = next(p for p in chess_board.players[turn].pieces 
                                if p.location == from_sq)
                    chess_board._move_piece(piece, to_sq)
                    chess_board._update_tiles()
                
                end_time = time.time()

                # Capture move times
                if turn == WHITE:
                    last_move_times[WHITE] = end_time - start_time
                elif turn == BLACK:
                    last_move_times[BLACK] = end_time - start_time

                if turn == WHITE and game_input[2] != None:
                    shot_clocks[WHITE] -= last_move_times[WHITE]
                elif turn == BLACK and game_input[2] != None:
                    shot_clocks[BLACK] -= last_move_times[BLACK]

            if game_input[2] != None:
                if shot_clocks[WHITE] <= 0 or shot_clocks[BLACK] <= 0:
                    running = False

                    if shot_clocks[WHITE]<=0:
                        print(f"White is out of time. \nWHITE SHOT CLOCK: {fmt_time(shot_clocks[WHITE])}")
                    elif shot_clocks[BLACK]<=0:
                        print(f"White is out of time. \nBLACK SHOT CLOCK: {fmt_time(shot_clocks[BLACK])}")
                    print(f"GAME OVER")
            
            turn = BLACK if turn == WHITE else WHITE


    # Player Vs Bot Game
    elif game_input[0] == 'aid':

        while running:

            if len(game_input) == 3:
                print("\033c", end="", flush=True)
            elif len(game_input) == 4:
                if game_input[3] == 'debug':
                    pass
                elif game_input[3] == 'DEBUG':
                    pass
                else:
                    print("\033c", end="", flush=True)
            else:
                print("\033c", end="", flush=True)

            # If player turn get bot recomendation
            if game_input[1] == turn:

                if len(chess_board.players[turn].possible_moves) == 0:
                    print(f"MATED: {COLORS[turn]} has been mated...\n")
                    print("GAME OVER")
                    running = False
                    return
                
                print("Waiting on bot recomendation..\n")
                bot_board = copy.deepcopy(chess_board)

                # Cap bot decions making time
                move_budget = 120 # Generouse 2 minutes
                depth = 3

                # Under a shot clock
                if game_input[2] != None:
                    move_budget = min(60.0, max(5.0, shot_clocks[turn] / 10))
                    if shot_clocks[turn] < .60 * game_input[2]:
                        move_budget = min(move_budget, max(3.0, shot_clocks[turn] / 8))
                    if shot_clocks[turn] < .2 * game_input[2]:
                        depth = 2

                start_time = time.time()

                # Bot recomendation
                if len(game_input) == 4: # Debug mode
                    if game_input[3] == "debug":
                        move = best_move(bot_board, turn, depth=depth, debug=1, time_budget=move_budget)
                    elif game_input[3] == "DEBUG":
                        move = best_move(bot_board, turn, depth=depth, debug=2, debug_max_children=4, time_budget=move_budget)
                    else:
                        move = best_move(bot_board, turn, depth=depth, time_budget=move_budget)
                else:  # not debug normal mode
                    move = best_move(bot_board, turn, depth=depth, time_budget=move_budget)

                if move:
                    from_sq, to_sq = move
                    print(f"Bot recomendation: {from_sq} {to_sq}")

                # log move:
                waiting = True
                while waiting:
                    user_input = input("Type: 'from_tile to_tile' (without quotes) and press Enter to log your played move. example: e2 e4\n")
                    if user_input.lower() == "exit":
                        return False

                    try:
                        from_tile, to_tile = user_input.split()
                    except Exception as e:
                        print(e)
                        continue

                    try:
                        piece = next(p for p in chess_board.players[turn].pieces 
                                    if p.location == from_tile)
                        chess_board._move_piece(piece, to_tile)
                        chess_board._update_tiles()
                        print(chess_board.actions[-1])
                        waiting = False
                    except Exception as e:
                        print("Move failed.. ")
                        print(e)
                
                end_time = time.time()

                # Capture move times
                if turn == WHITE:
                    last_move_times[WHITE] = end_time - start_time
                elif turn == BLACK:
                    last_move_times[BLACK] = end_time - start_time

                if turn == WHITE and game_input[2] != None:
                    shot_clocks[WHITE] -= last_move_times[WHITE]
                elif turn == BLACK and game_input[2] != None:
                    shot_clocks[BLACK] -= last_move_times[BLACK]

            else:
                print("Log opponent move below")
                waiting = True
                while waiting:
                    user_input = input("Type: 'from_tile to_tile' (without quotes) and press Enter to log a move. example: e2 e4\n")

                    if user_input.lower() == "exit":
                        return False

                    try:
                        from_tile, to_tile = user_input.split()
                    except ValueError:
                        print("Invalid input format. Please enter moves in the format 'e2 e4'.")
                        continue
                    try:
                        piece = next(p for p in chess_board.players[turn].pieces 
                                    if p.location == from_tile)
                        chess_board._move_piece(piece, to_tile)
                        chess_board._update_tiles()
                        print(chess_board.actions[-1])
                        waiting = False
                    except Exception as e:
                        print("Move failed.. ")
                        print(e)

                # Capture move times
                if turn == WHITE:
                    last_move_times[WHITE] = end_time - start_time
                elif turn == BLACK:
                    last_move_times[BLACK] = end_time - start_time

                if turn == WHITE and game_input[2] != None:
                    shot_clocks[WHITE] -= last_move_times[WHITE]
                elif turn == BLACK and game_input[2] != None:
                    shot_clocks[BLACK] -= last_move_times[BLACK]

            turn = BLACK if turn == WHITE else WHITE

            if game_input[2] != None:
                if shot_clocks[WHITE] <= 0 or shot_clocks[BLACK] <= 0:
                    running = False

                    if shot_clocks[WHITE]<=0:
                        print(f"White is out of time. \nWHITE SHOT CLOCK: {fmt_time(shot_clocks[WHITE])}")
                    elif shot_clocks[BLACK]<=0:
                        print(f"White is out of time. \nBLACK SHOT CLOCK: {fmt_time(shot_clocks[BLACK])}")
                    print(f"GAME OVER")

    print("GAME LOG: ")
    for player_action in chess_board.actions:
        print(player_action)

def start_game():
    print("Welcome to the Chess Engine!\n")

    chess_board = ChessBoard()

    game_input = []

    while len(game_input) != 3:

        print("\033c", end="", flush=True)

        if len(game_input) == 2:
            print(f"\nGreat! Its a {game_input[0]} game. You will be playing as {COLORS[game_input[1].upper()]}\n")
            print(f"Set the shot clock")
            user_input = str.upper(input("Type any number below to set shot clock time in minutes.\nType 'INF' below for no shot clock.\nType 'exit' at anytime to leave the game.\n"))

            if user_input == 'INF':
                game_input.append(None)
            
            try:
                shot_clock = int(user_input)
                game_input.append(shot_clock*60)
            except Exception as e:
                pass

        elif len(game_input) == 1:
            print(f"\nGreat! Its a {game_input[0]} game.\n")
            print(f"Will you be playing as White, Black, or Random?")
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

        elif len(game_input) == 0:
            print(f"\nWelcome! Answer a few questions to setup your game.\n")
            print("Would you like to play 2P, against a bot, or use a bot to play an opponent?")
            user_input = str.lower(input("Type '2P' below for 2 Player pass and play. \nType 'bot' to play against a bot.\nType 'aid' to get live move recomendations. \nType 'exit' at anytime to leave the game.\n")).strip()

            if user_input == '2p':
                game_input.append(user_input)
            elif user_input == 'bot':
                game_input.append(user_input)
            elif user_input == 'aid':
                game_input.append(user_input)

        if user_input == 'exit':
            print("GAME OVER\n")
            return

    shot_clock_str = "INF"
    if game_input[2] == None:
        shot_clock_str = "INF"
    elif game_input[2] != None:
        shot_clock_str = fmt_time(game_input[2])

    print("\033c", end="", flush=True)
    print(f"\nAlright! This is a {game_input[0]} game..\nYou will be playing as {COLORS[game_input[1].upper()]}\nSHOT CLOCK: {shot_clock_str}")
    
    hold = input("\nEnter anything other than exit in terminal to start the game\n")
    if hold == 'exit':
        print("GAME OVER\n")
        return False

    if hold == "debug" or "DEBUG":
        game_input.append(hold)


    print("Game Started!")
    game_loop(chess_board, game_input)
        