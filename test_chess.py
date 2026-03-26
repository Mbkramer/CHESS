import unittest
import copy

from chess_board import ChessBoard
from player import PlayerAction
from bot import best_move
from bot import move_order_score, _passes_opening_sanity
from opening_book import choose_book_move

WHITE = 'W'
BLACK = 'B'


def get_piece(board, square):
    for row in board.board:
        for tile in row:
            if tile.id == square:
                return tile.piece
    return None


def moves_for(board, square):
    piece = get_piece(board, square)
    assert piece is not None, f"No piece at {square}"
    return list(piece.moves)


def make_move(board, from_sq, to_sq, *, assert_legal=True, assert_consistent=True):
    piece = next(
        (p for p in board.players[WHITE].pieces + board.players[BLACK].pieces
         if p.location == from_sq),
        None
    )
    assert piece is not None, f"No piece found at {from_sq}"

    if assert_legal:
        assert to_sq in piece.moves, (
            f"Move {from_sq}->{to_sq} not legal for {piece}. "
            f"Available: {piece.moves}"
        )

    before_actions = len(getattr(board, "actions", []))
    board._move_piece(piece, to_sq)
    board._update_tiles()

    if hasattr(board, "actions"):
        assert len(board.actions) == before_actions + 1, (
            f"Expected board action log to increment by 1 after {from_sq}->{to_sq}"
        )

    if assert_consistent:
        all_pieces = board.players[WHITE].pieces + board.players[BLACK].pieces
        locations = [p.location for p in all_pieces]
        assert len(locations) == len(set(locations)), "Duplicate piece locations after move"

def set_position(b, white_pieces, black_pieces):
    from pieces import King, Queen, Rook, Bishop, Knight, Pawn

    piece_classes = {
        'K': King,
        'Q': Queen,
        'R': Rook,
        'B': Bishop,
        'N': Knight,
        'P': Pawn,
    }

    for color in (WHITE, BLACK):
        b.players[color].pieces = []
        b.players[color].actions = []
        b.players[color].possible_moves = []
        b.players[color].taken_pieces = []
        b.players[color].taken_pieces_str = ""
        b.players[color].points = 0
        b.players[color].checked = False
        b.players[color].mated = False

    b.actions = []

    counters = {
        WHITE: {'P': 0, 'N': 0, 'B': 0, 'R': 0, 'Q': 0, 'K': 0},
        BLACK: {'P': 0, 'N': 0, 'B': 0, 'R': 0, 'Q': 0, 'K': 0},
    }

    for color, pieces in ((WHITE, white_pieces), (BLACK, black_pieces)):
        for name, square in pieces:
            i = counters[color][name]
            piece = piece_classes[name](color, square, i)
            counters[color][name] += 1
            b.players[color].pieces.append(piece)

    b._update_tiles()

class ChessTestCase(unittest.TestCase):
    def assertPiece(self, board, square, name=None, color=None):
        piece = get_piece(board, square)
        self.assertIsNotNone(piece, f"Expected piece at {square}")
        if name is not None:
            self.assertEqual(piece.name, name)
        if color is not None:
            self.assertEqual(piece.color, color)
        return piece

    def assertEmpty(self, board, square):
        self.assertIsNone(get_piece(board, square), f"Expected empty square {square}")

    def assert_board_consistent(self, board):
        # Exactly one king per side
        white_kings = [p for p in board.players[WHITE].pieces if p.name == "K"]
        black_kings = [p for p in board.players[BLACK].pieces if p.name == "K"]
        self.assertEqual(len(white_kings), 1, "White should have exactly one king")
        self.assertEqual(len(black_kings), 1, "Black should have exactly one king")

        # No duplicate piece locations
        all_pieces = board.players[WHITE].pieces + board.players[BLACK].pieces
        locations = [p.location for p in all_pieces]
        self.assertEqual(len(locations), len(set(locations)), "Two pieces share a square")

        # Tile occupancy matches piece lists
        tile_piece_map = {}
        for row in board.board:
            for tile in row:
                if tile.piece is not None:
                    tile_piece_map[tile.id] = tile.piece

        self.assertEqual(
            len(tile_piece_map),
            len(all_pieces),
            "Board tiles and player piece lists disagree"
        )

        for piece in all_pieces:
            self.assertIn(piece.location, tile_piece_map, f"{piece} missing from tile map")
            self.assertIs(
                tile_piece_map[piece.location],
                piece,
                f"{piece} tile mapping inconsistent"
            )

        # Kings must never appear in taken pieces
        for color in [WHITE, BLACK]:
            taken = getattr(board.players[color], "taken_pieces", [])
            for item in taken:
                if hasattr(item, "name"):
                    self.assertNotEqual(item.name, "K", "King was recorded as captured")


