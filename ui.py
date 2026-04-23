"""
Pygame driver for the chess game and bot.

Piece image naming convention:
  assets/1x/{color}{name}.png   e.g.  WP.png  BP.png  WR.png  WQ.png  BK.png
  Color prefix is 'W' or 'B', name is the single-letter piece code.

Modes:
  2P              pass-and-play, both sides human
  BOT             human vs bot; human_color chosen at launch
  BOT_VS_BOT      bot self-play, watch live; pick num_games, depth, debug
  CHALLENGE_SF    bot vs Stockfish ladder, watch live; pick games, depth, debug, skill params
  REVIEW          replay any saved PGN file move by move

Features:
  - Two-step menu: pick mode, then configure settings
  - Correct per-color piece image loading (White vs Black distinction)
  - PGN game saving in the same format as chess_engine.py / bot.py
  - PGN review mode: replay any saved game move by move (all subdirs searched)
  - Bot vs Bot live viewer with game-by-game stats overlay
  - Challenge Stockfish live viewer with skill-ladder progress
  - Configurable move delay so you can watch at your own pace
  - P = pause / unpause in live modes
"""

import os
import sys
import threading
import datetime
import random
import shutil
import pygame as pg

from chess_board import ChessBoard, WHITE, BLACK
from pieces import Piece
from bot import best_move, MODEL_PATH

try:
    import chess
    import chess.pgn
except Exception:
    chess = None

try:
    import chess.engine as chess_engine_mod
except Exception:
    chess_engine_mod = None

# ── Colors ────────────────────────────────────────────────────────────────────
CL_BLACK      = (0,   0,   0)
CL_WHITE      = (255, 255, 255)
CL_GRAY_DARK  = (40,  40,  40)
CL_GRAY_MID   = (100, 100, 100)
CL_GRAY_LIGHT = (200, 200, 200)
CL_YELLOW     = (240, 210,  80)
CL_LIGHT_SQ   = (240, 217, 181)
CL_DARK_SQ    = (181, 136,  99)
CL_HIGHLIGHT  = (80,  180,  80,  160)
CL_SELECTED   = (60,  140, 220,  120)
CL_LAST_FROM  = (180, 140,  50,  100)
CL_LAST_TO    = (180, 140,  50,  140)
CL_CHECK      = (220,  50,  50,  140)
CL_BTN_NORM   = (100, 100, 100)
CL_GREEN      = (80,  200,  80)
CL_RED        = (220,  60,  60)
CL_BLUE_LT    = (100, 160, 240)

# ── Layout ────────────────────────────────────────────────────────────────────
SQ       = 72
BOARD_X  = 60
BOARD_Y  = 60
BOARD_PX = 8 * SQ          # 576
WINDOW_W = BOARD_X + BOARD_PX + 60    # 696
WINDOW_H = BOARD_Y + BOARD_PX + 130   # 746
INFO_Y   = BOARD_Y + BOARD_PX + 25

RANK = ['8','7','6','5','4','3','2','1']
FILE = ['a','b','c','d','e','f','g','h']

BOT_DEPTH        = 2
BOT_TIME_BUDGET  = 60.0
LIVE_MOVE_DELAY_MS = 400     # default pause between moves in live-watch modes

PGN_SAVE_DIR     = "data/played_games/UI"
BOT_VS_BOT_DIR   = "data/played_games/UI/bot_vs_bot"
CHALLENGE_SF_DIR = "data/played_games/UI/challenge_sf"


# ── Coordinate helpers ────────────────────────────────────────────────────────

def tile_to_px(tile: str) -> tuple[int, int]:
    col = FILE.index(tile[0])
    row = RANK.index(tile[1])
    return BOARD_X + col * SQ + SQ // 2, BOARD_Y + row * SQ + SQ // 2


def px_to_tile(x: int, y: int) -> str | None:
    col = (x - BOARD_X) // SQ
    row = (y - BOARD_Y) // SQ
    if 0 <= col <= 7 and 0 <= row <= 7:
        return f"{FILE[col]}{RANK[row]}"
    return None


# ── Sprite ────────────────────────────────────────────────────────────────────

