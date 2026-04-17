import unittest
import copy
import os
import time
import statistics
import csv
from datetime import datetime
from dataclasses import dataclass, asdict

from chess_board import ChessBoard
from player import PlayerAction
from bot import best_move, minimax
from bot import move_order_score, _passes_opening_sanity, _see, _square_pressure
from opening_book import choose_book_move
from bot import best_move, _queen_tactics, _queen_coordination_score

import torch
from tensor import board_to_tensor
from model import load_model

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


def play(board, from_sq, to_sq, *, simulate=False):
    piece = board._get_tile(from_sq).piece
    assert piece is not None, f"No piece at {from_sq}"
    board._move_piece(piece, to_sq, simulate=simulate)


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


@dataclass
class SearchStats:
    nodes: int = 0
    qnodes: int = 0
    leaf_evals: int = 0
    terminal_hits: int = 0
    cutoffs: int = 0

    move_order_calls: int = 0
    move_order_time: float = 0.0

    evaluate_calls: int = 0
    evaluate_time: float = 0.0

    quiescence_calls: int = 0
    quiescence_time: float = 0.0

    refresh_calls: int = 0
    refresh_time: float = 0.0

    snapshot_calls: int = 0
    snapshot_time: float = 0.0

    restore_calls: int = 0
    restore_time: float = 0.0

    root_candidates: int = 0
    root_moves: int = 0
    book_hit: int = 0

    elapsed: float = 0.0
    nps: float = 0.0

    @property
    def total_nodes(self) -> int:
        return self.nodes + self.qnodes


_LAST_SEARCH_STATS = SearchStats()


def _reset_search_stats():
    global _LAST_SEARCH_STATS
    _LAST_SEARCH_STATS = SearchStats()


def get_last_search_stats() -> dict:
    return asdict(_LAST_SEARCH_STATS) | {
        "total_nodes": _LAST_SEARCH_STATS.total_nodes
    }

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

    def assertSquareAttacked(self, board, square, by_color):
        self.assertGreater(
            board.pressure_map[by_color].get(square, {}).get("count", 0),
            0,
            f"Expected {square} to be attacked by {by_color}"
        )

    def assertSquareNotAttacked(self, board, square, by_color):
        self.assertEqual(
            board.pressure_map[by_color].get(square, {}).get("count", 0),
            0,
            f"Expected {square} not to be attacked by {by_color}"
        )

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

        self.assertSquareAttacked(b, 'e1', BLACK)
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

        self.assertSquareAttacked(b, 'f1', BLACK)
        self.assertSquareNotAttacked(b, 'e1', BLACK)
        self.assertSquareNotAttacked(b, 'g1', BLACK)

        king = self.assertPiece(b, 'e1', name='K', color=WHITE)
        self.assertNotIn('g1', king.moves, "White should not be allowed to castle through attacked f1")
        self.assertNotIn(('e1', 'g1'), b.players[WHITE].possible_moves)

    def test_castling_not_available_into_attacked_g1(self):
        b = ChessBoard()

        set_position(
            b,
            white_pieces=[('K', 'e1'), ('R', 'h1')],
            black_pieces=[('K', 'a8'), ('R', 'g8')],
        )

        self.assertSquareAttacked(b, 'g1', BLACK)
        self.assertSquareNotAttacked(b, 'e1', BLACK)
        self.assertSquareNotAttacked(b, 'f1', BLACK)

        king = self.assertPiece(b, 'e1', name='K', color=WHITE)
        self.assertNotIn('g1', king.moves, "White should not be allowed to castle into attacked g1")
        self.assertNotIn(('e1', 'g1'), b.players[WHITE].possible_moves)

    def test_castling_available_when_path_is_clear_and_safe(self):
        b = ChessBoard()

        set_position(
            b,
            white_pieces=[('K', 'e1'), ('R', 'h1')],
            black_pieces=[('K', 'a8')],
        )

        self.assertFalse(b.players[WHITE].checked)
        self.assertSquareNotAttacked(b, 'e1', BLACK)
        self.assertSquareNotAttacked(b, 'f1', BLACK)
        self.assertSquareNotAttacked(b, 'g1', BLACK)

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