class TestBoardInit(ChessTestCase):
    def setUp(self):
        self.b = ChessBoard()

    def test_all_pieces_placed(self):
        self.assertEqual(len(self.b.players[WHITE].pieces), 16)
        self.assertEqual(len(self.b.players[BLACK].pieces), 16)
        self.assert_board_consistent(self.b)

    def test_white_pawns_on_rank2(self):
        locs = {p.location for p in self.b.players[WHITE].pieces if p.name == 'P'}
        self.assertEqual(locs, {'a2', 'b2', 'c2', 'd2', 'e2', 'f2', 'g2', 'h2'})

    def test_black_pawns_on_rank7(self):
        locs = {p.location for p in self.b.players[BLACK].pieces if p.name == 'P'}
        self.assertEqual(locs, {'a7', 'b7', 'c7', 'd7', 'e7', 'f7', 'g7', 'h7'})

    def test_white_back_rank(self):
        expected = {
            'a1': 'R', 'b1': 'N', 'c1': 'B', 'd1': 'Q',
            'e1': 'K', 'f1': 'B', 'g1': 'N', 'h1': 'R'
        }
        for sq, name in expected.items():
            self.assertPiece(self.b, sq, name=name, color=WHITE)

    def test_black_back_rank(self):
        expected = {
            'a8': 'R', 'b8': 'N', 'c8': 'B', 'd8': 'Q',
            'e8': 'K', 'f8': 'B', 'g8': 'N', 'h8': 'R'
        }
        for sq, name in expected.items():
            self.assertPiece(self.b, sq, name=name, color=BLACK)

    def test_empty_middle_ranks(self):
        for rank in ['3', '4', '5', '6']:
            for col in 'abcdefgh':
                self.assertEmpty(self.b, f"{col}{rank}")


class TestPawnMoves(ChessTestCase):
    def setUp(self):
        self.b = ChessBoard()

    def test_white_pawn_opening_two_squares(self):
        mvs = moves_for(self.b, 'e2')
        self.assertIn('e4', mvs)
        self.assertIn('e3', mvs)

    def test_black_pawn_opening_two_squares(self):
        mvs = moves_for(self.b, 'e7')
        self.assertIn('e5', mvs)
        self.assertIn('e6', mvs)

    def test_white_pawn_blocked(self):
        make_move(self.b, 'e2', 'e4')
        make_move(self.b, 'e7', 'e5')
        self.assertEqual(moves_for(self.b, 'e4'), [])

    def test_white_pawn_diagonal_capture(self):
        make_move(self.b, 'e2', 'e4')
        make_move(self.b, 'd7', 'd5')
        self.assertIn('d5', moves_for(self.b, 'e4'))

    def test_black_pawn_diagonal_capture(self):
        make_move(self.b, 'd2', 'd4')
        make_move(self.b, 'e7', 'e5')
        self.assertIn('d4', moves_for(self.b, 'e5'))

    def test_pawn_no_double_move_after_first_move(self):
        make_move(self.b, 'e2', 'e3')
        make_move(self.b, 'a7', 'a6')
        self.assertNotIn('e5', moves_for(self.b, 'e3'))