class PieceSprite(pg.sprite.Sprite):
    _cache: dict[str, pg.Surface] = {}

    def __init__(self, piece: Piece):
        super().__init__()
        self.piece_id    = piece.id
        self.piece_color = piece.color
        self.piece_name  = piece.name
        self.image = self._load(piece.color, piece.name)
        self.rect  = self.image.get_rect()
        self.rect.center = tile_to_px(piece.location)
        self.home  = self.rect.center

    @classmethod
    def _load(cls, color: str, name: str) -> pg.Surface:
        key = f"{color}{name}"
        if key in cls._cache:
            return cls._cache[key]
        sz  = SQ - 8
        img = None
        for path in [
            f"assets/1x/{color}{name}.png",
            f"assets/piece_images/{color}{name}.png",
            f"assets/{color}{name}.png",
        ]:
            if os.path.exists(path):
                try:
                    img = pg.image.load(path).convert_alpha()
                    img = pg.transform.smoothscale(img, (sz, sz))
                    break
                except Exception:
                    img = None

        if img is None:
            fill  = (240, 240, 240) if color == WHITE else (60, 60, 60)
            txt_c = (30,  30,  30)  if color == WHITE else (220, 220, 220)
            img   = pg.Surface((sz, sz), pg.SRCALPHA)
            pg.draw.circle(img, fill,    (sz//2, sz//2), sz//2)
            pg.draw.circle(img, (0,0,0), (sz//2, sz//2), sz//2, 2)
            font = pg.font.SysFont("Arial", sz//3, bold=True)
            lbl  = font.render(name, True, txt_c)
            img.blit(lbl, lbl.get_rect(center=(sz//2, sz//2)))

        cls._cache[key] = img
        return img

    def snap_to(self, tile: str):
        self.rect.center = tile_to_px(tile)
        self.home = self.rect.center

    def snap_home(self):
        self.rect.center = self.home


# ── Sprite manager ────────────────────────────────────────────────────────────

class Sprites:
    def __init__(self, board: ChessBoard):
        self.sprites: dict[str, PieceSprite] = {}
        self._sync(board)

    def _sync(self, board: ChessBoard):
        live = set()
        for color in (WHITE, BLACK):
            for piece in board.players[color].pieces:
                live.add(piece.id)
                existing = self.sprites.get(piece.id)
                if existing is None:
                    self.sprites[piece.id] = PieceSprite(piece)
                elif existing.piece_name != piece.name:
                    self.sprites[piece.id] = PieceSprite(piece)
                else:
                    existing.snap_to(piece.location)
        for pid in list(self.sprites):
            if pid not in live:
                del self.sprites[pid]

    def after_move(self, board: ChessBoard):
        self._sync(board)

    def get(self, pid: str) -> PieceSprite | None:
        return self.sprites.get(pid)

    def draw(self, surface: pg.Surface, exclude: str | None = None):
        for pid, spr in self.sprites.items():
            if pid != exclude:
                surface.blit(spr.image, spr.rect)


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _alpha_rect(surface: pg.Surface, rgba: tuple, rect: pg.Rect):
    tmp = pg.Surface((rect.w, rect.h), pg.SRCALPHA)
    tmp.fill(rgba)
    surface.blit(tmp, rect.topleft)


def draw_board(surface: pg.Surface):
    font = pg.font.SysFont("Arial", 12, bold=True)
    for row in range(8):
        for col in range(8):
            color = CL_LIGHT_SQ if (row + col) % 2 == 0 else CL_DARK_SQ
            pg.draw.rect(surface, color,
                         (BOARD_X + col * SQ, BOARD_Y + row * SQ, SQ, SQ))
    for row, rank in enumerate(RANK):
        lbl = font.render(rank, True, CL_YELLOW)
        surface.blit(lbl, (BOARD_X - 16, BOARD_Y + row * SQ + 3))
    for col, f in enumerate(FILE):
        lbl = font.render(f, True, CL_YELLOW)
        surface.blit(lbl, (
            BOARD_X + col * SQ + SQ // 2 - lbl.get_width() // 2,
            BOARD_Y + 8 * SQ + 3
        ))


def draw_overlays(surface, board, selected_piece, highlighted, last_move):
    if last_move:
        for tile, rgba in zip(last_move, (CL_LAST_FROM, CL_LAST_TO)):
            col, row = FILE.index(tile[0]), RANK.index(tile[1])
            _alpha_rect(surface, rgba,
                        pg.Rect(BOARD_X + col*SQ, BOARD_Y + row*SQ, SQ, SQ))

    for color in (WHITE, BLACK):
        if board.players[color].checked:
            sq  = board.white_king_location if color == WHITE else board.black_king_location
            col, row = FILE.index(sq[0]), RANK.index(sq[1])
            _alpha_rect(surface, CL_CHECK,
                        pg.Rect(BOARD_X + col*SQ, BOARD_Y + row*SQ, SQ, SQ))

    if selected_piece:
        col = FILE.index(selected_piece.location[0])
        row = RANK.index(selected_piece.location[1])
        _alpha_rect(surface, CL_SELECTED,
                    pg.Rect(BOARD_X + col*SQ, BOARD_Y + row*SQ, SQ, SQ))

    dot_r = SQ // 6
    for tile in highlighted:
        col, row = FILE.index(tile[0]), RANK.index(tile[1])
        tmp    = pg.Surface((SQ, SQ), pg.SRCALPHA)
        target = board._get_tile(tile)
        if target and target.piece:
            pg.draw.circle(tmp, CL_HIGHLIGHT, (SQ//2, SQ//2), SQ//2 - 4, 5)
        else:
            pg.draw.circle(tmp, CL_HIGHLIGHT, (SQ//2, SQ//2), dot_r)
        surface.blit(tmp, (BOARD_X + col*SQ, BOARD_Y + row*SQ))


def draw_hud(surface, board, turn, mode, human_color,
             bot_thinking, status_msg, game_over):
    font    = pg.font.SysFont("Arial", 16, bold=True)
    font_sm = pg.font.SysFont("Arial", 13)
    font_go = pg.font.SysFont("Arial", 32, bold=True)
    y = INFO_Y

    role = ""
    if mode == "BOT":
        role = " (You)" if turn == human_color else " (Bot)"
    color_name = "White" if turn == WHITE else "Black"
    surface.blit(font.render(f"{color_name}'s turn{role}", True,
                             CL_WHITE if turn == WHITE else CL_YELLOW),
                 (BOARD_X, y))
    y += 22

    pts = font_sm.render(
        f"W: {board.players[WHITE].points} pts   "
        f"B: {board.players[BLACK].points} pts   "
        f"Taken — W: {board.players[WHITE].taken_pieces_str}  "
        f"B: {board.players[BLACK].taken_pieces_str}",
        True, CL_GRAY_LIGHT)
    surface.blit(pts, (BOARD_X, y)); y += 18

    for color in (WHITE, BLACK):
        if board.players[color].checked and not board.players[color].mated:
            cname = "White" if color == WHITE else "Black"
            surface.blit(font_sm.render(f"{cname} is in CHECK!", True, (220,80,80)),
                         (BOARD_X, y)); y += 18

    if bot_thinking:
        surface.blit(font_sm.render("Bot is thinking…", True, (150,200,255)),
                     (BOARD_X, y)); y += 18
    if status_msg:
        surface.blit(font_sm.render(status_msg, True, CL_GRAY_LIGHT),
                     (BOARD_X, y)); y += 18

    if game_over:
        overlay = pg.Surface((WINDOW_W, WINDOW_H), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))
        if board.players[WHITE].mated:
            msg = "Black wins by checkmate!"
        elif board.players[BLACK].mated:
            msg = "White wins by checkmate!"
        else:
            msg = "Stalemate — it's a draw!"
        go = font_go.render(msg, True, CL_YELLOW)
        surface.blit(go, go.get_rect(center=(WINDOW_W//2, WINDOW_H//2 - 30)))
        hint = font_sm.render("Press ESC to return to menu", True, CL_WHITE)
        surface.blit(hint, hint.get_rect(center=(WINDOW_W//2, WINDOW_H//2 + 20)))


# ── Promotion picker ──────────────────────────────────────────────────────────

def run_promotion_picker(screen, clock, color: str) -> str:
    choices  = [('Q', 'Queen'), ('R', 'Rook'), ('B', 'Bishop'), ('N', 'Knight')]
    font_ttl = pg.font.SysFont("Arial", 22, bold=True)
    font_lbl = pg.font.SysFont("Arial", 13)
    btn_size = 80; gap = 16
    total_w  = len(choices) * btn_size + (len(choices) - 1) * gap
    panel_w  = total_w + 48; panel_h = btn_size + 80
    panel_x  = (WINDOW_W - panel_w) // 2
    panel_y  = (WINDOW_H - panel_h) // 2
    btn_y    = panel_y + 40
    btns = []
    for i, (code, name) in enumerate(choices):
        bx = panel_x + 24 + i * (btn_size + gap)
        btns.append((pg.Rect(bx, btn_y, btn_size, btn_size), code, name))
    dim = pg.Surface((WINDOW_W, WINDOW_H), pg.SRCALPHA)
    dim.fill((0, 0, 0, 180))
    while True:
        screen.blit(dim, (0, 0))
        pr = pg.Rect(panel_x, panel_y, panel_w, panel_h)
        pg.draw.rect(screen, (50,50,50), pr, border_radius=12)
        pg.draw.rect(screen, CL_YELLOW, pr, 2, border_radius=12)
        ttl = font_ttl.render("Promote pawn to…", True, CL_YELLOW)
        screen.blit(ttl, ttl.get_rect(center=(WINDOW_W//2, panel_y+18)))
        mx, my = pg.mouse.get_pos()
        for rect, code, name in btns:
            hover = rect.collidepoint(mx, my)
            img   = PieceSprite._load(color, code)
            pg.draw.rect(screen, CL_YELLOW if hover else (80,80,80), rect, border_radius=10)
            pg.draw.rect(screen, CL_WHITE, rect, 1, border_radius=10)
            screen.blit(img, img.get_rect(center=rect.center))
            lbl = font_lbl.render(name, True, CL_WHITE)
            screen.blit(lbl, lbl.get_rect(center=(rect.centerx, rect.bottom+10)))
        pg.display.flip(); clock.tick(60)
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                for rect, code, _ in btns:
                    if rect.collidepoint(event.pos):
                        return code
            if event.type == pg.KEYDOWN:
                km = {pg.K_q:'Q', pg.K_r:'R', pg.K_b:'B', pg.K_n:'N'}
                if event.key in km:
                    return km[event.key]


def _is_promotion_move(piece, to_tile: str) -> bool:
    if piece.name != 'P':
        return False
    return (piece.color == WHITE and to_tile[1] == '8') or \
           (piece.color == BLACK and to_tile[1] == '1')


# ── PGN export ────────────────────────────────────────────────────────────────

def save_pgn(board: ChessBoard, mode: str, human_color,
             result: str = "*", save_dir: str = None,
             white_name: str = None, black_name: str = None) -> str | None:
    if chess is None:
        print("python-chess not available — PGN not saved")
        return None

    out_dir = save_dir or PGN_SAVE_DIR
    os.makedirs(out_dir, exist_ok=True)
    model_name = os.path.basename(MODEL_PATH).replace(".pt", "")

    if white_name is None or black_name is None:
        if mode == "2P":
            white_name = "Player One"; black_name = "Player Two"
        elif mode == "BOT":
            if human_color == WHITE:
                white_name = "Human"; black_name = model_name
            else:
                white_name = model_name; black_name = "Human"
        elif mode == "BOT_VS_BOT":
            white_name = model_name; black_name = model_name
        elif mode == "CHALLENGE_SF":
            white_name = model_name; black_name = "Stockfish"
        else:
            white_name = "White"; black_name = "Black"

    ref  = chess.Board()
    game = chess.pgn.Game()
    game.headers["Event"]  = mode
    game.headers["Site"]   = "Local"
    game.headers["Date"]   = datetime.datetime.now().strftime("%Y.%m.%d")
    game.headers["White"]  = white_name
    game.headers["Black"]  = black_name
    game.headers["Result"] = result

    node = game
    for action in board.actions:
        uci = action.from_tile + action.to_tile
        if action.promotion:
            uci += action.promotion.lower()
        move = chess.Move.from_uci(uci)
        if move not in ref.legal_moves:
            print(f"PGN export: illegal move {uci} — aborting save")
            return None
        ref.push(move)
        node = node.add_variation(move)

    ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{model_name}_{ts}.pgn"
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        exporter = chess.pgn.FileExporter(f)
        game.accept(exporter)
    print(f"Game saved: {filepath}")
    return filepath


# ── PGN Review ────────────────────────────────────────────────────────────────

def load_pgn_games(directory: str) -> list[str]:
    """Walk all subdirs and return .pgn paths sorted newest first."""
    if not os.path.isdir(directory):
        return []
    files = []
    for root, _, fnames in os.walk(directory):
        for f in fnames:
            if f.endswith(".pgn"):
                files.append(os.path.join(root, f))
    files.sort(reverse=True)
    return files


def run_pgn_review(screen, clock):
    if chess is None:
        _show_message(screen, clock, "python-chess not installed — cannot review PGNs")
        return

    font_big = pg.font.SysFont("Arial", 28, bold=True)
    font_med = pg.font.SysFont("Arial", 17)
    font_sm  = pg.font.SysFont("Arial", 13)

    pgn_files = load_pgn_games(PGN_SAVE_DIR)
    if not pgn_files:
        _show_message(screen, clock, f"No saved games found in {PGN_SAVE_DIR}/")
        return

    selected_idx = 0; scroll_off = 0; max_visible = 12

    while True:
        screen.fill(CL_GRAY_DARK)
        title = font_big.render("Review Saved Games", True, CL_YELLOW)
        screen.blit(title, title.get_rect(center=(WINDOW_W//2, 40)))
        hint = font_sm.render("↑/↓ select  |  Enter open  |  ESC back",
                              True, CL_GRAY_LIGHT)
        screen.blit(hint, hint.get_rect(center=(WINDOW_W//2, 75)))

        visible = pgn_files[scroll_off : scroll_off + max_visible]
        for i, path in enumerate(visible):
            idx   = scroll_off + i
            try:
                label = os.path.relpath(path, PGN_SAVE_DIR)
            except Exception:
                label = os.path.basename(path)
            is_sel = (idx == selected_idx)
            color  = CL_YELLOW if is_sel else CL_GRAY_LIGHT
            lbl    = font_med.render(label, True, color)
            y_pos  = 110 + i * 40
            if is_sel:
                pg.draw.rect(screen, CL_GRAY_MID,
                             pg.Rect(30, y_pos - 4, WINDOW_W - 60, 34), border_radius=6)
            screen.blit(lbl, (50, y_pos))

        pg.display.flip(); clock.tick(60)

        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    return
                if event.key == pg.K_DOWN:
                    selected_idx = min(selected_idx + 1, len(pgn_files) - 1)
                    if selected_idx >= scroll_off + max_visible:
                        scroll_off += 1
                if event.key == pg.K_UP:
                    selected_idx = max(selected_idx - 1, 0)
                    if selected_idx < scroll_off:
                        scroll_off -= 1
                if event.key in (pg.K_RETURN, pg.K_KP_ENTER):
                    _replay_pgn_file(screen, clock, pgn_files[selected_idx])
                    pgn_files = load_pgn_games(PGN_SAVE_DIR)
                    if not pgn_files:
                        return


def _replay_pgn_file(screen, clock, filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        game = chess.pgn.read_game(f)
    if game is None:
        _show_message(screen, clock, "Could not parse PGN file")
        return

    font_sm  = pg.font.SysFont("Arial", 13)
    font_med = pg.font.SysFont("Arial", 16, bold=True)

    white_name = game.headers.get("White", "White")
    black_name = game.headers.get("Black", "Black")
    result     = game.headers.get("Result", "*")
    moves      = list(game.mainline_moves())
    PROMO      = {chess.QUEEN:"Q", chess.ROOK:"R", chess.BISHOP:"B", chess.KNIGHT:"N"}

    board     = ChessBoard()
    sprites   = Sprites(board)
    ply_idx   = 0
    last_move = None

    def apply_ply(idx: int):
        nonlocal board, sprites, last_move
        board = ChessBoard(); turn = WHITE; last_move = None
        for i in range(idx):
            mv    = moves[i]
            from_sq = chess.square_name(mv.from_square)
            to_sq   = chess.square_name(mv.to_square)
            promo   = PROMO.get(mv.promotion)
            piece   = next((p for p in board.players[turn].pieces
                            if p.location == from_sq), None)
            if piece:
                board._move_piece(piece, to_sq, promotion=promo)
                board._update_tiles()
                if board.actions:
                    a = board.actions[-1]
                    last_move = (a.from_tile, a.to_tile)
            turn = BLACK if turn == WHITE else WHITE
        sprites = Sprites(board)

    apply_ply(ply_idx)

    while True:
        screen.fill(CL_GRAY_DARK)
        draw_board(screen)
        draw_overlays(screen, board, None, [], last_move)
        sprites.draw(screen)

        y = INFO_Y
        header = font_med.render(
            f"{white_name} vs {black_name}  |  Result: {result}  |  Ply {ply_idx}/{len(moves)}",
            True, CL_YELLOW)
        screen.blit(header, (BOARD_X, y)); y += 22
        nav = font_sm.render(
            "← prev   → next   Home=start   End=finish   ESC=back",
            True, CL_GRAY_LIGHT)
        screen.blit(nav, (BOARD_X, y))

        pg.display.flip(); clock.tick(60)

        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    return
                if event.key in (pg.K_RIGHT, pg.K_n):
                    if ply_idx < len(moves):
                        ply_idx += 1; apply_ply(ply_idx)
                if event.key in (pg.K_LEFT, pg.K_p):
                    if ply_idx > 0:
                        ply_idx -= 1; apply_ply(ply_idx)
                if event.key == pg.K_HOME:
                    ply_idx = 0; apply_ply(0)
                if event.key == pg.K_END:
                    ply_idx = len(moves); apply_ply(ply_idx)


def _show_message(screen, clock, msg: str):
    font    = pg.font.SysFont("Arial", 22, bold=True)
    font_sm = pg.font.SysFont("Arial", 16)
    while True:
        screen.fill(CL_GRAY_DARK)
        lbl  = font.render(msg, True, CL_YELLOW)
        hint = font_sm.render("Press ESC to go back", True, CL_GRAY_LIGHT)
        screen.blit(lbl,  lbl.get_rect(center=(WINDOW_W//2, WINDOW_H//2 - 20)))
        screen.blit(hint, hint.get_rect(center=(WINDOW_W//2, WINDOW_H//2 + 20)))
        pg.display.flip(); clock.tick(60)
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                return


# ── NumberField widget ────────────────────────────────────────────────────────

class NumberField:
    """Clickable integer field for config screens."""
    def __init__(self, label: str, default: int, min_val: int, max_val: int, step: int = 1):
        self.label   = label
        self.value   = default
        self.min_val = min_val
        self.max_val = max_val
        self.step    = step
        self.focused = False
        self._text   = str(default)

    def handle_key(self, event):
        if not self.focused:
            return
        if event.key == pg.K_UP:
            self.value = min(self.value + self.step, self.max_val)
            self._text = str(self.value)
        elif event.key == pg.K_DOWN:
            self.value = max(self.value - self.step, self.min_val)
            self._text = str(self.value)
        elif event.key == pg.K_BACKSPACE:
            self._text = self._text[:-1]
            self._commit()
        elif event.unicode.isdigit():
            self._text += event.unicode
            self._commit()

    def _commit(self):
        try:
            v = int(self._text)
            self.value = max(self.min_val, min(self.max_val, v))
        except Exception:
            pass

    def draw(self, surface: pg.Surface, font, rect: pg.Rect):
        color = CL_YELLOW if self.focused else CL_GRAY_LIGHT
        pg.draw.rect(surface, (60, 60, 60), rect, border_radius=6)
        pg.draw.rect(surface, color, rect, 2, border_radius=6)
        display = f"{self.label}: {self._text if self.focused else self.value}"
        lbl = font.render(display, True, color)
        surface.blit(lbl, lbl.get_rect(midleft=(rect.x + 10, rect.centery)))

    def click(self, pos, rect: pg.Rect) -> bool:
        if rect.collidepoint(pos):
            self.focused = True
            return True
        self.focused = False
        return False


# ── Generic config screen ─────────────────────────────────────────────────────

def run_config_screen(screen, clock, title_text: str,
                      fields: list[NumberField], start_label: str = "Start") -> bool:
    font_big = pg.font.SysFont("Arial", 32, bold=True)
    font_med = pg.font.SysFont("Arial", 19)
    font_sm  = pg.font.SysFont("Arial", 14)

    field_h = 46; field_w = 420
    field_x = (WINDOW_W - field_w) // 2
    start_y = 190

    rects = [pg.Rect(field_x, start_y + i * (field_h + 12), field_w, field_h)
             for i in range(len(fields))]

    btn_w   = 200; btn_h = 50
    btn_rect = pg.Rect((WINDOW_W - btn_w)//2,
                       start_y + len(fields) * (field_h + 12) + 20,
                       btn_w, btn_h)

    while True:
        screen.fill(CL_GRAY_DARK)
        ttl = font_big.render(title_text, True, CL_YELLOW)
        screen.blit(ttl, ttl.get_rect(center=(WINDOW_W//2, 110)))
        sub = font_sm.render("Click to focus  |  ↑/↓ or type to adjust  |  ESC = back",
                             True, CL_GRAY_MID)
        screen.blit(sub, sub.get_rect(center=(WINDOW_W//2, 152)))

        for field, rect in zip(fields, rects):
            field.draw(screen, font_med, rect)

        mx, my = pg.mouse.get_pos()
        hover  = btn_rect.collidepoint(mx, my)
        pg.draw.rect(screen, CL_YELLOW if hover else CL_BTN_NORM, btn_rect, border_radius=10)
        lbl = font_big.render(start_label, True, CL_BLACK if hover else CL_WHITE)
        screen.blit(lbl, lbl.get_rect(center=btn_rect.center))

        pg.display.flip(); clock.tick(60)

        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    return False
                for field in fields:
                    field.handle_key(event)
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                for field, rect in zip(fields, rects):
                    field.click(event.pos, rect)
                if btn_rect.collidepoint(event.pos):
                    return True


# ── Live-watch HUD ────────────────────────────────────────────────────────────

def draw_live_hud(surface, board, turn, status_lines, right_lines, game_over_msg=None):
    font    = pg.font.SysFont("Arial", 15, bold=True)
    font_sm = pg.font.SysFont("Arial", 13)
    font_go = pg.font.SysFont("Arial", 28, bold=True)

    y          = INFO_Y
    color_name = "White" if turn == WHITE else "Black"
    surface.blit(font.render(f"Turn: {color_name}", True,
                             CL_WHITE if turn == WHITE else CL_YELLOW), (BOARD_X, y))
    y += 20

    pts = font_sm.render(
        f"W: {board.players[WHITE].points} pts  B: {board.players[BLACK].points} pts"
        f"  | W taken: {board.players[WHITE].taken_pieces_str}"
        f"  B taken: {board.players[BLACK].taken_pieces_str}",
        True, CL_GRAY_LIGHT)
    surface.blit(pts, (BOARD_X, y)); y += 17

    for line, col in status_lines:
        surface.blit(font_sm.render(line, True, col), (BOARD_X, y)); y += 17

    # Right-side stats column
    sx = BOARD_X + BOARD_PX - 10
    sy = INFO_Y
    for line, col in right_lines:
        lbl = font_sm.render(line, True, col)
        surface.blit(lbl, (sx - lbl.get_width(), sy)); sy += 17

    if game_over_msg:
        overlay = pg.Surface((WINDOW_W, WINDOW_H), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))
        go = font_go.render(game_over_msg, True, CL_YELLOW)
        surface.blit(go, go.get_rect(center=(WINDOW_W//2, WINDOW_H//2 - 20)))
        hint = font_sm.render("ESC = menu  |  Space / N = next game", True, CL_GRAY_LIGHT)
        surface.blit(hint, hint.get_rect(center=(WINDOW_W//2, WINDOW_H//2 + 20)))


# ── Bot vs Bot ────────────────────────────────────────────────────────────────

def run_bot_vs_bot_config(screen, clock):
    fields = [
        NumberField("Games",          1,   1, 100),
        NumberField("Depth",          2,   1,   5),
        NumberField("Debug",          0,   0,   2),
        NumberField("Move delay (ms)", LIVE_MOVE_DELAY_MS, 0, 3000, step=100),
    ]
    if not run_config_screen(screen, clock, "Bot vs Bot", fields):
        return
    run_bot_vs_bot(screen, clock,
                   num_games=fields[0].value,
                   depth=fields[1].value,
                   debug=fields[2].value,
                   move_delay_ms=fields[3].value)


def run_bot_vs_bot(screen, clock, num_games=1, depth=2, debug=0, move_delay_ms=400):
    model_name = os.path.basename(MODEL_PATH).replace(".pt", "")
    os.makedirs(BOT_VS_BOT_DIR, exist_ok=True)

    white_wins = 0; black_wins = 0; draws = 0
    games_played = 0
    game_over_msg = None; pgn_saved = False; paused = False

    def new_board():
        b = ChessBoard()
        return b, Sprites(b), WHITE, None

    board, sprites, turn, last_move = new_board()

    bot_slot = [None]; thinking = [False]
    move_delay_ticks = [0]

    def start_bot():
        thinking[0] = True; bot_slot[0] = None
        def _w():
            mv = best_move(board, turn, depth=depth, debug=debug, time_budget=90.0)
            bot_slot[0] = mv if mv else "__NONE__"
        threading.Thread(target=_w, daemon=True).start()

    start_bot()

    while True:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    return
                if event.key == pg.K_p:
                    paused = not paused
                if game_over_msg and event.key in (pg.K_SPACE, pg.K_n):
                    if games_played < num_games:
                        board, sprites, turn, last_move = new_board()
                        bot_slot[0] = None; game_over_msg = None
                        pgn_saved = False; thinking[0] = False
                        move_delay_ticks[0] = 0
                        start_bot()

        if paused:
            screen.fill(CL_GRAY_DARK)
            draw_board(screen)
            draw_overlays(screen, board, None, [], last_move)
            sprites.draw(screen)
            right = _bvb_right_lines(games_played, num_games, white_wins, black_wins, draws, depth)
            draw_live_hud(screen, board, turn, [("PAUSED — P to resume", CL_BLUE_LT)],
                          right, game_over_msg)
            pg.display.flip(); clock.tick(60)
            continue

        # Poll bot
        if thinking[0] and bot_slot[0] is not None and not game_over_msg:
            thinking[0] = False
            raw = bot_slot[0]; moved = False
            if raw != "__NONE__":
                from_sq, to_sq = raw
                bp = next((p for p in board.players[turn].pieces
                           if p.location == from_sq), None)
                if bp:
                    try:
                        board._move_piece(bp, to_sq)
                        board._update_tiles()
                        if board.actions:
                            a = board.actions[-1]
                            last_move = (a.from_tile, a.to_tile)
                        sprites.after_move(board)
                        moved = True
                    except Exception as e:
                        print(f"BvB error: {e}")

            next_t = BLACK if turn == WHITE else WHITE
            result_str = None

            if moved:
                if board.players[next_t].mated:
                    winner = "White" if next_t == BLACK else "Black"
                    game_over_msg = f"{winner} wins by checkmate!"
                    result_str = "1-0" if next_t == BLACK else "0-1"
                    if next_t == BLACK: white_wins += 1
                    else:               black_wins += 1
                    games_played += 1
                elif not board.players[next_t].possible_moves:
                    game_over_msg = "Stalemate — draw!"
                    result_str = "1/2-1/2"; draws += 1; games_played += 1
                elif len(board.actions) >= 300:
                    game_over_msg = "Move limit — draw!"
                    result_str = "1/2-1/2"; draws += 1; games_played += 1
                else:
                    turn = next_t
                    move_delay_ticks[0] = max(1, move_delay_ms // 16)

                if result_str and not pgn_saved:
                    pgn_saved = True
                    save_pgn(board, "BOT_VS_BOT", None, result=result_str,
                             save_dir=BOT_VS_BOT_DIR,
                             white_name=model_name, black_name=model_name)
            else:
                game_over_msg = "No move returned — draw!"
                draws += 1; games_played += 1

        # Delay countdown before next bot call
        if move_delay_ticks[0] > 0 and not thinking[0] and not game_over_msg:
            move_delay_ticks[0] -= 1
            if move_delay_ticks[0] == 0:
                start_bot()

        if games_played >= num_games and not game_over_msg:
            game_over_msg = f"Series done! W:{white_wins} B:{black_wins} D:{draws}"

        # Render
        screen.fill(CL_GRAY_DARK)
        draw_board(screen)
        draw_overlays(screen, board, None, [], last_move)
        sprites.draw(screen)

        status = []
        if thinking[0]:
            status.append(("Bot thinking…", CL_BLUE_LT))
        elif move_delay_ticks[0] > 0:
            status.append(("Waiting before next move…", CL_GRAY_LIGHT))
        if board.actions:
            status.append((f"Last: {board.actions[-1]}", CL_GRAY_LIGHT))
        status.append(("P = pause  |  ESC = menu", CL_GRAY_MID))

        right = _bvb_right_lines(games_played, num_games, white_wins, black_wins, draws, depth)
        draw_live_hud(screen, board, turn, status, right, game_over_msg)
        pg.display.flip(); clock.tick(60)


def _bvb_right_lines(played, total, ww, bw, dr, depth):
    return [
        (f"Game {min(played+1, total)}/{total}", CL_YELLOW),
        (f"White wins: {ww}", CL_WHITE),
        (f"Black wins: {bw}", CL_YELLOW),
        (f"Draws:      {dr}", CL_GRAY_LIGHT),
        (f"depth={depth}", CL_GRAY_MID),
    ]


# ── Challenge Stockfish ───────────────────────────────────────────────────────

def _find_stockfish() -> str | None:
    for p in [
        os.environ.get("STOCKFISH_PATH"),
        shutil.which("stockfish"),
        "/opt/homebrew/bin/stockfish",
        "/usr/local/bin/stockfish",
        "/usr/bin/stockfish",
    ]:
        if p and os.path.exists(p):
            return p
    return None


def run_challenge_sf_config(screen, clock):
    sf = _find_stockfish()
    if sf is None:
        _show_message(screen, clock,
                      "Stockfish not found. Set STOCKFISH_PATH env var.")
        return
    if chess_engine_mod is None:
        _show_message(screen, clock, "chess.engine not available (update python-chess).")
        return

    fields = [
        NumberField("Games per skill level",  2,  1, 20),
        NumberField("Depth",                  2,  1,  5),
        NumberField("Debug",                  0,  0,  2),
        NumberField("Start skill",            0,  0, 20),
        NumberField("Skill step",             1,  1, 20),
        NumberField("Max skill",              3,  0, 20),
        NumberField("SF move time (ms)",    100, 50, 5000, step=50),
        NumberField("Move delay (ms)", LIVE_MOVE_DELAY_MS, 0, 3000, step=100),
    ]
    if not run_config_screen(screen, clock, "Challenge Stockfish", fields):
        return
    run_challenge_sf(screen, clock,
                     sf_path=sf,
                     games_per_level=fields[0].value,
                     depth=fields[1].value,
                     debug=fields[2].value,
                     start_skill=fields[3].value,
                     skill_step=fields[4].value,
                     max_skill=fields[5].value,
                     sf_move_ms=fields[6].value,
                     move_delay_ms=fields[7].value)


def run_challenge_sf(screen, clock, sf_path, games_per_level=2, depth=2, debug=0,
                     start_skill=0, skill_step=1, max_skill=3,
                     sf_move_ms=100, move_delay_ms=400):
    model_name = os.path.basename(MODEL_PATH).replace(".pt", "")
    os.makedirs(CHALLENGE_SF_DIR, exist_ok=True)

    PROMO_MAP = {chess.QUEEN:"Q", chess.ROOK:"R", chess.BISHOP:"B", chess.KNIGHT:"N"}

    skill_levels = list(range(start_skill, max_skill + 1, max(skill_step, 1)))
    total_games  = games_per_level * len(skill_levels)

    bot_wins = 0; sf_wins = 0; draws = 0
    games_played = 0; skill_idx = 0; game_in_level = 0
    current_skill = skill_levels[0] if skill_levels else 0

    def bot_color_for(idx): return WHITE if idx % 2 == 0 else BLACK

    bot_color = bot_color_for(game_in_level)

    def new_board():
        b = ChessBoard()
        return b, Sprites(b), WHITE, None, chess.Board()

    board, sprites, turn, last_move, py_board = new_board()

    game_over_msg = None; pgn_saved = False; paused = False

    move_slot = [None]; thinking = [False]
    move_delay_ticks = [0]

    try:
        sf_engine = chess_engine_mod.SimpleEngine.popen_uci(sf_path)
        sf_engine.configure({"Skill Level": current_skill})
    except Exception as e:
        _show_message(screen, clock, f"Stockfish failed to start: {e}")
        return

    def start_worker():
        thinking[0] = True; move_slot[0] = None
        bc = bot_color
        if turn == bc:
            def _bot():
                mv = best_move(board, turn, depth=depth, debug=debug, time_budget=90.0)
                move_slot[0] = mv if mv else "__NONE__"
            threading.Thread(target=_bot, daemon=True).start()
        else:
            def _sf():
                try:
                    res = sf_engine.play(py_board,
                                         chess_engine_mod.Limit(time=sf_move_ms/1000.0))
                    if res.move:
                        promo   = PROMO_MAP.get(res.move.promotion)
                        from_sq = chess.square_name(res.move.from_square)
                        to_sq   = chess.square_name(res.move.to_square)
                        move_slot[0] = (from_sq, to_sq, promo)
                    else:
                        move_slot[0] = "__NONE__"
                except Exception as ex:
                    print(f"SF error: {ex}"); move_slot[0] = "__NONE__"
            threading.Thread(target=_sf, daemon=True).start()

    def advance_game(result_str, winner_msg):
        nonlocal games_played, game_in_level, skill_idx, current_skill
        nonlocal bot_wins, sf_wins, draws, bot_color
        nonlocal board, sprites, turn, last_move, py_board
        nonlocal game_over_msg, pgn_saved

        if result_str and not pgn_saved:
            pgn_saved = True
            bc = bot_color
            sf_label = f"Stockfish_skill{current_skill}"
            wn = model_name if bc == WHITE else sf_label
            bn = sf_label if bc == WHITE else model_name
            save_pgn(board, "CHALLENGE_SF", None, result=result_str,
                     save_dir=CHALLENGE_SF_DIR, white_name=wn, black_name=bn)

        game_over_msg = winner_msg
        games_played += 1
        game_in_level += 1
        if game_in_level >= games_per_level:
            skill_idx += 1; game_in_level = 0
            if skill_idx < len(skill_levels):
                current_skill = skill_levels[skill_idx]
                try: sf_engine.configure({"Skill Level": current_skill})
                except Exception: pass

    start_worker()

    while True:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                try: sf_engine.quit()
                except Exception: pass
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    try: sf_engine.quit()
                    except Exception: pass
                    return
                if event.key == pg.K_p:
                    paused = not paused
                if game_over_msg and event.key in (pg.K_SPACE, pg.K_n):
                    if games_played < total_games and skill_idx < len(skill_levels):
                        bot_color = bot_color_for(game_in_level)
                        board, sprites, turn, last_move, py_board = new_board()
                        move_slot[0] = None; game_over_msg = None
                        pgn_saved = False; thinking[0] = False
                        move_delay_ticks[0] = 0
                        start_worker()

        if paused:
            screen.fill(CL_GRAY_DARK)
            draw_board(screen)
            draw_overlays(screen, board, None, [], last_move)
            sprites.draw(screen)
            right = _sf_right_lines(current_skill, skill_levels, skill_idx,
                                    games_per_level, game_in_level,
                                    bot_wins, sf_wins, draws, depth, games_played, total_games)
            draw_live_hud(screen, board, turn, [("PAUSED — P to resume", CL_BLUE_LT)],
                          right, game_over_msg)
            pg.display.flip(); clock.tick(60)
            continue

        # Poll worker
        if thinking[0] and move_slot[0] is not None and not game_over_msg:
            thinking[0] = False
            raw = move_slot[0]; moved = False

            if raw != "__NONE__":
                if turn == bot_color:
                    from_sq, to_sq = raw; promo = None
                else:
                    from_sq, to_sq = raw[0], raw[1]
                    promo = raw[2] if len(raw) > 2 else None

                bp = next((p for p in board.players[turn].pieces
                           if p.location == from_sq), None)
                if bp:
                    try:
                        board._move_piece(bp, to_sq, promotion=promo)
                        board._update_tiles()
                        if board.actions:
                            a = board.actions[-1]
                            last_move = (a.from_tile, a.to_tile)
                        sprites.after_move(board)
                        uci  = from_sq + to_sq + (promo.lower() if promo else "")
                        chmv = chess.Move.from_uci(uci)
                        if chmv in py_board.legal_moves:
                            py_board.push(chmv)
                        moved = True
                    except Exception as e:
                        print(f"SF game error: {e}")

            next_t = BLACK if turn == WHITE else WHITE

            if moved:
                if board.players[next_t].mated:
                    winner_is_bot = (next_t != bot_color)
                    if winner_is_bot:
                        bot_wins += 1
                        rs = "1-0" if bot_color == WHITE else "0-1"
                        advance_game(rs, f"Bot wins! (skill {current_skill})")
                    else:
                        sf_wins += 1
                        rs = "0-1" if bot_color == WHITE else "1-0"
                        advance_game(rs, f"Stockfish wins! (skill {current_skill})")
                elif not board.players[next_t].possible_moves:
                    draws += 1
                    advance_game("1/2-1/2", "Stalemate — draw!")
                elif len(board.actions) >= 300:
                    draws += 1
                    advance_game("1/2-1/2", "Move limit — draw!")
                else:
                    turn = next_t
                    move_delay_ticks[0] = max(1, move_delay_ms // 16)
            else:
                draws += 1
                advance_game(None, "No move — forfeit (draw)")

        if move_delay_ticks[0] > 0 and not thinking[0] and not game_over_msg:
            move_delay_ticks[0] -= 1
            if move_delay_ticks[0] == 0:
                start_worker()

        if games_played >= total_games and not game_over_msg:
            game_over_msg = (f"Series complete! Bot:{bot_wins} SF:{sf_wins} D:{draws}")

        # Render
        screen.fill(CL_GRAY_DARK)
        draw_board(screen)
        draw_overlays(screen, board, None, [], last_move)
        sprites.draw(screen)

        bc_name = "White" if bot_color == WHITE else "Black"
        status  = []
        if thinking[0]:
            mover = "Bot" if turn == bot_color else f"Stockfish (skill {current_skill})"
            status.append((f"{mover} thinking…", CL_BLUE_LT))
        elif move_delay_ticks[0] > 0:
            status.append(("Waiting before next move…", CL_GRAY_LIGHT))
        if board.actions:
            status.append((f"Last: {board.actions[-1]}", CL_GRAY_LIGHT))
        status.append((f"Bot plays {bc_name}  |  P=pause  ESC=menu", CL_GRAY_MID))

        right = _sf_right_lines(current_skill, skill_levels, skill_idx,
                                games_per_level, game_in_level,
                                bot_wins, sf_wins, draws, depth, games_played, total_games)
        draw_live_hud(screen, board, turn, status, right, game_over_msg)
        pg.display.flip(); clock.tick(60)


def _sf_right_lines(skill, skill_levels, skill_idx, gpl, game_in_level,
                    bw, sfw, dr, depth, played, total):
    return [
        (f"Skill {skill}  g {game_in_level+1}/{gpl}", CL_YELLOW),
        (f"Bot wins:  {bw}", CL_GREEN),
        (f"SF  wins:  {sfw}", CL_RED),
        (f"Draws:     {dr}", CL_GRAY_LIGHT),
        (f"Progress: {played}/{total}", CL_GRAY_LIGHT),
        (f"depth={depth}", CL_GRAY_MID),
    ]


# ── Human game (2P / vs Bot) ──────────────────────────────────────────────────

def run_game(screen, clock, mode: str, human_color):
    board   = ChessBoard()
    sprites = Sprites(board)
    turn    = WHITE

    selected_piece = None
    highlighted    = []
    last_move      = None
    dragging       = False
    drag_sprite    = None
    drag_piece     = None
    drag_origin    = None
    drag_offset    = (0, 0)

    bot_thinking = False
    bot_slot     = [None]
    status_msg   = ""
    game_over    = False
    pgn_saved    = False

    def commit(piece: Piece, to_tile: str) -> bool:
        nonlocal last_move, status_msg
        promotion = None
        if _is_promotion_move(piece, to_tile):
            screen.fill((40,40,40))
            draw_board(screen)
            draw_overlays(screen, board, selected_piece, highlighted, last_move)
            did = drag_sprite.piece_id if drag_sprite else None
            sprites.draw(screen, exclude=did)
            if drag_sprite:
                screen.blit(drag_sprite.image, drag_sprite.rect)
            draw_hud(screen, board, turn, mode, human_color, bot_thinking, status_msg, game_over)
            promotion = run_promotion_picker(screen, clock, piece.color)
        try:
            board._move_piece(piece, to_tile, promotion=promotion)
            board._update_tiles()
            if board.actions:
                a = board.actions[-1]
                last_move = (a.from_tile, a.to_tile)
            sprites.after_move(board)
            status_msg = ""
            return True
        except ValueError as e:
            status_msg = str(e)
            if drag_sprite:
                drag_sprite.snap_home()
            return False

    def is_over(next_turn: str) -> bool:
        return (board.players[next_turn].mated or
                not board.players[next_turn].possible_moves)

    def start_bot():
        nonlocal bot_thinking
        bot_thinking = True; bot_slot[0] = None
        def _w():
            mv = best_move(board, turn, depth=BOT_DEPTH, time_budget=BOT_TIME_BUDGET)
            bot_slot[0] = mv if mv is not None else "__NONE__"
        threading.Thread(target=_w, daemon=True).start()

    def determine_result() -> str:
        if board.players[WHITE].mated: return "0-1"
        if board.players[BLACK].mated: return "1-0"
        return "1/2-1/2"

    if mode == "BOT" and human_color == BLACK:
        start_bot()

    while True:
        if bot_thinking and bot_slot[0] is not None:
            bot_thinking = False
            raw = bot_slot[0]
            if raw != "__NONE__" and not game_over:
                from_sq, to_sq = raw
                bp = next((p for p in board.players[turn].pieces
                           if p.location == from_sq), None)
                if bp and commit(bp, to_sq):
                    next_t = BLACK if turn == WHITE else WHITE
                    if is_over(next_t):
                        game_over = True
                    else:
                        turn = next_t

        if game_over and not pgn_saved:
            pgn_saved = True
            save_pgn(board, mode, human_color, result=determine_result())

        for event in pg.event.get():
            if event.type == pg.QUIT:
                if not pgn_saved:
                    save_pgn(board, mode, human_color, result="*")
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                if not pgn_saved:
                    save_pgn(board, mode, human_color, result="*")
                return
            if game_over:
                continue
            if mode == "BOT" and (turn != human_color or bot_thinking):
                continue

            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                mx, my  = event.pos
                clicked = px_to_tile(mx, my)

                if selected_piece and clicked and clicked in highlighted:
                    if commit(selected_piece, clicked):
                        next_t = BLACK if turn == WHITE else WHITE
                        if is_over(next_t):
                            game_over = True
                        else:
                            turn = next_t
                            if mode == "BOT" and turn != human_color:
                                start_bot()
                    selected_piece = None; highlighted = []
                    continue

                if clicked:
                    tile_obj = board._get_tile(clicked)
                    if tile_obj and tile_obj.piece and tile_obj.piece.color == turn:
                        piece          = tile_obj.piece
                        selected_piece = piece
                        highlighted    = list(piece.moves)
                        spr = sprites.get(piece.id)
                        if spr:
                            dragging    = True
                            drag_sprite = spr
                            drag_piece  = piece
                            drag_origin = clicked
                            drag_offset = (mx - spr.rect.centerx, my - spr.rect.centery)
                        continue

                selected_piece = None; highlighted = []

            if event.type == pg.MOUSEMOTION and dragging and drag_sprite:
                mx, my = event.pos
                drag_sprite.rect.center = (mx - drag_offset[0], my - drag_offset[1])

            if event.type == pg.MOUSEBUTTONUP and event.button == 1 and dragging:
                dragging  = False
                mx, my    = event.pos
                drop_tile = px_to_tile(mx, my)
                committed = False

                if drop_tile and drop_tile in highlighted and drag_piece:
                    if commit(drag_piece, drop_tile):
                        committed = True
                        next_t = BLACK if turn == WHITE else WHITE
                        if is_over(next_t):
                            game_over = True
                        else:
                            turn = next_t
                            if mode == "BOT" and turn != human_color:
                                start_bot()
                        selected_piece = None; highlighted = []

                if not committed and drag_sprite:
                    drag_sprite.snap_home()
                    if selected_piece:
                        highlighted = list(selected_piece.moves)

                drag_sprite = None; drag_piece = None; drag_origin = None

        screen.fill(CL_GRAY_DARK)
        draw_board(screen)
        draw_overlays(screen, board, selected_piece, highlighted, last_move)

        drid = drag_sprite.piece_id if drag_sprite else None
        sprites.draw(screen, exclude=drid)
        if drag_sprite:
            screen.blit(drag_sprite.image, drag_sprite.rect)

        draw_hud(screen, board, turn, mode, human_color, bot_thinking, status_msg, game_over)
        pg.display.flip(); clock.tick(60)


# ── Main menu ─────────────────────────────────────────────────────────────────

def run_menu(screen, clock):
    font_big = pg.font.SysFont("Arial", 40, bold=True)
    font_med = pg.font.SysFont("Arial", 22)
    font_sm  = pg.font.SysFont("Arial", 14)

    mode_options = [
        ("2-Player  (Pass & Play)",  "2P"),
        ("vs Bot",                   "BOT"),
        ("Bot vs Bot  (Watch Live)", "BOT_VS_BOT"),
        ("Challenge Stockfish",      "CHALLENGE_SF"),
        ("Review Saved Games",       "REVIEW"),
    ]

    btn_w   = 360; btn_h = 50
    btn_x   = (WINDOW_W - btn_w) // 2
    spacing = 66
    start_y = 210
    mode_btns = [pg.Rect(btn_x, start_y + i * spacing, btn_w, btn_h)
                 for i in range(len(mode_options))]

    chosen_mode = None
    while chosen_mode is None:
        screen.fill(CL_GRAY_DARK)
        title = font_big.render("Chess", True, CL_YELLOW)
        screen.blit(title, title.get_rect(center=(WINDOW_W//2, 130)))
        sub = font_med.render("Select a game mode", True, CL_GRAY_LIGHT)
        screen.blit(sub, sub.get_rect(center=(WINDOW_W//2, 180)))

        mx, my = pg.mouse.get_pos()
        for i, (label, _) in enumerate(mode_options):
            hover = mode_btns[i].collidepoint(mx, my)
            pg.draw.rect(screen, CL_YELLOW if hover else CL_BTN_NORM,
                         mode_btns[i], border_radius=10)
            lbl = font_med.render(label, True, CL_BLACK if hover else CL_WHITE)
            screen.blit(lbl, lbl.get_rect(center=mode_btns[i].center))

        mdl = font_sm.render(f"Model: {os.path.basename(MODEL_PATH)}", True, CL_GRAY_MID)
        screen.blit(mdl, mdl.get_rect(center=(WINDOW_W//2, WINDOW_H - 18)))

        pg.display.flip(); clock.tick(60)

        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                for i, (_, mode) in enumerate(mode_options):
                    if mode_btns[i].collidepoint(event.pos):
                        chosen_mode = mode

    if chosen_mode == "REVIEW":
        run_pgn_review(screen, clock)
        return run_menu(screen, clock)

    if chosen_mode == "BOT_VS_BOT":
        run_bot_vs_bot_config(screen, clock)
        return run_menu(screen, clock)

    if chosen_mode == "CHALLENGE_SF":
        run_challenge_sf_config(screen, clock)
        return run_menu(screen, clock)

    if chosen_mode == "2P":
        return "2P", None

    # BOT — pick color
    color_options = [
        ("Play as White", WHITE),
        ("Play as Black", BLACK),
        ("Random Color",  "RANDOM"),
    ]
    color_btns = [pg.Rect(btn_x, 260 + i * 80, btn_w, btn_h)
                  for i in range(len(color_options))]

    chosen_color = None
    while chosen_color is None:
        screen.fill(CL_GRAY_DARK)
        title = font_big.render("Chess", True, CL_YELLOW)
        screen.blit(title, title.get_rect(center=(WINDOW_W//2, 140)))
        sub = font_med.render("Choose your color", True, CL_GRAY_LIGHT)
        screen.blit(sub, sub.get_rect(center=(WINDOW_W//2, 210)))
        back = font_sm.render("ESC = back to mode select", True, CL_GRAY_MID)
        screen.blit(back, back.get_rect(center=(WINDOW_W//2, WINDOW_H - 30)))

        mx, my = pg.mouse.get_pos()
        for i, (label, _) in enumerate(color_options):
            hover = color_btns[i].collidepoint(mx, my)
            pg.draw.rect(screen, CL_YELLOW if hover else CL_BTN_NORM,
                         color_btns[i], border_radius=8)
            lbl = font_med.render(label, True, CL_BLACK if hover else CL_WHITE)
            screen.blit(lbl, lbl.get_rect(center=color_btns[i].center))

        pg.display.flip(); clock.tick(60)

        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                return run_menu(screen, clock)
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                for i, (_, col) in enumerate(color_options):
                    if color_btns[i].collidepoint(event.pos):
                        chosen_color = random.choice([WHITE, BLACK]) if col == "RANDOM" else col

    return "BOT", chosen_color


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    pg.init()
    screen = pg.display.set_mode((WINDOW_W, WINDOW_H))
    pg.display.set_caption("Chess")
    clock = pg.time.Clock()
    while True:
        result = run_menu(screen, clock)
        if result is not None:
            mode, human_color = result
            run_game(screen, clock, mode, human_color)


if __name__ == "__main__":
    main()