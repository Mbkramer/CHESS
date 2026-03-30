import sys
import os
import time
import random
from chess_board import ChessBoard
from bot import best_move, MODEL_PATH, MODEL_NAME
from opening_book import REPERTOIRES, BALANCED, SOLID, AGRESSIVE, TACTICAL
import copy

try:
    import chess
    import chess.pgn
except Exception:
    chess = None
from datetime import datetime

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

def export_game_to_pgn(chess_board, game_input, result: str = "*"):
    """
    Exports a completed game to a PGN file using the python-chess library. 
    The PGN file will be saved in the 'data/played_games/{game_type}/' directory, 
    where {game_type} is determined by the type of game played (e.g., '2p', 'bot', 'aid').

    Modified from the original in bot.py
    """

    if chess is None:
        raise RuntimeError("python-chess is required for PGN export")

    game_type = game_input[0].upper()
    output_path = f"data/played_games/{game_type}/"

    model_name = os.path.basename(MODEL_PATH).replace(".pt", "")

    if game_input[0] == '2p':
        white_player_name = "Person One"
        black_player_name = "Perosn Two"
    elif game_input[0] == 'bot':
        if game_input[1] == WHITE:
            white_player_name = "Human"
            black_player_name = model_name
        elif game_input[1] == BLACK:
            white_player_name = model_name
            black_player_name = "Human"
    elif game_input[0] == 'aid':
        if game_input[1] == WHITE:
            white_player_name = "Human (Bot Aid)"
            black_player_name = "Opponent"
        elif game_input[1] == BLACK:
            white_player_name = "Opponent"
            black_player_name = "Human (Bot Aid)"

    board = chess.Board()
    game = chess.pgn.Game()

    game.headers["Event"] = game_type
    game.headers["Site"] = "Local"
    game.headers["Date"] = datetime.now().strftime("%m.%d.%Y")
    game.headers["White"] = white_player_name
    game.headers["Black"] = black_player_name
    game.headers["Result"] = result

    node = game

    for i, action in enumerate(chess_board.actions):
        move_uci = action.from_tile + action.to_tile
        if action.promotion:
            move_uci += action.promotion.lower()

        move = chess.Move.from_uci(move_uci)

        if move not in board.legal_moves:
            print(f"\nFailed at action {i}: {action}")
            print(f"UCI attempted: {move_uci}")
            print(f"python-chess board:\n{board}")
            print(f"Legal moves: {list(board.legal_moves)}")
            raise ValueError(f"Illegal move during PGN export: {move_uci}")

        board.push(move)
        node = node.add_variation(move)

    save_dir = output_path
    os.makedirs(save_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}.pgn"

    if game_input[0] != '2p':
        filename = f"{model_name}_{timestamp}.pgn"

    filepath = os.path.join(save_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        exporter = chess.pgn.FileExporter(f)
        game.accept(exporter)

    return filepath

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

    white_win = "1/2"
    black_win = "1/2"

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

            # Check for game end conditions
            if running == False:
                if COLORS[turn] == WHITE and chess_board.players[turn].mated:
                    black_win = "1"
                    white_win = "0"
                elif COLORS[turn] == BLACK and chess_board.players[turn].mated:
                    white_win = "1"
                    black_win = "0"
                elif (
                    len(chess_board.players[WHITE].possible_moves) == 0 and not chess_board.players[WHITE].mated
                    or len(chess_board.players[BLACK].possible_moves) == 0 and not chess_board.players[BLACK].mated
                ):
                    white_win = "1/2"
                    black_win = "1/2"
                else:
                    white_win = "*"
                    black_win = "*"

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
                    if shot_clocks[WHITE] <= 0:
                        print(f"White is out of time. \nWHITE SHOT CLOCK: {fmt_time(shot_clocks[WHITE])}")
                        black_win = "1"
                        white_win = "0"
                    elif shot_clocks[BLACK] <= 0:
                        print(f"White is out of time. \nBLACK SHOT CLOCK: {fmt_time(shot_clocks[BLACK])}")
                        white_win = "1"
                        black_win = "0"

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
                    if running == False:
                        if COLORS[turn] == WHITE and chess_board.players[turn].mated:
                            black_win = "1"
                            white_win = "0"
                        elif COLORS[turn] == BLACK and chess_board.players[turn].mated:
                            white_win = "1"
                            black_win = "0"
                        elif (
                            len(chess_board.players[WHITE].possible_moves) == 0 and not chess_board.players[WHITE].mated
                            or len(chess_board.players[BLACK].possible_moves) == 0 and not chess_board.players[BLACK].mated
                        ):
                            white_win = "1/2"
                            black_win = "1/2"
                        else:
                            white_win = "*"
                            black_win = "*"

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
                    running = False

                if running == False:
                    if COLORS[turn] == WHITE and chess_board.players[turn].mated:
                        black_win = "1"
                        white_win = "0"
                    elif COLORS[turn] == BLACK and chess_board.players[turn].mated:
                        white_win = "1"
                        black_win = "0"
                    elif (
                        len(chess_board.players[WHITE].possible_moves) == 0 and not chess_board.players[WHITE].mated
                        or len(chess_board.players[BLACK].possible_moves) == 0 and not chess_board.players[BLACK].mated
                    ):
                        white_win = "1/2"
                        black_win = "1/2"
                    else:
                        white_win = "*"
                        black_win = "*"

                    break
                    
                
                print("Waiting on bot move..\n")

                # Cap bot decions making time
                move_budget = 90 # Generouse 2 minutes
                depth = 2

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
                    if shot_clocks[WHITE] <= 0:
                        print(f"White is out of time. \nWHITE SHOT CLOCK: {fmt_time(shot_clocks[WHITE])}")
                        black_win = "1"
                        white_win = "0"
                    elif shot_clocks[BLACK] <= 0:
                        print(f"White is out of time. \nBLACK SHOT CLOCK: {fmt_time(shot_clocks[BLACK])}")
                        white_win = "1"
                        black_win = "0"
            
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
                    running = False

                if running == False:
                    if COLORS[turn] == WHITE and chess_board.players[turn].mated:
                        black_win = "1"
                        white_win = "0"
                    elif COLORS[turn] == BLACK and chess_board.players[turn].mated:
                        white_win = "1"
                        black_win = "0"
                    elif (
                        len(chess_board.players[WHITE].possible_moves) == 0 and not chess_board.players[WHITE].mated
                        or len(chess_board.players[BLACK].possible_moves) == 0 and not chess_board.players[BLACK].mated
                    ):
                        white_win = "1/2"
                        black_win = "1/2"
                    else:
                        white_win = "*"
                        black_win = "*"
                    
                    break
                
                print("Waiting on bot recomendation..\n")
                bot_board = copy.deepcopy(chess_board)

                # Cap bot decions making time
                move_budget = 75 # Generouse 2 minutes
                depth = 2

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
                start_time = time.time()
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

            turn = BLACK if turn == WHITE else WHITE

            if game_input[2] != None:
                if shot_clocks[WHITE] <= 0 or shot_clocks[BLACK] <= 0:
                    running = False
                    if shot_clocks[WHITE] <= 0:
                        print(f"White is out of time. \nWHITE SHOT CLOCK: {fmt_time(shot_clocks[WHITE])}")
                        black_win = "1"
                        white_win = "0"
                    elif shot_clocks[BLACK] <= 0:
                        print(f"White is out of time. \nBLACK SHOT CLOCK: {fmt_time(shot_clocks[BLACK])}")
                        white_win = "1"
                        black_win = "0"


    # Store PGN of game
    if white_win == "*" and black_win == "*":
        result = "*"
    else:
        result = f"{white_win}-{black_win}"
    filepath = export_game_to_pgn(chess_board, game_input, result=result)

    print(f"Saved PGN to: {filepath}\n")
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
        