class TestKnightMoves(ChessTestCase):
    def setUp(self):
        self.b = ChessBoard()

    def test_white_knight_opening_moves(self):
        mvs = moves_for(self.b, 'g1')
        self.assertIn('f3', mvs)
        self.assertIn('h3', mvs)

    def test_knight_l_shape(self):
        make_move(self.b, 'g1', 'f3')
        make_move(self.b, 'a7', 'a6')
        mvs = moves_for(self.b, 'f3')
        self.assertIn('e5', mvs)
        self.assertIn('g5', mvs)
        self.assertIn('d4', mvs)
        self.assertIn('h4', mvs)

    def test_knight_cannot_move_to_own_piece(self):
        self.assertNotIn('e2', moves_for(self.b, 'g1'))


class TestBishopMoves(ChessTestCase):
    def setUp(self):
        self.b = ChessBoard()

    def test_bishop_blocked_at_start(self):
        self.assertEqual(moves_for(self.b, 'c1'), [])

    def test_bishop_moves_diagonally(self):
        make_move(self.b, 'e2', 'e4')
        make_move(self.b, 'a7', 'a6')
        mvs = moves_for(self.b, 'f1')
        self.assertIn('e2', mvs)
        self.assertIn('d3', mvs)
        self.assertIn('c4', mvs)

    def test_bishop_blocked_by_own_piece(self):
        self.assertNotIn('b2', moves_for(self.b, 'c1'))


class TestRookMoves(ChessTestCase):
    def setUp(self):
        self.b = ChessBoard()

    def test_rook_blocked_at_start(self):
        self.assertEqual(moves_for(self.b, 'a1'), [])

    def test_rook_moves_straight(self):
        make_move(self.b, 'a2', 'a4')
        make_move(self.b, 'a7', 'a6')
        mvs = moves_for(self.b, 'a1')
        self.assertIn('a2', mvs)
        self.assertIn('a3', mvs)


class TestQueenMoves(ChessTestCase):
    def setUp(self):
        self.b = ChessBoard()

    def test_queen_blocked_at_start(self):
        self.assertEqual(moves_for(self.b, 'd1'), [])

    def test_queen_diagonal_and_straight(self):
        make_move(self.b, 'd2', 'd4')
        make_move(self.b, 'a7', 'a6')
        mvs = moves_for(self.b, 'd1')
        self.assertIn('d2', mvs)
        self.assertIn('d3', mvs)


class TestKingMoves(ChessTestCase):
    def setUp(self):
        self.b = ChessBoard()

    def test_king_blocked_at_start(self):
        self.assertEqual(moves_for(self.b, 'e1'), [])

    def test_king_moves_one_square(self):
        make_move(self.b, 'e2', 'e4')
        make_move(self.b, 'a7', 'a6')
        mvs = moves_for(self.b, 'e1')
        self.assertIn('e2', mvs)
        self.assertNotIn('e3', mvs)


class TestCaptures(ChessTestCase):
    def setUp(self):
        self.b = ChessBoard()

    def test_capture_removes_piece_from_opponent(self):
        before = len(self.b.players[BLACK].pieces)
        make_move(self.b, 'e2', 'e4')
        make_move(self.b, 'd7', 'd5')
        make_move(self.b, 'e4', 'd5')
        self.assertEqual(len(self.b.players[BLACK].pieces), before - 1)
        self.assert_board_consistent(self.b)

    def test_capture_awards_points(self):
        make_move(self.b, 'e2', 'e4')
        make_move(self.b, 'd7', 'd5')
        make_move(self.b, 'e4', 'd5')
        self.assertEqual(self.b.players[WHITE].points, 1)

    def test_capture_bookkeeping_not_duplicated(self):
        make_move(self.b, 'e2', 'e4')
        make_move(self.b, 'd7', 'd5')
        before_taken = len(getattr(self.b.players[WHITE], "taken_pieces", []))
        make_move(self.b, 'e4', 'd5')
        after_taken = len(getattr(self.b.players[WHITE], "taken_pieces", []))
        self.assertEqual(after_taken - before_taken, 1)

    def test_capture_updates_board_state(self):
        make_move(self.b, 'e2', 'e4')
        make_move(self.b, 'd7', 'd5')
        make_move(self.b, 'e4', 'd5')
        self.assertPiece(self.b, 'd5', name='P', color=WHITE)
        self.assertEmpty(self.b, 'e4')
        self.assert_board_consistent(self.b)