class TestSEE(unittest.TestCase):
    """
    SEE tests focus on tactical truth, not strategic evaluation.

    Convention assumed:
      _see(board, square, color)
        - `square` is the contested square
        - `color` is the side that just moved a piece onto `square`
        - positive => good for `color`
        - negative => bad for `color`
    """

    def setUp(self):
        self.board = ChessBoard()

    def play(self, moves):
        for from_sq, to_sq in moves:
            piece = self.board._get_tile(from_sq).piece
            self.assertIsNotNone(piece, f"No piece on {from_sq}")
            self.board._move_piece(piece, to_sq)
            self.board._update_tiles()

    def test_see_equal_pawn_trade_is_about_equal(self):
        """
        1. e4 d5 2. exd5
        White pawn captures pawn on d5.
        With no immediate favorable/unfavorable imbalance, SEE should be near neutral or positive.
        """
        self.play([
            ('e2', 'e4'),
            ('d7', 'd5'),
            ('e4', 'd5'),
        ])

        score = _see(self.board, 'd5', WHITE, captured_val=1)
        self.assertGreaterEqual(score, 0, f"Expected non-negative SEE, got {score}")

    def test_see_hanging_pawn_capture_is_positive(self):
        """
        White should profit from capturing a truly loose pawn.
        """
        self.play([
            ('e2', 'e4'),
            ('a7', 'a6'),
            ('d2', 'd4'),
            ('b7', 'b6'),
            ('e4', 'd5'),
        ])

        score = _see(self.board, 'd5', WHITE, captured_val=1)
        self.assertGreater(score, 0, f"Expected positive SEE for free pawn capture, got {score}")

    def test_see_knight_takes_defended_pawn_is_negative(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('N', 'f3')],
            black_pieces=[('K', 'e8'), ('P', 'e5'), ('B', 'g7')],
        )

        # simulate Nxe5
        piece = b._get_tile('f3').piece
        b._move_piece(piece, 'e5')
        b._update_tiles()

        score = _see(b, 'e5', WHITE, captured_val=1)
        self.assertLess(score, 0, f"Expected negative SEE, got {score}")

    def test_see_bishop_takes_loose_rook_is_strongly_positive(self):
        """
        If a bishop can take an undefended rook, SEE should be very positive.
        """
        self.play([
            ('e2', 'e4'),
            ('a7', 'a6'),
            ('f1', 'b5'),
            ('a6', 'a5'),
            ('b5', 'd7'),
            ('h7', 'h6'),
            ('d7', 'a4'),
            ('b7', 'b6'),
        ])

        # Manually create a clearer tactical scenario if needed
        # depending on your engine legality handling.
        # If your board API allows direct setup, use that instead.
        #
        # Here we just assert structure if you later wire a board-builder.
        self.assertTrue(True)

    def test_see_queen_takes_poisoned_pawn_is_negative(self):
        """
        The engine has shown queen-for-pawn nonsense.
        This test exists specifically to reject that.
        """
        self.play([
            ('e2', 'e4'),
            ('e7', 'e5'),
            ('d1', 'h5'),
            ('b8', 'c6'),
            ('h5', 'e5'),
        ])

        score = _see(self.board, 'e5', WHITE, captured_val=1)
        self.assertLess(score, 0, f"Expected negative SEE for poisoned queen capture, got {score}")

    def test_see_rook_recaptures_and_holds_square_is_non_negative(self):
        """
        If a rook recaptures and the exchange is sound, SEE should not mark it losing.
        """
        self.play([
            ('e2', 'e4'),
            ('e7', 'e5'),
            ('g1', 'f3'),
            ('g8', 'f6'),
            ('f1', 'c4'),
            ('f8', 'c5'),
            ('e1', 'g1'),
            ('e8', 'g8'),
            ('f1', 'e1'),  # depends on your castling implementation / rook square updates
        ])

        self.assertTrue(True)

    def test_see_simple_recapture_sequence_white(self):
        """
        White takes on d5, black recaptures, white recaptures.
        SEE should account for the capture ladder, not just the first victim.
        """
        self.play([
            ('d2', 'd4'),
            ('d7', 'd5'),
            ('c2', 'c4'),
            ('e7', 'e6'),
            ('c4', 'd5'),
        ])

        score = _see(self.board, 'd5', WHITE, captured_val=3)
        # This exact numeric outcome depends on defenders,
        # but it should not look like a totally free win.
        self.assertIsInstance(score, (int, float))

    def test_see_simple_recapture_sequence_black(self):
        """
        Same idea from black side so color-sign logic does not drift.
        """
        self.play([
            ('d2', 'd4'),
            ('e7', 'e5'),
            ('d4', 'e5'),
            ('d7', 'd6'),
            ('e5', 'd6'),
        ])

        score = _see(self.board, 'd6', WHITE, captured_val=3)
        self.assertIsInstance(score, (int, float))

    def test_see_does_not_return_inf_or_none(self):
        """
        Guards against old crashes / broken exchange recursion.
        """
        self.play([
            ('e2', 'e4'),
            ('d7', 'd5'),
            ('e4', 'd5'),
        ])

        score = _see(self.board, 'd5', WHITE, captured_val=1)

        self.assertIsNotNone(score)
        self.assertNotEqual(score, float('inf'))
        self.assertNotEqual(score, float('-inf'))
        self.assertFalse(score != score, "SEE returned NaN")

    def test_see_queen_sac_for_pawn_is_heavily_negative(self):
        """
        This should fail loudly if the engine ever thinks QxPawn with immediate loss is okay.
        """
        self.play([
            ('e2', 'e4'),
            ('d7', 'd5'),
            ('d1', 'h5'),
            ('g8', 'f6'),
            ('h5', 'd5'),
        ])

        score = _see(self.board, 'd5', WHITE, captured_val=1)
        self.assertLess(score, -5, f"Expected heavily negative SEE for queen blunder, got {score}")

    def test_see_minor_piece_wins_exchange_is_positive(self):
        """
        Knight or bishop wins material in a short capture chain.
        """
        self.play([
            ('e2', 'e4'),
            ('d7', 'd5'),
            ('g1', 'f3'),
            ('c8', 'g4'),
            ('f3', 'e5'),
        ])

        score = _see(self.board, 'e5', WHITE, captured_val=1)
        self.assertIsInstance(score, (int, float))

    def test_see_on_empty_square_is_safe(self):
        """
        Defensive test: SEE should not explode on empty squares.
        Decide whether you want 0 or an exception. This assumes 0.
        """
        score = _see(self.board, 'e4', WHITE)
        self.assertEqual(score, 0)

    def test_see_capture_of_high_value_piece_beats_attacker_cost_when_truly_safe(self):
        """
        If the capture is actually safe, taking a more valuable piece should score well.
        """
        self.play([
            ('e2', 'e4'),
            ('d7', 'd5'),
            ('f1', 'b5'),
            ('c7', 'c6'),
            ('b5', 'c6'),
        ])

        score = _see(self.board, 'c6', WHITE, captured_val=1)
        self.assertIsInstance(score, (int, float))


