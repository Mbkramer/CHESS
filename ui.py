"""
Pygame driver for the chess game and bot.

Piece image naming convention:
  assets/1x/{color}{name}.png   e.g.  WP.png  BP.png  WR.png  WQ.png  BK.png
  Color prefix is 'W' or 'B', name is the single-letter piece code.

Modes:
  2P   pass-and-play, both sides human
  BOT  human vs bot; human_color chosen at launch

Features:
  - Two-step menu: pick mode first, then color (for BOT mode)
  - Correct per-color piece image loading (White vs Black distinction)
  - PGN game saving in the same format as chess_engine.py / bot.py
  - PGN review mode: replay any saved game move by move
  - Smaller window sized for laptop screens
"""

import os
import sys
import threading
import datetime
import pygame as pg

from chess_board import ChessBoard, WHITE, BLACK
from pieces import Piece
from bot import best_move, MODEL_PATH

try:
    import chess
    import chess.pgn
except Exception:
    chess = None

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
CL_BTN_ACTIVE = (80,  160,  80)
CL_BTN_NORM   = (100, 100, 100)

# ── Layout (laptop-friendly) ──────────────────────────────────────────────────
SQ            = 72        # square size; 8 × 72 = 576 px board
BOARD_X       = 60
BOARD_Y       = 60
BOARD_PX      = 8 * SQ   # 576
WINDOW_W      = BOARD_X + BOARD_PX + 60   # 696
WINDOW_H      = BOARD_Y + BOARD_PX + 110  # 746
INFO_Y        = BOARD_Y + BOARD_PX + 25

RANK = ['8','7','6','5','4','3','2','1']
FILE = ['a','b','c','d','e','f','g','h']

BOT_DEPTH       = 3
BOT_TIME_BUDGET = 90.0