class TestCheckAndMate(ChessTestCase):
    def test_scholars_mate_check(self):
        b = ChessBoard()
        make_move(b, 'e2', 'e4')
        make_move(b, 'e7', 'e5')
        make_move(b, 'f1', 'c4')
        make_move(b, 'b8', 'c6')
        make_move(b, 'd1', 'h5')
        make_move(b, 'a7', 'a6')
        make_move(b, 'h5', 'f7')
        self.assertTrue(b.players[BLACK].checked)

    def test_scholars_mate(self):
        b = ChessBoard()
        make_move(b, 'e2', 'e4')
        make_move(b, 'e7', 'e5')
        make_move(b, 'f1', 'c4')
        make_move(b, 'b8', 'c6')
        make_move(b, 'd1', 'h5')
        make_move(b, 'a7', 'a6')
        make_move(b, 'h5', 'f7')
        self.assertTrue(b.players[BLACK].mated)

    def test_fools_mate(self):
        b = ChessBoard()
        make_move(b, 'f2', 'f3')
        make_move(b, 'e7', 'e5')
        make_move(b, 'g2', 'g4')
        make_move(b, 'd8', 'h4')
        self.assertTrue(b.players[WHITE].checked)
        self.assertTrue(b.players[WHITE].mated)


class TestBoardState(ChessTestCase):
    def setUp(self):
        self.b = ChessBoard()

    def test_move_updates_piece_location(self):
        make_move(self.b, 'e2', 'e4')
        self.assertPiece(self.b, 'e4', name='P', color=WHITE)

    def test_old_tile_empty_after_move(self):
        make_move(self.b, 'e2', 'e4')
        self.assertEmpty(self.b, 'e2')

    def test_action_logged(self):
        make_move(self.b, 'e2', 'e4')
        last = self.b.players[WHITE].actions[-1]
        self.assertIsInstance(last, PlayerAction)
        self.assertEqual(last.from_tile, 'e2')
        self.assertEqual(last.to_tile, 'e4')

    def test_board_action_logged(self):
        make_move(self.b, 'e2', 'e4')
        last = self.b.actions[-1]
        self.assertIsInstance(last, PlayerAction)
        self.assertEqual(last.from_tile, 'e2')
        self.assertEqual(last.to_tile, 'e4')

    def test_deep_copy_does_not_affect_original(self):
        b2 = copy.deepcopy(self.b)
        make_move(b2, 'e2', 'e4')
        self.assertEmpty(self.b, 'e4')
        self.assertPiece(self.b, 'e2', name='P', color=WHITE)

    def test_board_consistency_after_normal_move(self):
        make_move(self.b, 'e2', 'e4')
        self.assert_board_consistent(self.b)


class TestSimulationIntegrity(ChessTestCase):
    def test_snapshot_restore_round_trip(self):
        b = ChessBoard()
        snap = b._snapshot_state()

        piece = self.assertPiece(b, 'e2', name='P', color=WHITE)
        b._move_piece(piece, 'e4', simulate=True)
        b._restore_state(snap)

        self.assertPiece(b, 'e2', name='P', color=WHITE)
        self.assertEmpty(b, 'e4')
        self.assert_board_consistent(b)

    def test_move_is_safe_does_not_mutate_board(self):
        b = ChessBoard()
        before = copy.deepcopy(b)

        piece = self.assertPiece(b, 'e2', name='P', color=WHITE)
        _ = b._move_is_safe(WHITE, piece, 'e4')

        current = sorted((p.color, p.name, p.location)
                         for p in b.players[WHITE].pieces + b.players[BLACK].pieces)
        original = sorted((p.color, p.name, p.location)
                          for p in before.players[WHITE].pieces + before.players[BLACK].pieces)

        self.assertEqual(current, original)
        self.assert_board_consistent(b)