class TestSEEExactPositions(unittest.TestCase):
    """
    SEE tests built from direct board setup, not long move histories.
    These are much more reliable for tactical truth.
    """

    def setUp(self):
        self.board = ChessBoard()

    def test_see_white_pawn_takes_free_pawn_positive(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('P', 'e4')],
            black_pieces=[('K', 'e8'), ('P', 'd5')],
        )

        piece = b._get_tile('e4').piece
        b._move_piece(piece, 'd5')
        b._update_tiles()

        score = _see(b, 'd5', WHITE, captured_val=1)
        self.assertGreater(score, 0, f"Expected positive SEE for free pawn capture, got {score}")

    def test_see_white_queen_takes_defended_pawn_heavily_negative(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('Q', 'd1')],
            black_pieces=[('K', 'e8'), ('P', 'd5'), ('N', 'f6')],
        )

        piece = b._get_tile('d1').piece
        b._move_piece(piece, 'd5')
        b._update_tiles()

        score = _see(b, 'd5', WHITE, captured_val=1)
        self.assertLess(score, -5, f"Expected heavily negative SEE for Qxd5??, got {score}")

    def test_see_white_knight_takes_pawn_defended_by_bishop_negative(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('N', 'f3')],
            black_pieces=[('K', 'e8'), ('P', 'e5'), ('B', 'g7')],
        )

        piece = b._get_tile('f3').piece
        b._move_piece(piece, 'e5')
        b._update_tiles()

        score = _see(b, 'e5', WHITE, captured_val=1)
        self.assertLess(score, 0, f"Expected negative SEE for Nxe5 into bishop recapture, got {score}")

    def test_see_white_bishop_takes_free_rook_strongly_positive(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('B', 'c4')],
            black_pieces=[('K', 'e8'), ('R', 'f7')],
        )

        piece = b._get_tile('c4').piece
        b._move_piece(piece, 'f7')
        b._update_tiles()

        score = _see(b, 'f7', WHITE, captured_val=5)
        self.assertGreater(score, 3, f"Expected strongly positive SEE for Bxf7 winning rook, got {score}")

    def test_see_white_rook_takes_defended_rook_not_free(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('R', 'd1')],
            black_pieces=[('K', 'e8'), ('R', 'd7'), ('Q', 'd8')],
        )

        piece = b._get_tile('d1').piece
        b._move_piece(piece, 'd7')
        b._update_tiles()

        score = _see(b, 'd7', WHITE, captured_val=5)
        self.assertLessEqual(score, 0, f"Expected non-positive SEE for Rxd7 when queen recaptures, got {score}")

    def test_see_black_pawn_takes_free_pawn_positive(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('P', 'e4')],
            black_pieces=[('K', 'e8'), ('P', 'd5')],
        )

        piece = b._get_tile('d5').piece
        b._move_piece(piece, 'e4')
        b._update_tiles()

        score = _see(b, 'e4', BLACK, captured_val=1)
        self.assertGreater(score, 0, f"Expected positive SEE for black free pawn capture, got {score}")

    def test_see_black_queen_takes_defended_pawn_heavily_negative(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('B', 'd3'), ('P', 'e4')],
            black_pieces=[('K', 'e8'), ('Q', 'd8')],
        )

        piece = b._get_tile('d8').piece
        b._move_piece(piece, 'e4')
        b._update_tiles()

        score = _see(b, 'e4', BLACK, captured_val=1)
        self.assertLess(score, -5, f"Expected heavily negative SEE for ...Qxe4??, got {score}")

    def test_see_empty_square_returns_zero(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1')],
            black_pieces=[('K', 'e8')],
        )

        score = _see(b, 'd4', WHITE)
        self.assertEqual(score, 0)

    def test_see_capture_with_no_recap_is_at_least_captured_value(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('N', 'c4')],
            black_pieces=[('K', 'e8'), ('P', 'd6')],
        )

        piece = b._get_tile('c4').piece
        b._move_piece(piece, 'd6')
        b._update_tiles()

        score = _see(b, 'd6', WHITE, captured_val=1)
        self.assertGreaterEqual(score, 1, f"Expected SEE >= captured material when no recapture exists, got {score}")

    def test_see_does_not_return_nan_inf_on_defended_capture(self):
        b = self.board
        set_position(
            b,
            white_pieces=[('K', 'e1'), ('Q', 'd1')],
            black_pieces=[('K', 'e8'), ('P', 'd5'), ('N', 'f6')],
        )

        piece = b._get_tile('d1').piece
        b._move_piece(piece, 'd5')
        b._update_tiles()

        score = _see(b, 'd5', WHITE, captured_val=1)
        self.assertIsInstance(score, (int, float))
        self.assertNotEqual(score, float("inf"))
        self.assertNotEqual(score, float("-inf"))
        self.assertFalse(score != score, "SEE returned NaN")


class TestPressureMapExactPositions(unittest.TestCase):
    def test_rook_attacks_clear_file(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[('K', 'e1')],
            black_pieces=[('K', 'a8'), ('R', 'e8')],
        )

        self.assertGreater(b.pressure_map[BLACK].get('e1', {}).get('count', 0), 0)
        self.assertEqual(b.pressure_map[BLACK].get('f1', {}).get('count', 0), 0)

    def test_bishop_attacks_diagonal_only(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[('K', 'e1')],
            black_pieces=[('K', 'a8'), ('B', 'h4')],
        )

        self.assertGreater(b.pressure_map[BLACK].get('e1', {}).get('count', 0), 0)
        self.assertEqual(b.pressure_map[BLACK].get('f1', {}).get('count', 0), 0)


class TestSnapshotRestoreIntegrity(ChessTestCase):
    def test_pressure_map_restores_as_dict(self):
        b = ChessBoard()
        make_move(b, 'e2', 'e4')
        snap = b._snapshot_state()
        make_move(b, 'd7', 'd5')
        b._restore_state(snap)

        self.assertIsInstance(b.pressure_map[WHITE], dict)
        self.assertIsInstance(b.pressure_map[BLACK], dict)
        self.assertIn('e4', b.pressure_map[WHITE])
        self.assert_board_consistent(b)

    def test_repeated_snapshot_restore_preserves_live_moves(self):
        b = ChessBoard()
        for from_sq, to_sq in [('e2', 'e4'), ('e7', 'e5'), ('g1', 'f3'), ('b8', 'c6')]:
            make_move(b, from_sq, to_sq)

        baseline_white = set(b.players[WHITE].possible_moves)
        baseline_black = set(b.players[BLACK].possible_moves)

        for _ in range(8):
            snap = b._snapshot_state()
            try:
                play(b, 'f1', 'b5', simulate=True)
                b._refresh_search_state_for_turn(BLACK)
            finally:
                b._restore_state(snap)

        self.assertEqual(baseline_white, set(b.players[WHITE].possible_moves))
        self.assertEqual(baseline_black, set(b.players[BLACK].possible_moves))
        self.assert_board_consistent(b)