PGN_SAVE_DIR = "data/played_games/UI"

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
    """One sprite per live chess piece. Cache keyed by color+name so
    White and Black pieces each get their own distinct image."""

    _cache: dict[str, pg.Surface] = {}

    def __init__(self, piece: Piece):
        super().__init__()
        self.piece_id    = piece.id
        self.piece_color = piece.color
        self.image = self._load(piece.color, piece.name)
        self.rect  = self.image.get_rect()
        self.rect.center = tile_to_px(piece.location)
        self.home  = self.rect.center

    @classmethod
    def _load(cls, color: str, name: str) -> pg.Surface:
        # BUG FIX #2: cache key must include color so W vs B pieces are distinct
        key = f"{color}{name}"
        if key in cls._cache:
            return cls._cache[key]
        sz = SQ - 8
        img = None
        # Try several naming conventions that might exist in the assets folder
        candidates = [
            f"assets/1x/{color}{name}.png",
            f"assets/piece_images/{color}{name}.png",
            f"assets/{color}{name}.png",
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    img = pg.image.load(path).convert_alpha()
                    img = pg.transform.smoothscale(img, (sz, sz))
                    break
                except Exception:
                    img = None

        if img is None:
            # Fallback: colored circle with letter so W/B are visually distinct
            fill  = (240, 240, 240) if color == WHITE else (60, 60, 60)
            txt_c = (30,  30,  30)  if color == WHITE else (220, 220, 220)
            img = pg.Surface((sz, sz), pg.SRCALPHA)
            pg.draw.circle(img, fill,   (sz//2, sz//2), sz//2)
            pg.draw.circle(img, (0,0,0),(sz//2, sz//2), sz//2, 2)
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
                if piece.id not in self.sprites:
                    self.sprites[piece.id] = PieceSprite(piece)
                else:
                    self.sprites[piece.id].snap_to(piece.location)
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
        tmp = pg.Surface((SQ, SQ), pg.SRCALPHA)
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


# ── PGN export (matches chess_engine.py / bot.py format) ─────────────────────

def save_pgn(board: ChessBoard, mode: str, human_color, result: str = "*"):
    """Save completed game as PGN to data/played_games/UI/"""
    if chess is None:
        print("python-chess not available — PGN not saved")
        return None

    os.makedirs(PGN_SAVE_DIR, exist_ok=True)
    model_name = os.path.basename(MODEL_PATH).replace(".pt", "")

    if mode == "2P":
        white_name = "Player One"
        black_name = "Player Two"
        event_tag  = "2P"
    else:
        if human_color == WHITE:
            white_name = "Human"
            black_name = model_name
        else:
            white_name = model_name
            black_name = "Human"
        event_tag = "BOT"

    ref = chess.Board()
    game = chess.pgn.Game()
    game.headers["Event"]  = event_tag
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
    filename = f"{model_name}_{ts}.pgn" if mode == "BOT" else f"{ts}.pgn"
    filepath = os.path.join(PGN_SAVE_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        exporter = chess.pgn.FileExporter(f)
        game.accept(exporter)

    print(f"Game saved to: {filepath}")
    return filepath


# ── PGN Review mode ───────────────────────────────────────────────────────────

def load_pgn_games(directory: str) -> list[str]:
    """Return list of .pgn filepaths in directory, most recent first."""
    if not os.path.isdir(directory):
        return []
    files = [
        os.path.join(directory, f)
        for f in sorted(os.listdir(directory), reverse=True)
        if f.endswith(".pgn")
    ]
    return files


def run_pgn_review(screen, clock):
    """Browse saved PGN files and replay them move by move."""
    if chess is None:
        _show_message(screen, clock, "python-chess not installed — cannot review PGNs")
        return

    font_big = pg.font.SysFont("Arial", 28, bold=True)
    font_med = pg.font.SysFont("Arial", 18)
    font_sm  = pg.font.SysFont("Arial", 14)

    pgn_files = load_pgn_games(PGN_SAVE_DIR)
    if not pgn_files:
        _show_message(screen, clock, f"No saved games found in {PGN_SAVE_DIR}/")
        return

    # ── File picker ──────────────────────────────────────────────────────────
    selected_idx = 0
    scroll_off   = 0
    max_visible  = 12

    while True:
        screen.fill(CL_GRAY_DARK)
        title = font_big.render("Review Saved Games", True, CL_YELLOW)
        screen.blit(title, title.get_rect(center=(WINDOW_W//2, 40)))
        hint = font_sm.render("↑/↓ to select  |  Enter to open  |  ESC to cancel", True, CL_GRAY_LIGHT)
        screen.blit(hint, hint.get_rect(center=(WINDOW_W//2, 75)))

        visible = pgn_files[scroll_off : scroll_off + max_visible]
        for i, path in enumerate(visible):
            idx     = scroll_off + i
            label   = os.path.basename(path)
            is_sel  = (idx == selected_idx)
            color   = CL_YELLOW if is_sel else CL_GRAY_LIGHT
            lbl     = font_med.render(label, True, color)
            y_pos   = 110 + i * 42
            if is_sel:
                pg.draw.rect(screen, CL_GRAY_MID,
                             pg.Rect(30, y_pos - 4, WINDOW_W - 60, 36), border_radius=6)
            screen.blit(lbl, (50, y_pos))

        pg.display.flip()
        clock.tick(60)

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
                    # Refresh file list in case new games were saved
                    pgn_files = load_pgn_games(PGN_SAVE_DIR)
                    if not pgn_files:
                        return


def _replay_pgn_file(screen, clock, filepath: str):
    """Load one PGN file and replay it interactively."""
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

    # Build move list from PGN
    moves = list(game.mainline_moves())
    PROMO = {chess.QUEEN:"Q", chess.ROOK:"R", chess.BISHOP:"B", chess.KNIGHT:"N"}

    # Replay state
    board        = ChessBoard()
    sprites      = Sprites(board)
    applied      = []    # list of chess.Move already pushed
    ply_idx      = 0
    last_move    = None

    def apply_ply(idx: int):
        """Rebuild board from scratch to ply idx (0 = start)."""
        nonlocal board, sprites, last_move
        board   = ChessBoard()
        turn    = WHITE
        last_move = None
        for i in range(idx):
            mv = moves[i]
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

        # HUD
        y = INFO_Y
        header = font_med.render(
            f"{white_name} vs {black_name}  |  Result: {result}  |  "
            f"Ply {ply_idx}/{len(moves)}",
            True, CL_YELLOW)
        screen.blit(header, (BOARD_X, y)); y += 22
        nav = font_sm.render(
            "← prev   → next   Home=start   End=finish   ESC=back",
            True, CL_GRAY_LIGHT)
        screen.blit(nav, (BOARD_X, y))

        pg.display.flip()
        clock.tick(60)

        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    return
                if event.key in (pg.K_RIGHT, pg.K_n):
                    if ply_idx < len(moves):
                        ply_idx += 1
                        apply_ply(ply_idx)
                if event.key in (pg.K_LEFT, pg.K_p):
                    if ply_idx > 0:
                        ply_idx -= 1
                        apply_ply(ply_idx)
                if event.key == pg.K_HOME:
                    ply_idx = 0
                    apply_ply(0)
                if event.key == pg.K_END:
                    ply_idx = len(moves)
                    apply_ply(ply_idx)


def _show_message(screen, clock, msg: str):
    font = pg.font.SysFont("Arial", 22, bold=True)
    font_sm = pg.font.SysFont("Arial", 16)
    while True:
        screen.fill(CL_GRAY_DARK)
        lbl = font.render(msg, True, CL_YELLOW)
        screen.blit(lbl, lbl.get_rect(center=(WINDOW_W//2, WINDOW_H//2 - 20)))
        hint = font_sm.render("Press ESC to go back", True, CL_GRAY_LIGHT)
        screen.blit(hint, hint.get_rect(center=(WINDOW_W//2, WINDOW_H//2 + 20)))
        pg.display.flip()
        clock.tick(60)
        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                return


# ── Menu screen (two-step: mode → color) ─────────────────────────────────────

def run_menu(screen, clock):
    """
    FIX #1: Two-step menu.
      Step 1 – choose mode: 2P | Bot | Review PGN
      Step 2 – (BOT only) choose color: White | Black | Random
    Returns (mode, human_color)  e.g.  ("BOT", "W")  or  ("2P", None)
    """
    font_big = pg.font.SysFont("Arial", 40, bold=True)
    font_med = pg.font.SysFont("Arial", 24)
    font_sm  = pg.font.SysFont("Arial", 16)

    # ── Step 1: pick mode ────────────────────────────────────────────────────
    import random
    mode_options = [
        ("2-Player  (Pass & Play)", "2P"),
        ("vs Bot",                  "BOT"),
        ("Review Saved Games",      "REVIEW"),
    ]
    btn_w, btn_h = 340, 50
    btn_x = (WINDOW_W - btn_w) // 2
    mode_btns = [pg.Rect(btn_x, 240 + i * 80, btn_w, btn_h)
                 for i in range(len(mode_options))]

    chosen_mode = None
    while chosen_mode is None:
        screen.fill(CL_GRAY_DARK)
        title = font_big.render("Chess", True, CL_YELLOW)
        screen.blit(title, title.get_rect(center=(WINDOW_W//2, 140)))
        sub = font_med.render("Select a game mode", True, CL_GRAY_LIGHT)
        screen.blit(sub, sub.get_rect(center=(WINDOW_W//2, 200)))

        mx, my = pg.mouse.get_pos()
        for i, (label, _) in enumerate(mode_options):
            hover = mode_btns[i].collidepoint(mx, my)
            pg.draw.rect(screen, CL_YELLOW if hover else CL_GRAY_MID,
                         mode_btns[i], border_radius=8)
            lbl = font_med.render(label, True, CL_BLACK if hover else CL_WHITE)
            screen.blit(lbl, lbl.get_rect(center=mode_btns[i].center))

        pg.display.flip()
        clock.tick(60)

        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                for i, (_, mode) in enumerate(mode_options):
                    if mode_btns[i].collidepoint(event.pos):
                        if mode == "REVIEW":
                            run_pgn_review(screen, clock)
                        else:
                            chosen_mode = mode

    # 2P needs no color step
    if chosen_mode == "2P":
        return "2P", None

    # ── Step 2: pick color (BOT only) ────────────────────────────────────────
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
        back_hint = font_sm.render("ESC = back to mode select", True, CL_GRAY_MID)
        screen.blit(back_hint, back_hint.get_rect(center=(WINDOW_W//2, WINDOW_H - 30)))

        mx, my = pg.mouse.get_pos()
        for i, (label, _) in enumerate(color_options):
            hover = color_btns[i].collidepoint(mx, my)
            pg.draw.rect(screen, CL_YELLOW if hover else CL_GRAY_MID,
                         color_btns[i], border_radius=8)
            lbl = font_med.render(label, True, CL_BLACK if hover else CL_WHITE)
            screen.blit(lbl, lbl.get_rect(center=color_btns[i].center))

        pg.display.flip()
        clock.tick(60)

        for event in pg.event.get():
            if event.type == pg.QUIT:
                pg.quit(); sys.exit()
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                return run_menu(screen, clock)  # restart from step 1
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                for i, (_, col) in enumerate(color_options):
                    if color_btns[i].collidepoint(event.pos):
                        if col == "RANDOM":
                            chosen_color = random.choice([WHITE, BLACK])
                        else:
                            chosen_color = col

    return "BOT", chosen_color


# ── Game loop ─────────────────────────────────────────────────────────────────

def run_game(screen, clock, mode: str, human_color):
    board   = ChessBoard()
    sprites = Sprites(board)
    turn    = WHITE

    selected_piece = None
    highlighted    = []
    last_move      = None

    dragging    = False
    drag_sprite = None
    drag_piece  = None
    drag_origin = None
    drag_offset = (0, 0)

    bot_thinking = False
    bot_slot     = [None]

    status_msg = ""
    game_over  = False
    pgn_saved  = False

    # ── helpers ──────────────────────────────────────────────────────────

    def commit(piece: Piece, to_tile: str) -> bool:
        nonlocal last_move, status_msg
        try:
            board._move_piece(piece, to_tile)
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
        bot_thinking = True
        bot_slot[0]  = None
        def _worker():
            move = best_move(board, turn,
                             depth=BOT_DEPTH,
                             time_budget=BOT_TIME_BUDGET)
            bot_slot[0] = move if move is not None else "__NONE__"
        threading.Thread(target=_worker, daemon=True).start()

    def determine_result() -> str:
        if board.players[WHITE].mated:
            return "0-1"
        if board.players[BLACK].mated:
            return "1-0"
        return "1/2-1/2"

    if mode == "BOT" and human_color == BLACK:
        start_bot()

    while True:

        # Poll bot thread
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

        # Auto-save PGN when game ends
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
                mx, my   = event.pos
                clicked  = px_to_tile(mx, my)

                if selected_piece and clicked and clicked in highlighted:
                    if commit(selected_piece, clicked):
                        next_t = BLACK if turn == WHITE else WHITE
                        if is_over(next_t):
                            game_over = True
                        else:
                            turn = next_t
                            if mode == "BOT" and turn != human_color:
                                start_bot()
                    selected_piece = None
                    highlighted    = []
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
                            drag_offset = (mx - spr.rect.centerx,
                                           my - spr.rect.centery)
                        continue

                selected_piece = None
                highlighted    = []

            if event.type == pg.MOUSEMOTION and dragging and drag_sprite:
                mx, my = event.pos
                drag_sprite.rect.center = (mx - drag_offset[0],
                                           my - drag_offset[1])

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
                        selected_piece = None
                        highlighted    = []

                if not committed and drag_sprite:
                    drag_sprite.snap_home()
                    if selected_piece:
                        highlighted = list(selected_piece.moves)

                drag_sprite = None
                drag_piece  = None
                drag_origin = None

        # ── Render ───────────────────────────────────────────────────────────
        screen.fill(CL_GRAY_DARK)
        draw_board(screen)
        draw_overlays(screen, board, selected_piece, highlighted, last_move)

        drag_id = drag_sprite.piece_id if drag_sprite else None
        sprites.draw(screen, exclude=drag_id)
        if drag_sprite:
            screen.blit(drag_sprite.image, drag_sprite.rect)

        draw_hud(screen, board, turn, mode, human_color,
                 bot_thinking, status_msg, game_over)

        pg.display.flip()
        clock.tick(60)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    pg.init()
    screen = pg.display.set_mode((WINDOW_W, WINDOW_H))
    pg.display.set_caption("Chess")
    clock = pg.time.Clock()
    while True:
        mode, human_color = run_menu(screen, clock)
        run_game(screen, clock, mode, human_color)


if __name__ == "__main__":
    main()