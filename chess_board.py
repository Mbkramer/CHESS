import copy
from pieces import Piece, Pawn, Knight, Bishop, Rook, Queen, King
from ascii_art import ASCII_PIECES
from player import Player, PlayerAction

ROWS = ["1", "2", "3", "4", "5", "6", "7", "8"]
COLUMNS = ["a", "b", "c", "d", "e", "f", "g", "h"]

TYLE_COLORS = {"W": "White", "B": "Black"}

WHITE = 'W'
BLACK = 'B'

COLORS = [WHITE, BLACK]
PHASES = ("EARLY", "MIDDLE", "LATE")

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
    
    def _is_occupied(self):
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
        self.actions = []

        self._init_board_tiles()
        self.tile_map = {tile.id: tile for row in self.board for tile in row}

        self.players = {
            WHITE: Player(WHITE),
            BLACK: Player(BLACK)
        }

        self.pressure_map = {
            WHITE: self._build_pressure_map(WHITE),
            BLACK: self._build_pressure_map(BLACK),
        }

        self.black_king_location = "e8"
        self.white_king_location = "e1"

        self.phase = "EARLY"

        self._update_tiles()

        self.players[WHITE].update_moves(self, [])
        self.players[BLACK].update_moves(self, [])


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
        print("            a         b         c         d         e         f         g         h         \n")
        for row in self.board:
            rank = row[0].id[1]
            self._print_side_by_side(*[tile.ascii for tile in row], index=rank)

    
    """
    Assess Board and player moves

    """
    def _get_king_piece(self, color):
        for piece in self.players[color].pieces:
            if piece.name == "K":
                return piece
        return None

    # Get tile
    def _get_tile(self, tile_id: str) -> Tile:
        return self.tile_map.get(tile_id)

    # Check if board tile is occupied by a piece
    def _check_tile_occupied(self, tile_id: str) -> bool:
        tile = self._get_tile(tile_id)
        return tile._is_occupied() if tile else False
    
    # search opponent's pressure map for a pressure at location
    def _is_square_attacked(self, location: str, opp_color: str) -> bool:
        return self.pressure_map[opp_color].get(location, 0) > 0

    def _update_tiles(self) -> None:
        self._sync_board()

        # 1. Generate raw pseudo-legal moves
        for color in COLORS:
            opp = BLACK if color == WHITE else WHITE
            self.players[color].update_moves(self, self.players[opp].actions)

        # 2. Build attack map from RAW moves
        self.pressure_map[WHITE] = self._build_pressure_map(WHITE)
        self.pressure_map[BLACK] = self._build_pressure_map(BLACK)

        # 3. Determine check from raw attack map
        checked_status = {}
        for color in COLORS:
            checked_status[color] = self._test_check(color)

        # 4. Cut illegal executable moves
        for color in COLORS:
            self._cut_illegal_moves(color)

        # 5. Rebuild legal move pairs only
        for color in COLORS:
            self.players[color].possible_moves = []
            for piece in self.players[color].pieces:
                for move in piece.moves:
                    self.players[color].possible_moves.append((piece.location, move))

        # 6. Apply checked / mated flags
        for color in COLORS:
            self.players[color].checked = checked_status[color]
            self.players[color].mated = checked_status[color] and len(self.players[color].possible_moves) == 0
            

    def _sync_board(self) -> None:
        # Clear all tiles first
        for row in self.board:
            for tile in row:
                tile.remove_piece()

        # Re-place all active pieces
        for color in COLORS:
            for piece in self.players[color].pieces:
                tile = self._get_tile(piece.location)
                if tile is None:
                    raise ValueError(f"Piece {piece} has invalid location {piece.location}")
                if tile._is_occupied():
                    raise ValueError(f"Two pieces occupy {piece.location}")
                if piece.name == "K" and piece.color == WHITE:
                    self.white_king_location = piece.location
                if piece.name == "K" and piece.color == BLACK:
                    self.black_king_location = piece.location
                    
                tile.place_piece(piece)

    def _fast_update_tiles(self) -> None:
        self._sync_board()
        for color in COLORS:
            opp = BLACK if color == WHITE else WHITE
            self.players[color].update_moves(self, self.players[opp].actions)

        self.pressure_map[WHITE] = self._build_pressure_map(WHITE)
        self.pressure_map[BLACK] = self._build_pressure_map(BLACK)

        for color in COLORS:
            self.players[color].checked = self._test_check(color)

    def _refresh_search_state_after_move(self, side_that_just_moved: str) -> None:
        """
        Lightweight post-move refresh for search nodes.
        Regenerates raw (pseudo-legal) moves and check flags only.
        Does NOT call _cut_illegal_moves — the search handles illegality
        by detecting if the moving side left its king in check.

        USED ONLY FOR PGN TRAIN
        """
        self._sync_board()

        self.players[WHITE].update_moves(self, self.players[BLACK].actions)
        self.players[BLACK].update_moves(self, self.players[WHITE].actions)

        # build attack map
        self.pressure_map[WHITE] = self._build_pressure_map(WHITE)
        self.pressure_map[BLACK] = self._build_pressure_map(BLACK)

        self.players[WHITE].checked = self._test_check(WHITE)
        self.players[BLACK].checked = self._test_check(BLACK)


    def _refresh_search_state_for_turn(self, turn: str) -> None:
        opp = BLACK if turn == WHITE else WHITE

        self._sync_board()

        # Clear stale search flags before regenerating
        self.players[WHITE].checked = False
        self.players[BLACK].checked = False
        self.players[WHITE].possible_moves = []
        self.players[BLACK].possible_moves = []

        # Generate raw moves
        self.players[WHITE].update_moves(self, self.players[BLACK].actions)
        self.players[BLACK].update_moves(self, self.players[WHITE].actions)

        # Rebuild pressure maps
        self.pressure_map[WHITE] = self._build_pressure_map(WHITE)
        self.pressure_map[BLACK] = self._build_pressure_map(BLACK)

        # Set check flags from current position
        self.players[WHITE].checked = self._test_check(WHITE)
        self.players[BLACK].checked = self._test_check(BLACK)

        # Legalize ONLY side to move
        self._cut_illegal_moves(turn)

        self.players[turn].possible_moves = []
        for piece in self.players[turn].pieces:
            for move in piece.moves:
                self.players[turn].possible_moves.append((piece.location, move))
                
                # debug
                tile = self._get_tile(move)
                if tile and tile.piece and tile.piece.color == piece.color:
                    print("BAD SEARCH STATE")
                    print("turn =", turn)
                    print("piece =", piece, "at", piece.location)
                    print("move =", move)
                    print("occupant =", tile.piece, "at", tile.id)
                    print("piece.moves =", piece.moves)
                    raise ValueError(
                        f"Illegal same-color move survived pruning: {piece} {piece.location}->{move} onto {tile.piece}"
                    )

        self.players[turn].mated = (
            self.players[turn].checked and
            len(self.players[turn].possible_moves) == 0
        )


    # Remove any move that leaves own king in check.
    def _cut_illegal_moves(self, color) -> None:
        for piece in self.players[color].pieces:
            legal = []
            original_moves = list(piece.moves)
            for move in original_moves:
                try:
                    if self._move_is_safe(color, piece, move):
                        legal.append(move)

                except ValueError as e:
                    msg = str(e)
                    if "kings cannot be captured" in msg or "cannot move onto own piece" in msg:
                        continue
                    raise

                except Exception as e:
                    print(f"_cut_illegal_moves crash: color={color} piece={piece} at {piece.location} move={move}")
                    raise

            piece.moves = legal


    def _test_check(self, color) -> bool:
        opp_color = BLACK if color == WHITE else WHITE
        king_location = self.white_king_location if color == WHITE else self.black_king_location
        king = self._get_king_piece(color)

        if king is None:
            raise ValueError(f"No king found for {color}")

        king.check = False

        if self.pressure_map[opp_color].get(king_location, 0) > 0:
            king.check = True
            return True

        return False
    

    def _checked(self, color) -> list:
        moves_out = []

        for piece in self.players[color].pieces:
            for move in list(piece.moves):
                if self._move_is_safe(color, piece, move):
                    moves_out.append((piece.location, move))

        return moves_out
    

    def _snapshot_state(self):
        pieces_state = {}
        for color in COLORS:
            for piece in self.players[color].pieces:
                pieces_state[id(piece)] = (
                    piece.location,
                    list(piece.moves),
                    getattr(piece, "castle", ""),
                    getattr(piece, "starting_location", None),
                    getattr(piece, "check", False),
                )

        return {
            "actions": list(self.actions),
            "pieces_state": pieces_state,
            "player_pieces": {c: list(self.players[c].pieces) for c in COLORS},
            "player_points": {c: self.players[c].points for c in COLORS},
            "player_actions": {c: list(self.players[c].actions) for c in COLORS},
            "player_taken": {c: list(self.players[c].taken_pieces) for c in COLORS},
            "player_taken_str": {c: self.players[c].taken_pieces_str for c in COLORS},
            "checked": {c: self.players[c].checked for c in COLORS},
            "mated": {c: self.players[c].mated for c in COLORS},
            "possible_moves": {c: list(self.players[c].possible_moves) for c in COLORS},
            "pressure_maps": {
                WHITE: dict(self.pressure_map[WHITE]),
                BLACK: dict(self.pressure_map[BLACK]),
            },
            "white_king_location": self.white_king_location,
            "black_king_location": self.black_king_location,
        }


    def _restore_state(self, state):
        for color in COLORS:
            p = self.players[color]
            p.pieces = state["player_pieces"][color]
            p.points = state["player_points"][color]
            p.actions = list(state["player_actions"][color])
            p.taken_pieces = list(state["player_taken"][color])
            p.taken_pieces_str = state["player_taken_str"][color]
            p.checked = state["checked"][color]
            p.mated = state["mated"][color]
            p.possible_moves = list(state["possible_moves"][color])

            for piece in p.pieces:
                ps = state["pieces_state"].get(id(piece))
                if ps:
                    piece.location = ps[0]
                    piece.moves = list(ps[1])
                    piece.castle = ps[2]
                    piece.starting_location = ps[3]
                    piece.check = ps[4]

        self.actions = list(state["actions"])
        self.pressure_map = {
            WHITE: dict(state["pressure_maps"][WHITE]),
            BLACK: dict(state["pressure_maps"][BLACK]),
        }
        self.white_king_location = state["white_king_location"]
        self.black_king_location = state["black_king_location"]
        self._sync_board()


    def _move_is_safe(self, color, piece, move) -> bool:
        opp = BLACK if color == WHITE else WHITE

        target_tile = self._get_tile(move)
        if target_tile and target_tile.piece:
            if target_tile.piece.name == "K":
                return False
            if target_tile.piece.color == color:
                return False

        # Special castling legality:
        # cannot castle while in check or through check
        if piece.name == "K":
            from_sq = piece.location
            is_castle = (
                (piece.color == WHITE and from_sq == "e1" and move in ("g1", "c1")) or
                (piece.color == BLACK and from_sq == "e8" and move in ("g8", "c8"))
            )

            if is_castle:
                # build current attack map for the CURRENT position
                self.pressure_map[WHITE] = self._build_pressure_map(WHITE)
                self.pressure_map[BLACK] = self._build_pressure_map(BLACK)

                opp_color = BLACK if color == WHITE else WHITE

                # cannot castle out of check
                if self.pressure_map[opp_color].get(from_sq, 0) > 0:
                    return False

                transit_sq = {
                    "g1": "f1",
                    "c1": "d1",
                    "g8": "f8",
                    "c8": "d8",
                }[move]

                # cannot castle through check
                if self.pressure_map[opp_color].get(transit_sq, 0) > 0:
                    return False

        snap = self._snapshot_state()

        try:
            self._move_piece(piece, move, simulate=True)
            self._sync_board()

            self.players[color].update_moves(self, self.players[opp].actions)
            self.players[opp].update_moves(self, self.players[color].actions)

            self.pressure_map[WHITE] = self._build_pressure_map(WHITE)
            self.pressure_map[BLACK] = self._build_pressure_map(BLACK)

            # destination square safety, including castling into check
            return not self._test_check(color)
        finally:
            self._restore_state(snap)
            

    def _simulate_and_refresh(self, moving_color, piece, move):

        opp = BLACK if moving_color == WHITE else WHITE
        snap = self._snapshot_state()

        self._move_piece(piece, move, simulate=True)
        self._sync_board()

        self.players[WHITE].update_moves(self, self.players[BLACK].actions)
        self.players[BLACK].update_moves(self, self.players[WHITE].actions)

        self.pressure_map[WHITE] = self._build_pressure_map(WHITE)
        self.pressure_map[BLACK] = self._build_pressure_map(BLACK)

        self.players[WHITE].checked = self._test_check(WHITE)
        self.players[BLACK].checked = self._test_check(BLACK)

        return snap
    
    """
    Manipulate the board
    
    """

    def _get_game_phase(self) -> str:
        return self.phase

    def _is_castle_move(self, piece, from_tile_id, to_tile_id):
        if piece.name != "K":
            return None
        if piece.color == WHITE and from_tile_id == "e1" and to_tile_id == "g1":
            return "KS"
        if piece.color == WHITE and from_tile_id == "e1" and to_tile_id == "c1":
            return "QS"
        if piece.color == BLACK and from_tile_id == "e8" and to_tile_id == "g8":
            return "KS"
        if piece.color == BLACK and from_tile_id == "e8" and to_tile_id == "c8":
            return "QS"
        return None
    
    def _castle_rook_move(self, color, side):
        if color == WHITE and side == "KS":
            rook_from, rook_to = "h1", "f1"
        elif color == WHITE and side == "QS":
            rook_from, rook_to = "a1", "d1"
        elif color == BLACK and side == "KS":
            rook_from, rook_to = "h8", "f8"
        else:
            rook_from, rook_to = "a8", "d8"

        rook_from_tile = self._get_tile(rook_from)
        rook_to_tile = self._get_tile(rook_to)

        rook = rook_from_tile.piece
        if rook is None or rook.name != "R":
            raise ValueError("Invalid castling state: rook missing")

        rook_from_tile.remove_piece()
        rook_to_tile.place_piece(rook)
        rook.location = rook_to
        rook.starting_location = None

    def _last_action(self):
        if not self.actions:
            return None
        return self.actions[-1]


    def _is_en_passant_move(self, piece, from_tile_id, to_tile_id):
        if piece.name != "P":
            return None

        last_action = self._last_action()
        if last_action is None:
            return None

        if last_action.piece_name != "P":
            return None

        victim_tile = self._get_tile(last_action.to_tile)
        if victim_tile is None or victim_tile.piece is None:
            return None

        last_piece = victim_tile.piece

        if last_piece.name != "P":
            return None
        if last_piece.color == piece.color:
            return None

        last_from_rank = int(last_action.from_tile[1])
        last_to_rank = int(last_action.to_tile[1])

        # Last move must have been a 2-square pawn advance
        if last_piece.color == WHITE:
            if not (last_action.from_tile[1] == "2" and last_to_rank - last_from_rank == 2):
                return None
            passed_square = f"{last_action.from_tile[0]}3"
        else:
            if not (last_action.from_tile[1] == "7" and last_from_rank - last_to_rank == 2):
                return None
            passed_square = f"{last_action.from_tile[0]}6"

        if to_tile_id != passed_square:
            return None

        to_tile = self._get_tile(to_tile_id)
        if to_tile is None or to_tile._is_occupied():
            return None

        from_file = ord(from_tile_id[0])
        to_file = ord(to_tile_id[0])
        from_rank = int(from_tile_id[1])
        to_rank = int(to_tile_id[1])

        file_delta = abs(to_file - from_file)
        rank_delta = to_rank - from_rank if piece.color == WHITE else from_rank - to_rank

        if file_delta != 1 or rank_delta != 1:
            return None

        return last_piece
    

    def _build_pressure_map(self, color: str) -> dict[str, int]:
        # Initialize all 64 squares to 0 pressure
        pressure = {
            f"{col}{row}": 0
            for row in ROWS
            for col in COLUMNS
        }

        for piece in self.players[color].pieces:
            col = ord(piece.location[0])
            row = int(piece.location[1])

            if piece.name == "P":
                if color == WHITE:
                    for dc in (-1, 1):
                        nc = col + dc
                        nr = row + 1
                        if 97 <= nc <= 104 and 1 <= nr <= 8:
                            pressure[f"{chr(nc)}{nr}"] += 1
                else:
                    for dc in (-1, 1):
                        nc = col + dc
                        nr = row - 1
                        if 97 <= nc <= 104 and 1 <= nr <= 8:
                            pressure[f"{chr(nc)}{nr}"] += 1

            elif piece.name == "K":
                for dc in (-1, 0, 1):
                    for dr in (-1, 0, 1):
                        if dc == 0 and dr == 0:
                            continue
                        nc = col + dc
                        nr = row + dr
                        if 97 <= nc <= 104 and 1 <= nr <= 8:
                            pressure[f"{chr(nc)}{nr}"] += 1

            else:
                for sq in piece.moves:
                    pressure[sq] += 1

        return pressure

    # Move piece from one tile to another, updating piece location and board state
    def _move_piece(self, piece: Piece, to_tile_id: str,
                simulate: bool = False, promotion: str = None) -> None:

        from_tile_id = piece.location
        start_tile = self._get_tile(from_tile_id)
        target_tile = self._get_tile(to_tile_id)

        opponent_color = WHITE if piece.color == BLACK else BLACK

        if start_tile is None or target_tile is None:
            raise ValueError("Invalid move: bad tile id")
        
        captured_piece = target_tile.piece
        if captured_piece != None:
            if captured_piece.name == "K":
                raise ValueError("Illegal move: kings cannot be captured")
            
            if captured_piece.color == piece.color:
                raise ValueError(f"Illegal move: {piece} cannot move onto own piece at {to_tile_id}")

        castle = self._is_castle_move(piece, from_tile_id, to_tile_id)

        start_tile.remove_piece()

        # Special Case Castle
        if castle != None:

            piece.starting_location = None
            self._castle_rook_move(piece.color, castle)
            target_tile.place_piece(piece)
            piece.location = to_tile_id

            if not simulate:
                self.players[piece.color]._log_action(PlayerAction(from_tile_id, to_tile_id, piece, castle=castle))
                self.actions.append(PlayerAction(from_tile_id, to_tile_id, piece, castle=castle))
            
            piece.castle = ""
            return

        # Special Case Pawn Promotion
        if piece.name == "P" and (
            (piece.color == WHITE and to_tile_id[1] == "8") or
            (piece.color == BLACK and to_tile_id[1] == "1")
        ):
            opponent_color = BLACK if piece.color == WHITE else WHITE
            captured_piece = None

            # Handle capture on promotion square
            if target_tile._is_occupied():
                captured_piece = target_tile.piece

                if captured_piece.color == piece.color:
                    raise ValueError(f"Illegal move: {piece} cannot move onto own piece at {to_tile_id}")

                if captured_piece.name == "K":
                    raise ValueError("Illegal move: kings cannot be captured")

                self.players[opponent_color].pieces.remove(captured_piece)

                if not simulate:
                    self.players[piece.color].take_piece(captured_piece, simulate=False)

            promotions = {"Q", "R", "B", "N"}

            if promotion is None:
                if simulate:
                    promotion = "Q"
                else:
                    promotion = "Q"
                    """
                    while promotion not in promotions:
                        promotion = input(
                            "Pawn Promotion:\n"
                            "Type 'Q' for Queen\n"
                            "Type 'R' for Rook\n"
                            "Type 'B' for Bishop\n"
                            "Type 'N' for Knight\n"
                        ).upper()
                    """
            else:
                promotion = promotion.upper()
                if promotion not in promotions:
                    raise ValueError(f"Unsupported promotion piece: {promotion}")

            if promotion == 'Q':
                promoted = Queen(piece.color, to_tile_id, 0)
                promoted.value = 9
            elif promotion == 'R':
                promoted = Rook(piece.color, to_tile_id, 0)
                promoted.value = 5
            elif promotion == 'B':
                promoted = Bishop(piece.color, to_tile_id, 0)
                promoted.value = 3
            elif promotion == 'N':
                promoted = Knight(piece.color, to_tile_id, 0)
                promoted.value = 3
            else:
                raise ValueError(f"Unsupported promotion piece: {promotion}")

            promoted.id = piece.id

            # Replace pawn with promoted piece
            self.players[piece.color].pieces.remove(piece)
            self.players[piece.color].pieces.append(promoted)
            target_tile.place_piece(promoted)

            if not simulate:
                action = PlayerAction(
                    from_tile_id,
                    to_tile_id,
                    piece,
                    captured=captured_piece,
                    promotion=promotion
                )
                self.players[piece.color]._log_action(action)
                self.actions.append(action)

            return

        # Check En Passant Move
        if piece.name == "P":
            en_passant = self._is_en_passant_move(piece, from_tile_id, to_tile_id)
            if en_passant is not None:
                
                target_tile.place_piece(piece)
                piece.location = to_tile_id

                passed_pawn_location = ""

                if piece.color == WHITE:

                    col = piece.location[0]
                    row = int(piece.location[1])
                    passed_pawn_location = f"{col}{row-1}"

                    passed_tile = self._get_tile(passed_pawn_location)
                    if passed_tile is None or passed_tile.piece is None or passed_tile.piece.name != "P":
                        raise ValueError("Invalid en passant state")
                    captured_piece = passed_tile.piece

                    self.players[piece.color].take_piece(captured_piece, simulate)
                    self.players[opponent_color].pieces.remove(captured_piece)
                    passed_tile.remove_piece()

                elif piece.color == BLACK:

                    col = piece.location[0]
                    row = int(piece.location[1])
                    passed_pawn_location = f"{col}{row+1}"

                    passed_tile = self._get_tile(passed_pawn_location)
                    if passed_tile is None or passed_tile.piece is None or passed_tile.piece.name != "P":
                        raise ValueError("Invalid en passant state")
                    captured_piece = passed_tile.piece

                    self.players[piece.color].take_piece(captured_piece, simulate)
                    self.players[opponent_color].pieces.remove(captured_piece)
                    passed_tile.remove_piece()

                if not simulate:
                    action = PlayerAction(from_tile_id, to_tile_id, piece, captured=en_passant)
                    self.players[piece.color]._log_action(action)
                    self.actions.append(action)
                return

        # Standard Capture
        if target_tile._is_occupied() and target_tile.piece.color != piece.color:

            captured_piece = target_tile.piece
            if captured_piece.name == "K":
                raise ValueError("Illegal move: kings cannot be captured")
            
            if captured_piece is not None and captured_piece.color == piece.color:
                raise ValueError(f"Illegal move: {piece} cannot move onto own piece at {to_tile_id}")
            
            if piece.name == "K":
                if piece.color == WHITE:
                    self.white_king_location = to_tile_id
                elif piece.color == BLACK:
                    self.black_king_location = to_tile_id

            opponent_color = BLACK if piece.color == WHITE else WHITE

            self.players[piece.color].take_piece(captured_piece, simulate)
            self.players[opponent_color].pieces.remove(captured_piece)
            target_tile.place_piece(piece)
            piece.location = to_tile_id
            if hasattr(piece, "starting_location"):
                piece.starting_location = None

            # Capture
            if not simulate:
                action = PlayerAction(from_tile_id, to_tile_id, piece, captured=captured_piece)
                self.players[piece.color]._log_action(action)
                self.actions.append(action)

        # Standard Open Space Move
        else:
            if piece.name == "K":
                if piece.color == WHITE:
                    self.white_king_location = to_tile_id
                elif piece.color == BLACK:
                    self.black_king_location = to_tile_id

            target_tile.place_piece(piece)
            piece.location = to_tile_id
            if hasattr(piece, "starting_location"):
                piece.starting_location = None

            if not simulate:
                action = PlayerAction(from_tile_id, to_tile_id, piece)
                self.players[piece.color]._log_action(action)
                self.actions.append(action)