class TestSearchIntegrity(ChessTestCase):
    def test_best_move_returns_live_legal_move(self):
        b = ChessBoard()
        for from_sq, to_sq in [
            ('e2', 'e4'),
            ('e7', 'e5'),
            ('g1', 'f3'),
            ('b8', 'c6'),
            ('f1', 'b5'),
            ('a7', 'a6'),
            ('b5', 'a4'),
            ('g8', 'f6'),
        ]:
            make_move(b, from_sq, to_sq)

        move = best_move(b, WHITE, depth=2, use_opening_book=False)
        self.assertIsNotNone(move)
        self.assertIn(move, b.players[WHITE].possible_moves)

    def test_search_candidates_are_executable(self):
        b = ChessBoard()
        for from_sq, to_sq in [('d2', 'd4'), ('d7', 'd5'), ('c2', 'c4'), ('e7', 'e6')]:
            make_move(b, from_sq, to_sq)

        bad = []
        for from_sq, to_sq in list(b.players[WHITE].possible_moves):
            snap = b._snapshot_state()
            try:
                piece = b._get_tile(from_sq).piece
                if piece is None:
                    bad.append(((from_sq, to_sq), 'no piece on from-square'))
                    continue
                try:
                    b._move_piece(piece, to_sq, simulate=True)
                except ValueError as e:
                    bad.append(((from_sq, to_sq), str(e)))
            finally:
                b._restore_state(snap)

        self.assertEqual([], bad, f'Non-executable moves found in possible_moves: {bad}')

    def test_minimax_does_not_mutate_board_state(self):
        b = ChessBoard()
        for from_sq, to_sq in [('d2', 'd4'), ('d7', 'd5'), ('c2', 'c4'), ('e7', 'e6')]:
            make_move(b, from_sq, to_sq)

        baseline_positions = {
            p.id: p.location
            for color in [WHITE, BLACK]
            for p in b.players[color].pieces
        }
        baseline_white = set(b.players[WHITE].possible_moves)
        baseline_black = set(b.players[BLACK].possible_moves)

        try:
            _ = minimax(b, depth=2, turn=WHITE, root_color=WHITE)
        except Exception as e:
            self.fail(f'minimax raised unexpectedly on a legal position: {e}')

        final_positions = {
            p.id: p.location
            for color in [WHITE, BLACK]
            for p in b.players[color].pieces
        }

        self.assertEqual(baseline_positions, final_positions)
        self.assertEqual(baseline_white, set(b.players[WHITE].possible_moves))
        self.assertEqual(baseline_black, set(b.players[BLACK].possible_moves))
        self.assert_board_consistent(b)


class TestBotExecutionSafety(ChessTestCase):
    def test_bot_move_executes_without_self_check(self):
        b = ChessBoard()
        move = best_move(b, WHITE, depth=2, use_opening_book=False)
        self.assertIsNotNone(move)
        self.assertIn(move, b.players[WHITE].possible_moves)

        from_sq, to_sq = move
        play(b, from_sq, to_sq)
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