class TestActionHistory(ChessTestCase):
    def test_action_log_tracks_real_moves_only(self):
        b = ChessBoard()
        make_move(b, 'e2', 'e4')
        make_move(b, 'e7', 'e5')

        self.assertEqual(len(b.actions), 2)
        self.assertEqual(b.actions[0].from_tile, 'e2')
        self.assertEqual(b.actions[0].to_tile, 'e4')
        self.assertEqual(b.actions[1].from_tile, 'e7')
        self.assertEqual(b.actions[1].to_tile, 'e5')

    def test_simulation_does_not_append_actions(self):
        b = ChessBoard()
        piece = self.assertPiece(b, 'e2', name='P', color=WHITE)
        before = len(b.actions)
        b._move_piece(piece, 'e4', simulate=True)
        self.assertEqual(len(b.actions), before)


class TestCastling(ChessTestCase):
    def _clear_kingside_white(self, b):
        make_move(b, 'e2', 'e4')
        make_move(b, 'a7', 'a6')
        make_move(b, 'f1', 'c4')
        make_move(b, 'a6', 'a5')
        make_move(b, 'g1', 'f3')
        make_move(b, 'a5', 'a4')

    def test_kingside_castling_available(self):
        b = ChessBoard()
        self._clear_kingside_white(b)
        king = next(p for p in b.players[WHITE].pieces if p.name == 'K')
        self.assertIn('g1', king.moves)

    def test_kingside_castle_places_pieces(self):
        b = ChessBoard()
        self._clear_kingside_white(b)
        make_move(b, 'e1', 'g1')
        self.assertPiece(b, 'g1', name='K', color=WHITE)
        self.assertPiece(b, 'f1', name='R', color=WHITE)
        self.assertEmpty(b, 'h1')
        self.assertEmpty(b, 'e1')
        self.assert_board_consistent(b)

    def test_castling_not_available_after_king_moves(self):
        b = ChessBoard()
        self._clear_kingside_white(b)
        make_move(b, 'e1', 'e2')
        make_move(b, 'e2', 'e1')

        king = self.assertPiece(b, 'e1', name='K', color=WHITE)
        self.assertNotIn('g1', king.moves)

    def test_castling_not_available_while_in_check(self):
        b = ChessBoard()

        set_position(
            b,
            white_pieces=[('K', 'e1'), ('R', 'h1')],
            black_pieces=[('K', 'a8'), ('R', 'e8')],
        )

        self.assertGreater(b.pressure_map[BLACK].get('e1', 0), 0)
        self.assertTrue(b.players[WHITE].checked)

        king = self.assertPiece(b, 'e1', name='K', color=WHITE)
        self.assertNotIn('g1', king.moves)
        self.assertNotIn(('e1', 'g1'), b.players[WHITE].possible_moves)


    def test_castling_not_available_through_attacked_f1(self):
        b = ChessBoard()

        set_position(
            b,
            white_pieces=[('K', 'e1'), ('R', 'h1')],
            black_pieces=[('K', 'a8'), ('R', 'f8')],
        )

        self.assertGreater(b.pressure_map[BLACK].get('f1', 0), 0)
        self.assertEqual(b.pressure_map[BLACK].get('e1', 0), 0)
        self.assertEqual(b.pressure_map[BLACK].get('g1', 0), 0)

        king = self.assertPiece(b, 'e1', name='K', color=WHITE)
        self.assertNotIn('g1', king.moves)
        self.assertNotIn(('e1', 'g1'), b.players[WHITE].possible_moves)


    def test_castling_not_available_into_attacked_g1(self):
        b = ChessBoard()

        set_position(
            b,
            white_pieces=[('K', 'e1'), ('R', 'h1')],
            black_pieces=[('K', 'a8'), ('R', 'g8')],
        )

        self.assertGreater(b.pressure_map[BLACK].get('g1', 0), 0)
        self.assertEqual(b.pressure_map[BLACK].get('e1', 0), 0)
        self.assertEqual(b.pressure_map[BLACK].get('f1', 0), 0)

        king = self.assertPiece(b, 'e1', name='K', color=WHITE)
        self.assertNotIn('g1', king.moves)
        self.assertNotIn(('e1', 'g1'), b.players[WHITE].possible_moves)


    def test_castling_available_when_path_is_clear_and_safe(self):
        b = ChessBoard()

        set_position(
            b,
            white_pieces=[('K', 'e1'), ('R', 'h1')],
            black_pieces=[('K', 'a8')],
        )

        self.assertFalse(b.players[WHITE].checked)
        self.assertEqual(b.pressure_map[BLACK].get('e1', 0), 0)
        self.assertEqual(b.pressure_map[BLACK].get('f1', 0), 0)
        self.assertEqual(b.pressure_map[BLACK].get('g1', 0), 0)

        king = self.assertPiece(b, 'e1', name='K', color=WHITE)
        self.assertIn('g1', king.moves)
        self.assertIn(('e1', 'g1'), b.players[WHITE].possible_moves)