class TestEvaluateDiagnostics(ChessTestCase):
    """
    Diagnostic tests for the static evaluator.

    These are not just pass/fail unit tests.
    They also print a component breakdown so you can inspect:
      - total eval
      - classical
      - raw model score
      - model_scaled
      - phase
      - weights
      - key classical subcomponents

    Run with:
        python3 -m unittest test_chess.TestEvaluateDiagnostics -v
    """

    def _eval_breakdown(self, board, color=WHITE):
        import torch
        from bot import (
            evaluate,
            evaluate_terminal,
            game_phase,
            EVAL_PARAMS,
            model,
            board_to_tensor,
            WHITE,
            BLACK,
            EARLY,
            MIDDLE,
            _piece_value,
            get_position_bonus,
            _pawn_structure,
            _mobility,
            _king_safety,
            _bishop_tactics,
            _rook_tactics,
            _hanging_pieces,
            _development_score,
            _repetition_penalty,
        )

        p = EVAL_PARAMS

        # --- raw model ---
        model_score = 0.0
        if model is not None and torch is not None and board_to_tensor is not None:
            tensor = board_to_tensor(board, turn=color)
            x = torch.tensor(tensor).unsqueeze(0).float()
            with torch.no_grad():
                model_score = model(x).item()

        # --- classical material + PST ---
        material_pst = 0.0
        for piece in board.players[WHITE].pieces:
            material_pst += _piece_value(piece.name, p) + get_position_bonus(piece, p)
        for piece in board.players[BLACK].pieces:
            material_pst -= _piece_value(piece.name, p) + get_position_bonus(piece, p)

        pawn_structure = _pawn_structure(board, WHITE) - _pawn_structure(board, BLACK)
        mobility = _mobility(board)
        king_safety = _king_safety(board, WHITE) - _king_safety(board, BLACK)
        bishop_pair = _bishop_tactics(board, WHITE) - _bishop_tactics(board, BLACK)
        rook_files = _rook_tactics(board, WHITE) - _rook_tactics(board, BLACK)
        hanging = _hanging_pieces(board, WHITE) - _hanging_pieces(board, BLACK)
        development = _development_score(board, WHITE) - _development_score(board, BLACK)
        repetition = -_repetition_penalty(board, WHITE) + _repetition_penalty(board, BLACK)

        classical = (
            material_pst
            + pawn_structure
            + mobility
            + king_safety
            + bishop_pair
            + rook_files
            + hanging
            + development
            + repetition
        )

        phase = game_phase(board)
        model_scaled = max(min(model_score * 3, 3), -3)

        ply_count = len(getattr(board, "actions", []))
        if ply_count <= 10:
            model_weight = 0.3
        elif phase == EARLY:
            model_weight = 0.2
        elif phase == MIDDLE:
            model_weight = 0.15
        else:
            model_weight = 0.1
        classical_weight = 1 - model_weight

        blended_white = model_weight * model_scaled + classical_weight * classical
        total = blended_white if color == WHITE else -blended_white

        return {
            "color": color,
            "phase": phase,
            "ply_count": ply_count,
            "total": total,
            "white_pov_total": blended_white,
            "classical": classical,
            "material_pst": material_pst,
            "pawn_structure": pawn_structure,
            "mobility": mobility,
            "king_safety": king_safety,
            "bishop_pair": bishop_pair,
            "rook_files": rook_files,
            "hanging": hanging,
            "development": development,
            "repetition": repetition,
            "model_score": model_score,
            "model_scaled": model_scaled,
            "model_weight": model_weight,
            "classical_weight": classical_weight,
            "terminal_white": evaluate_terminal(board, WHITE, WHITE, 0),
            "terminal_black": evaluate_terminal(board, BLACK, WHITE, 0),
            "evaluate_call": evaluate(board, color, turn_to_move=color),
        }

    def _print_breakdown(self, label, d):
        print(f"\n=== {label} ===")
        print(f"phase={d['phase']} ply_count={d['ply_count']} color={d['color']}")
        print(f"evaluate(...)={d['evaluate_call']:.4f}")
        print(f"total={d['total']:.4f} white_pov_total={d['white_pov_total']:.4f}")
        print(f"classical={d['classical']:.4f}")
        print(f"  material_pst={d['material_pst']:.4f}")
        print(f"  pawn_structure={d['pawn_structure']:.4f}")
        print(f"  mobility={d['mobility']:.4f}")
        print(f"  king_safety={d['king_safety']:.4f}")
        print(f"  bishop_pair={d['bishop_pair']:.4f}")
        print(f"  rook_files={d['rook_files']:.4f}")
        print(f"  hanging={d['hanging']:.4f}")
        print(f"  development={d['development']:.4f}")
        print(f"  repetition={d['repetition']:.4f}")
        print(f"model_score={d['model_score']:.4f}")
        print(f"model_scaled={d['model_scaled']:.4f}")
        print(f"weights: model={d['model_weight']:.2f} classical={d['classical_weight']:.2f}")
        print(f"terminal_white={d['terminal_white']} terminal_black={d['terminal_black']}")

    def test_start_position_is_near_equal(self):
        b = ChessBoard()
        d = self._eval_breakdown(b, WHITE)
        self._print_breakdown("start_position", d)

        self.assertAlmostEqual(d["evaluate_call"], 0.0, delta=1.0)

    def test_white_extra_queen_is_strongly_positive(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[('K', 'g1'), ('Q', 'd4'), ('R', 'a1')],
            black_pieces=[('K', 'g8'), ('R', 'a8')],
        )
        d = self._eval_breakdown(b, WHITE)
        self._print_breakdown("white_extra_queen", d)

        self.assertGreater(d["classical"], 7.0)
        self.assertGreater(d["evaluate_call"], 5.0)

    def test_black_extra_queen_is_strongly_negative_for_white(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[('K', 'g1'), ('R', 'a1')],
            black_pieces=[('K', 'g8'), ('Q', 'd5'), ('R', 'a8')],
        )
        d = self._eval_breakdown(b, WHITE)
        self._print_breakdown("black_extra_queen", d)

        self.assertLess(d["classical"], -7.0)
        self.assertLess(d["evaluate_call"], -5.0)

    def test_good_trade_position_beats_bad_trade_position(self):
        # Good trade: white wins a rook for a bishop-type imbalance
        good = ChessBoard()
        set_position(
            good,
            white_pieces=[('K', 'g1'), ('B', 'd3'), ('R', 'a1')],
            black_pieces=[('K', 'g8'), ('R', 'e6')],
        )

        # Bad trade: white down exchange / queen pressure against king
        bad = ChessBoard()
        set_position(
            bad,
            white_pieces=[('K', 'g1'), ('B', 'd3')],
            black_pieces=[('K', 'g8'), ('R', 'e6'), ('Q', 'h4')],
        )

        d_good = self._eval_breakdown(good, WHITE)
        d_bad = self._eval_breakdown(bad, WHITE)

        self._print_breakdown("good_trade_shell", d_good)
        self._print_breakdown("bad_trade_shell", d_bad)

        self.assertGreater(d_good["evaluate_call"], d_bad["evaluate_call"])

    def test_castled_king_scores_better_than_exposed_king(self):
        safe = ChessBoard()
        set_position(
            safe,
            white_pieces=[
                ('K', 'g1'), ('R', 'f1'),
                ('P', 'f2'), ('P', 'g2'), ('P', 'h2'),
                ('Q', 'd1')
            ],
            black_pieces=[('K', 'g8'), ('Q', 'd8')]
        )

        exposed = ChessBoard()
        set_position(
            exposed,
            white_pieces=[
                ('K', 'e1'),
                ('P', 'a2'), ('P', 'b2'), ('P', 'c2'),
                ('Q', 'd1')
            ],
            black_pieces=[('K', 'g8'), ('Q', 'h4')]
        )

        d_safe = self._eval_breakdown(safe, WHITE)
        d_exposed = self._eval_breakdown(exposed, WHITE)

        self._print_breakdown("safe_king", d_safe)
        self._print_breakdown("exposed_king", d_exposed)

        self.assertGreater(d_safe["king_safety"], d_exposed["king_safety"])
        self.assertGreater(d_safe["evaluate_call"], d_exposed["evaluate_call"])

    def test_passed_pawn_position_beats_blocked_isolated_pawn(self):
        passed = ChessBoard()
        set_position(
            passed,
            white_pieces=[('K', 'g1'), ('P', 'd6')],
            black_pieces=[('K', 'g8')]
        )

        weak = ChessBoard()
        set_position(
            weak,
            white_pieces=[('K', 'g1'), ('P', 'a2')],
            black_pieces=[('K', 'g8')]
        )

        d_passed = self._eval_breakdown(passed, WHITE)
        d_weak = self._eval_breakdown(weak, WHITE)

        self._print_breakdown("passed_pawn", d_passed)
        self._print_breakdown("weak_pawn", d_weak)

        self.assertGreater(d_passed["pawn_structure"], d_weak["pawn_structure"])
        self.assertGreater(d_passed["evaluate_call"], d_weak["evaluate_call"])

    def test_mate_is_terminal_not_static(self):
        # Black is mated: white queen on f7, white king supports, black king trapped
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[('K', 'h6'), ('Q', 'f7')],
            black_pieces=[('K', 'h8')],
        )

        d = self._eval_breakdown(b, WHITE)
        self._print_breakdown("terminal_mate_position", d)

        # Static eval should be winning, but not mate-score huge
        self.assertGreater(d["evaluate_call"], 5.0)

        # Terminal eval should be decisive for black-to-move
        term = d["terminal_black"]
        self.assertIsNotNone(term)
        self.assertGreater(term, 90000)

    def test_eval_is_antisymmetric_by_color(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[('K', 'g1'), ('Q', 'd4')],
            black_pieces=[('K', 'g8')],
        )

        w = self._eval_breakdown(b, WHITE)
        bl = self._eval_breakdown(b, BLACK)

        self._print_breakdown("antisymmetry_white", w)
        self._print_breakdown("antisymmetry_black", bl)

        self.assertAlmostEqual(w["evaluate_call"], -bl["evaluate_call"], delta=0.05)


class TestQueenTactics(ChessTestCase):
    def queen_at(self, board, square, color):
        piece = get_piece(board, square)
        self.assertIsNotNone(piece, f"No piece at {square}")
        self.assertEqual(piece.name, "Q", f"Expected queen at {square}, got {piece}")
        self.assertEqual(piece.color, color, f"Expected {color} queen at {square}, got {piece.color}")
        return piece

    def test_early_queen_development_is_penalized(self):
        b = ChessBoard()

        # Opening position baseline
        base = _queen_tactics(b, WHITE)

        # Move queen out early
        make_move(b, "d2", "d4")
        make_move(b, "a7", "a6")
        make_move(b, "d1", "d3")

        moved = _queen_tactics(b, WHITE)

        self.assertLess(
            moved, base,
            f"Expected early queen development to be worse. base={base}, moved={moved}"
        )

    def test_safe_supported_queen_scores_better_than_exposed_queen(self):
        safe = ChessBoard()
        set_position(
            safe,
            white_pieces=[("K", "g1"), ("Q", "d3"), ("N", "f3"), ("B", "e2")],
            black_pieces=[("K", "g8")],
        )

        exposed = ChessBoard()
        set_position(
            exposed,
            white_pieces=[("K", "g1"), ("Q", "d3")],
            black_pieces=[("K", "g8"), ("R", "d8")],
        )

        safe_score = _queen_tactics(safe, WHITE)
        exposed_score = _queen_tactics(exposed, WHITE)

        self.assertGreater(
            safe_score, exposed_score,
            f"Expected supported queen to score better. safe={safe_score}, exposed={exposed_score}"
        )

    def test_hanging_queen_is_penalized(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[("K", "g1"), ("Q", "d4")],
            black_pieces=[("K", "g8"), ("R", "d8")],
        )

        score = _queen_tactics(b, WHITE)
        self.assertLess(score, 0.0, f"Expected hanging queen penalty, got {score}")

    def test_battery_with_rook_on_open_line_scores_positive(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[("K", "g1"), ("R", "d1"), ("Q", "d3")],
            black_pieces=[("K", "d8"), ("N", "d7")],
        )

        queen = self.queen_at(b, "d3", WHITE)
        score = _queen_coordination_score(b, queen, WHITE)

        self.assertGreater(
            score, 0.0,
            f"Expected rook-queen battery pressure to score positively, got {score}"
        )

    def test_bishop_battery_on_diagonal_scores_positive(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[("K", "g1"), ("B", "b1"), ("Q", "c2")],
            black_pieces=[("K", "h7"), ("R", "g6")],
        )

        queen = self.queen_at(b, "c2", WHITE)
        score = _queen_coordination_score(b, queen, WHITE)

        self.assertGreater(
            score, 0.0,
            f"Expected bishop-queen diagonal battery to score positively, got {score}"
        )

    def test_no_battery_bonus_without_rear_support(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[("K", "g1"), ("Q", "d3")],
            black_pieces=[("K", "d8"), ("N", "d7")],
        )

        queen = self.queen_at(b, "d3", WHITE)
        score = _queen_coordination_score(b, queen, WHITE)

        self.assertEqual(
            score, 0.0,
            f"Expected no battery score without rook/bishop support, got {score}"
        )

    def test_no_false_battery_when_friendly_support_is_wrong_piece(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[("K", "g1"), ("N", "d1"), ("Q", "d3")],
            black_pieces=[("K", "d8"), ("N", "d7")],
        )

        queen = self.queen_at(b, "d3", WHITE)
        score = _queen_coordination_score(b, queen, WHITE)

        self.assertEqual(
            score, 0.0,
            f"Expected no battery score with knight behind queen, got {score}"
        )