class TestEnPassant(ChessTestCase):
    def test_white_en_passant_available(self):
        b = ChessBoard()
        make_move(b, 'e2', 'e4')
        make_move(b, 'a7', 'a6')
        make_move(b, 'e4', 'e5')
        make_move(b, 'd7', 'd5')
        self.assertIn('d6', moves_for(b, 'e5'))

    def test_black_en_passant_available(self):
        b = ChessBoard()
        make_move(b, 'a2', 'a3')
        make_move(b, 'e7', 'e5')
        make_move(b, 'a3', 'a4')
        make_move(b, 'e5', 'e4')
        make_move(b, 'd2', 'd4')
        self.assertIn('d3', moves_for(b, 'e4'))

    def test_en_passant_expires_after_delay(self):
        b = ChessBoard()
        make_move(b, 'e2', 'e4')
        make_move(b, 'a7', 'a6')
        make_move(b, 'e4', 'e5')
        make_move(b, 'd7', 'd5')
        make_move(b, 'a2', 'a3')
        make_move(b, 'a6', 'a5')
        self.assertNotIn('d6', moves_for(b, 'e5'))

    def test_white_en_passant_execution(self):
        b = ChessBoard()
        make_move(b, 'e2', 'e4')
        make_move(b, 'a7', 'a6')
        make_move(b, 'e4', 'e5')
        make_move(b, 'd7', 'd5')
        make_move(b, 'e5', 'd6')

        self.assertPiece(b, 'd6', name='P', color=WHITE)
        self.assertEmpty(b, 'd5')
        self.assertEqual(len([p for p in b.players[BLACK].pieces if p.location == 'd5']), 0)
        self.assert_board_consistent(b)

    def test_black_en_passant_execution(self):
        b = ChessBoard()
        make_move(b, 'a2', 'a3')
        make_move(b, 'e7', 'e5')
        make_move(b, 'a3', 'a4')
        make_move(b, 'e5', 'e4')
        make_move(b, 'd2', 'd4')
        make_move(b, 'e4', 'd3')

        self.assertPiece(b, 'd3', name='P', color=BLACK)
        self.assertEmpty(b, 'd4')
        self.assert_board_consistent(b)