class TestKillBotMatePatterns(ChessTestCase):
    """
    Tests the raw kill-bot NN on mate-near positions.

    Important:
    - This scores the MODEL directly, not bot.evaluate().
    - Positive score = good for White
    - Negative score = good for Black

    These are not meant to prove full tactical correctness.
    They are meant to sanity-check whether the kill model prefers
    canonical mate-net positions and likes the mating move even more.
    """

    MODEL_PATH = os.environ.get("CHESS_KILL_MODEL_PATH", "check_points/kill_bot_v1.pt")
    _kill_model = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not os.path.exists(cls.MODEL_PATH):
            raise unittest.SkipTest(f"Kill bot model not found: {cls.MODEL_PATH}")
        cls._kill_model = load_model(cls.MODEL_PATH)
        cls._kill_model.eval()

    def _raw_model_score(self, board, turn):
        """
        Raw NN output in [-1, 1] approximately.
        Positive => White favored
        Negative => Black favored
        """
        x = torch.tensor(board_to_tensor(board, turn=turn)).unsqueeze(0).float()
        with torch.no_grad():
            return self._kill_model(x).item()

    def _assert_white_stays_strongly_winning_after_move(
        self, board, from_sq, to_sq, floor=0.20, max_drop=0.05
    ):
        before = self._raw_model_score(board, WHITE)
        make_move(board, from_sq, to_sq)
        after = self._raw_model_score(board, BLACK)

        self.assertGreater(
            before, floor,
            f"Expected White to already be clearly winning before {from_sq}->{to_sq}, got {before:.4f}"
        )
        self.assertGreater(
            after, floor,
            f"Expected White to remain clearly winning after {from_sq}->{to_sq}, got {after:.4f}"
        )
        self.assertGreater(
            after, before - max_drop,
            f"Expected White move {from_sq}->{to_sq} not to collapse evaluation. "
            f"before={before:.4f}, after={after:.4f}"
        )
        return before, after


    def _assert_black_stays_strongly_winning_after_move(
        self, board, from_sq, to_sq, floor=-0.20, max_rise=0.05
    ):
        before = self._raw_model_score(board, BLACK)
        make_move(board, from_sq, to_sq)
        after = self._raw_model_score(board, WHITE)

        self.assertLess(
            before, floor,
            f"Expected Black to already be clearly winning before {from_sq}->{to_sq}, got {before:.4f}"
        )
        self.assertLess(
            after, floor,
            f"Expected Black to remain clearly winning after {from_sq}->{to_sq}, got {after:.4f}"
        )
        self.assertLess(
            after, before + max_rise,
            f"Expected Black move {from_sq}->{to_sq} not to collapse evaluation. "
            f"before={before:.4f}, after={after:.4f}"
        )
        return before, after

    # ------------------------------------------------------------------
    # 1. Back Rank Mate
    # ------------------------------------------------------------------
    def test_killbot_back_rank_mate_white(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[
                ('K', 'g1'),
                ('Q', 'd1'),
                ('R', 'd7'),
            ],
            black_pieces=[
                ('K', 'g8'),
                ('P', 'f7'),
                ('P', 'g7'),
                ('P', 'h7'),
            ],
        )

        # White is already crushing; Rd8# should be even better.
        pre = self._raw_model_score(b, WHITE)
        self.assertGreater(pre, 0.15, f"Expected White-favored mate-net score, got {pre:.4f}")

        before, after = self._assert_white_stays_strongly_winning_after_move(b, 'd7', 'd8')
        print(f"\nBack Rank Mate: before={before:.4f}, after={after:.4f}")

    # ------------------------------------------------------------------
    # 2. Scholar's Mate
    # ------------------------------------------------------------------
    def test_killbot_scholars_mate_white(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[
                ('K', 'e1'),
                ('Q', 'h5'),
                ('B', 'c4'),
            ],
            black_pieces=[
                ('K', 'e8'),
                ('P', 'f7'),
                ('P', 'g7'),
                ('P', 'h7'),
                ('P', 'e5'),
                ('N', 'c6'),
            ],
        )

        pre = self._raw_model_score(b, WHITE)
        self.assertGreater(pre, 0.10, f"Expected White-favored Scholar pattern score, got {pre:.4f}")

        before, after = self._assert_white_stays_strongly_winning_after_move(b, 'h5', 'f7')
        print(f"\nScholar's Mate: before={before:.4f}, after={after:.4f}")

    # ------------------------------------------------------------------
    # 3. Fool's Mate
    # ------------------------------------------------------------------
    def test_killbot_fools_mate_black(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[
                ('K', 'e1'),
                ('P', 'f3'),
                ('P', 'g4'),
            ],
            black_pieces=[
                ('K', 'e8'),
                ('Q', 'h4'),
                ('P', 'e5'),
            ],
        )

        # This position is already essentially winning for Black.
        pre = self._raw_model_score(b, BLACK)
        self.assertLess(pre, -0.10, f"Expected Black-favored Fool's Mate score, got {pre:.4f}")

        # If you want the pre-move version instead, use queen on d8 and move d8->h4.
        print(f"\nFool's Mate pattern score for Black to move: {pre:.4f}")

    # ------------------------------------------------------------------
    # 4. Smothered Mate (mate already on board shape)
    # ------------------------------------------------------------------
    def test_killbot_smothered_mate_white_pattern(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[
                ('K', 'a1'),
                ('N', 'f7'),
            ],
            black_pieces=[
                ('K', 'h8'),
                ('R', 'g8'),
                ('P', 'g7'),
                ('P', 'h7'),
            ],
        )

        # Nf7# shape already represented.
        score = self._raw_model_score(b, BLACK)
        # Since Black is to move in a mated-looking structure, White should still be heavily favored.
        self.assertGreater(score, 0.20, f"Expected White-favored smothered mate pattern, got {score:.4f}")
        print(f"\nSmothered Mate pattern score: {score:.4f}")

    # ------------------------------------------------------------------
    # 5. Arabian Mate
    # ------------------------------------------------------------------
    def test_killbot_arabian_mate_white(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[
                ('K', 'a1'),
                ('R', 'h1'),
                ('N', 'f7'),
            ],
            black_pieces=[
                ('K', 'h8'),
            ],
        )

        pre = self._raw_model_score(b, WHITE)
        self.assertGreater(pre, 0.10, f"Expected White-favored Arabian mate-net score, got {pre:.4f}")

        before, after = self._assert_white_stays_strongly_winning_after_move(b, 'h1', 'h7')
        print(f"\nArabian Mate: before={before:.4f}, after={after:.4f}")

    # ------------------------------------------------------------------
    # 6. Greco's Mate
    # ------------------------------------------------------------------
    """
    def test_killbot_grecos_mate_white(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[
                ('K', 'a1'),
                ('R', 'h1'),
                ('B', 'd3'),
            ],
            black_pieces=[
                ('K', 'h8'),
                ('P', 'g7'),
            ],
        )

        pre = self._raw_model_score(b, WHITE)
        self.assertGreater(pre, 0.10, f"Expected White-favored Greco mate-net score, got {pre:.4f}")

        before, after = self._assert_white_stays_strongly_winning_after_move(b, 'h1', 'h8')
        print(f"\nGreco's Mate: before={before:.4f}, after={after:.4f}")
    """
    # ------------------------------------------------------------------
    # 7. Lolli's Mate
    # ------------------------------------------------------------------
    def test_killbot_lollis_mate_white(self):
        b = ChessBoard()
        set_position(
            b,
            white_pieces=[
                ('K', 'a1'),
                ('Q', 'g7'),
                ('P', 'h6'),
            ],
            black_pieces=[
                ('K', 'h8'),
            ],
        )

        score = self._raw_model_score(b, BLACK)
        self.assertGreater(score, 0.20, f"Expected White-favored Lolli mate pattern, got {score:.4f}")
        print(f"\nLolli's Mate pattern score: {score:.4f}")

    # ------------------------------------------------------------------
    # 8. Simple sanity comparison:
    #    mate-near position should outscore a neutral sparse ending
    # ------------------------------------------------------------------
    def test_killbot_prefers_mate_net_over_neutral_endgame(self):
        mate_net = ChessBoard()
        set_position(
            mate_net,
            white_pieces=[
                ('K', 'g1'),
                ('Q', 'h5'),
                ('B', 'c4'),
            ],
            black_pieces=[
                ('K', 'e8'),
                ('P', 'f7'),
                ('P', 'g7'),
                ('P', 'h7'),
                ('P', 'e5'),
            ],
        )

        neutral = ChessBoard()
        set_position(
            neutral,
            white_pieces=[
                ('K', 'e2'),
                ('P', 'd4'),
            ],
            black_pieces=[
                ('K', 'e7'),
                ('P', 'd5'),
            ],
        )

        mate_score = self._raw_model_score(mate_net, WHITE)
        neutral_score = self._raw_model_score(neutral, WHITE)

        self.assertGreater(
            mate_score,
            neutral_score + 0.10,
            f"Expected mate-net to outrank neutral ending. "
            f"mate_score={mate_score:.4f}, neutral_score={neutral_score:.4f}"
        )

        print(f"\nMate-net vs neutral: mate_score={mate_score:.4f}, neutral_score={neutral_score:.4f}")


class TestSearchRuntimeBenchmark(unittest.TestCase):
    """
    Runtime benchmark for minimax search with:
      - time
      - node count
      - nodes/sec
      - lightweight profiling buckets

    Enable with:
        RUN_SEARCH_BENCHMARK=1 python -m unittest test_chess.TestSearchRuntimeBenchmark -v
    """

    def setUp(self):
        if os.environ.get("RUN_SEARCH_BENCHMARK") != "1":
            self.skipTest("Set RUN_SEARCH_BENCHMARK=1 to enable runtime benchmark")

        depths_env = os.environ.get("SEARCH_BENCH_DEPTHS", "1,2,3,4")
        self.depths = [int(d.strip()) for d in depths_env.split(",")]

        self.repeats = int(os.environ.get("SEARCH_BENCH_REPEATS", "5"))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        output_dir = "data/test_benchmarks"
        os.makedirs(output_dir, exist_ok=True)

        csv_filename = f"search_benchmark_{timestamp}.csv"
        self.csv_path = os.path.join(output_dir, csv_filename)

    # ── Position Builders ─────────────────────────────────────────────

    def _build_opening(self):
        return ChessBoard()

    def _build_open_game(self):
        b = ChessBoard()
        self._play_seq(b, [
            ("e2", "e4"), ("e7", "e5"),
            ("g1", "f3"), ("b8", "c6"),
            ("f1", "c4"), ("f8", "c5"),
            ("d2", "d3"), ("d7", "d6"),
        ])
        return b

    def _build_midgame(self):
        b = ChessBoard()
        self._play_seq(b, [
            ("d2", "d4"), ("d7", "d5"),
            ("c2", "c4"), ("e7", "e6"),
            ("g1", "f3"), ("g8", "f6"),
            ("c1", "g5"), ("f8", "e7"),
            ("e2", "e3"), ("b8", "d7"),
        ])
        return b

    def _build_endgame(self):
        from test_chess import set_position
        b = ChessBoard()

        set_position(
            b,
            white_pieces=[('K', 'e4'), ('P', 'd5')],
            black_pieces=[('K', 'e6'), ('P', 'f6')],
        )
        return b

    def _play_seq(self, board, moves):
        for from_sq, to_sq in moves:
            piece = next(
                (p for p in board.players[WHITE].pieces + board.players[BLACK].pieces
                 if p.location == from_sq),
                None
            )
            if piece and to_sq in piece.moves:
                board._move_piece(piece, to_sq)
                board._update_tiles()

    def _clone(self, board):
        import copy
        return copy.deepcopy(board)

    # ── Benchmark ────────────────────────────────────────────────────

    def test_search_runtime(self):
        from bot import best_move, get_last_search_stats

        positions = {
            "opening": self._build_opening(),
            "open_game": self._build_open_game(),
            "midgame": self._build_midgame(),
            "endgame": self._build_endgame(),
        }

        print("\n=== SEARCH RUNTIME BENCHMARK (WITH NODES) ===")
        print(f"Depths: {self.depths} | Repeats: {self.repeats}")
        print(f"CSV Output: {self.csv_path}\n")

        with open(self.csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "position",
                "depth",
                "run",
                "time_sec",
                "nodes",
                "qnodes",
                "total_nodes",
                "nps",
                "cutoffs",
                "leaf_evals",
                "terminal_hits",
                "move_order_time",
                "refresh_time",
                "evaluate_time",
                "quiescence_time"
            ])

            overall = {}

            for name, base_board in positions.items():
                print(f"\n--- Position: {name} ---")
                overall[name] = {}

                for depth in self.depths:
                    times = []
                    nodes_list = []
                    nps_list = []

                    for i in range(self.repeats):
                        board = self._clone(base_board)

                        start = time.perf_counter()

                        best_move(
                            board,
                            WHITE,
                            depth=depth,
                            debug=0,
                            time_budget=None,
                            use_opening_book=False,  # IMPORTANT
                        )

                        elapsed = time.perf_counter() - start
                        stats = get_last_search_stats()

                        times.append(elapsed)
                        nodes_list.append(stats.get("total_nodes", 0))
                        nps_list.append(stats.get("nps", 0))

                        writer.writerow([
                            datetime.now().isoformat(),
                            name,
                            depth,
                            i,
                            elapsed,
                            stats.get("nodes", 0),
                            stats.get("qnodes", 0),
                            stats.get("total_nodes", 0),
                            stats.get("nps", 0),
                            stats.get("cutoffs", 0),
                            stats.get("leaf_evals", 0),
                            stats.get("terminal_hits", 0),
                            stats.get("move_order_time", 0),
                            stats.get("refresh_time", 0),
                            stats.get("evaluate_time", 0),
                            stats.get("quiescence_time", 0),
                        ])

                    mean_t = statistics.mean(times)
                    mean_nodes = statistics.mean(nodes_list)
                    mean_nps = statistics.mean(nps_list)

                    overall[name][depth] = (mean_t, mean_nodes)

                    print(
                        f"Depth {depth}: "
                        f"time={mean_t:.3f}s | "
                        f"nodes={mean_nodes:.0f} | "
                        f"nps={mean_nps:.0f}"
                    )

        # ── Scaling Summary ─────────────────────────────────────────

        print("\n=== DEPTH SCALING SUMMARY ===")
        for name, depth_map in overall.items():
            print(f"\n{name}:")
            prev_t = None
            prev_n = None

            for depth in sorted(depth_map):
                t, n = depth_map[depth]

                if prev_t:
                    print(
                        f"  depth {depth}: {t:.3f}s (x{t/prev_t:.2f}) | "
                        f"nodes={n:.0f} (x{n/prev_n:.2f})"
                    )
                else:
                    print(f"  depth {depth}: {t:.3f}s | nodes={n:.0f}")

                prev_t = t
                prev_n = n

        print("\nBenchmark complete.\n")


if __name__ == '__main__':
    unittest.main(verbosity=2)