class TestCheckConsistency(ChessTestCase):
    def test_checked_side_has_no_illegal_escape_moves(self):
        b = ChessBoard()
        make_move(b, 'f2', 'f3')
        make_move(b, 'e7', 'e5')
        make_move(b, 'g2', 'g4')
        make_move(b, 'd8', 'h4')

        self.assertTrue(b.players[WHITE].checked)

        for piece in b.players[WHITE].pieces:
            for move in list(piece.moves):
                snap = b._snapshot_state()
                try:
                    b._move_piece(piece, move, simulate=True)
                    b._sync_board()
                    b.players[WHITE].update_moves(b.board, b.players[BLACK].actions)
                    b.players[BLACK].update_moves(b.board, b.players[WHITE].actions)
                    self.assertFalse(
                        b._test_check(WHITE),
                        f"Illegal escape move survived: {piece.location}->{move}"
                    )
                finally:
                    b._restore_state(snap)


class TestRegression(ChessTestCase):
    def test_king_capture_moves_not_executable(self):
        b = ChessBoard()
        for color in [WHITE, BLACK]:
            for piece in b.players[color].pieces:
                for move in piece.moves:
                    tile = b._get_tile(move)
                    self.assertFalse(
                        tile and tile.piece and tile.piece.name == 'K',
                        f"Executable move targets king square: {piece.location}->{move}"
                    )

    def test_no_duplicate_taken_piece_on_simulation(self):
        b = ChessBoard()
        make_move(b, 'e2', 'e4')
        make_move(b, 'd7', 'd5')

        before_taken = len(getattr(b.players[WHITE], "taken_pieces", []))
        piece = self.assertPiece(b, 'e4', name='P', color=WHITE)
        snap = b._snapshot_state()
        try:
            b._move_piece(piece, 'd5', simulate=True)
        finally:
            b._restore_state(snap)

        self.assertEqual(len(getattr(b.players[WHITE], "taken_pieces", [])), before_taken)
        self.assert_board_consistent(b)


class TestBot(ChessTestCase):
    def test_bot_does_not_walk_into_check(self):
        b = ChessBoard()
        move = best_move(b, WHITE, depth=2)
        self.assertIsNotNone(move)
        from_sq, to_sq = move
        piece = next(p for p in b.players[WHITE].pieces if p.location == from_sq)
        b._move_piece(piece, to_sq)
        b._update_tiles()
        self.assertFalse(b._test_check(WHITE))
        self.assert_board_consistent(b)


class TestBotDecisionQuality(ChessTestCase):
    def test_opening_sanity_rejects_early_queen_wander(self):
        b = ChessBoard()
        queen = self.assertPiece(b, "d1", name="Q", color=WHITE)
        self.assertFalse(_passes_opening_sanity(b, queen, "h5"))

    def test_opening_sanity_rejects_flank_pawn_push(self):
        b = ChessBoard()
        pawn = self.assertPiece(b, "a2", name="P", color=WHITE)
        self.assertFalse(_passes_opening_sanity(b, pawn, "a4"))

    def test_move_order_prioritizes_central_pawn_development(self):
        b = ChessBoard()
        center_pawn = self.assertPiece(b, "e2", name="P", color=WHITE)
        flank_pawn = self.assertPiece(b, "a2", name="P", color=WHITE)

        center_score = move_order_score(b, center_pawn, "e4", color=WHITE)
        flank_score = move_order_score(b, flank_pawn, "a4", color=WHITE)
        self.assertGreater(center_score, flank_score)

    def test_book_can_pick_top_weight_deterministically(self):
        b = ChessBoard()
        book_move = choose_book_move(
            b,
            WHITE,
            repertoire_name="balanced",
            weighted=False,
            deterministic_top=True,
        )
        self.assertIsNotNone(book_move)
        from_sq, to_sq, _meta = book_move
        self.assertEqual((from_sq, to_sq), ("e2", "e4"))


if __name__ == '__main__':
    unittest.main(verbosity=2)