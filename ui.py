import pygame
import sys
from chess_board import ChessBoard

# ── Layout constants ──────────────────────────────────────────────────────────
TILE_SIZE      = 80          # pixels per square
BOARD_COLS     = 8
BOARD_ROWS     = 8
SIDEBAR_WIDTH  = 220         # right-side info panel
LABEL_MARGIN   = 30          # space for rank/file labels on the left and bottom
BOARD_PX       = TILE_SIZE * BOARD_COLS
WINDOW_W       = LABEL_MARGIN + BOARD_PX + SIDEBAR_WIDTH
WINDOW_H       = LABEL_MARGIN + BOARD_PX + LABEL_MARGIN
FPS            = 30

# ── Palette ───────────────────────────────────────────────────────────────────
COLOR_LIGHT       = (240, 217, 181)   # cream
COLOR_DARK        = (181, 136,  99)   # warm brown
COLOR_BACKGROUND  = ( 30,  30,  40)   # dark window bg
COLOR_SIDEBAR_BG  = ( 22,  22,  32)
COLOR_LABEL       = (200, 200, 200)
COLOR_WHITE_PIECE = (255, 255, 255)
COLOR_BLACK_PIECE = ( 20,  20,  20)
COLOR_PIECE_OUTLINE = (100, 100, 100)

# Piece symbol map  (piece.name → unicode chess glyph)
PIECE_GLYPHS = {
    "P": ("♙", "♟"),   # (white glyph, black glyph)
    "N": ("♘", "♞"),
    "B": ("♗", "♝"),
    "R": ("♖", "♜"),
    "Q": ("♕", "♛"),
    "K": ("♔", "♚"),
}

COLUMNS = ["a", "b", "c", "d", "e", "f", "g", "h"]
ROWS    = ["8", "7", "6", "5", "4", "3", "2", "1"]   # top → bottom on screen


# ── Helper: board tile-id → pixel rect ───────────────────────────────────────
def tile_id_to_rect(tile_id: str) -> pygame.Rect:
    """Return the pygame.Rect for a tile id like 'e4'."""
    col = COLUMNS.index(tile_id[0])
    row = ROWS.index(tile_id[1])          # row 8 is index 0 (top)
    x = LABEL_MARGIN + col * TILE_SIZE
    y = LABEL_MARGIN + row * TILE_SIZE
    return pygame.Rect(x, y, TILE_SIZE, TILE_SIZE)


# ── Drawing helpers ───────────────────────────────────────────────────────────
def draw_board(surface: pygame.Surface) -> None:
    """Draw the 8×8 checkerboard squares."""
    for r, rank in enumerate(ROWS):
        for c, file in enumerate(COLUMNS):
            color = COLOR_LIGHT if (r + c) % 2 == 0 else COLOR_DARK
            rect = pygame.Rect(
                LABEL_MARGIN + c * TILE_SIZE,
                LABEL_MARGIN + r * TILE_SIZE,
                TILE_SIZE, TILE_SIZE
            )
            pygame.draw.rect(surface, color, rect)


def draw_labels(surface: pygame.Surface, font: pygame.font.Font) -> None:
    """Draw rank numbers (1-8) and file letters (a-h) around the board."""
    for r, rank in enumerate(ROWS):
        label = font.render(rank, True, COLOR_LABEL)
        x = (LABEL_MARGIN - label.get_width()) // 2
        y = LABEL_MARGIN + r * TILE_SIZE + (TILE_SIZE - label.get_height()) // 2
        surface.blit(label, (x, y))

    for c, file in enumerate(COLUMNS):
        label = font.render(file, True, COLOR_LABEL)
        x = LABEL_MARGIN + c * TILE_SIZE + (TILE_SIZE - label.get_width()) // 2
        y = LABEL_MARGIN + BOARD_PX + (LABEL_MARGIN - label.get_height()) // 2
        surface.blit(label, (x, y))


def draw_pieces(surface: pygame.Surface, chess_board: ChessBoard,
                piece_font: pygame.font.Font) -> None:
    """Render each piece glyph centred on its tile."""
    for board_row in chess_board.board:
        for tile in board_row:
            if tile.piece is None:
                continue
            piece = tile.piece
            glyph_w, glyph_b = PIECE_GLYPHS.get(piece.name, ("?", "?"))
            glyph  = glyph_w if piece.color == "W" else glyph_b
            color  = COLOR_WHITE_PIECE if piece.color == "W" else COLOR_BLACK_PIECE

            rect = tile_id_to_rect(tile.id)
            text_surf = piece_font.render(glyph, True, color)

            # Subtle shadow / outline for contrast on any square colour
            shadow = piece_font.render(glyph, True, COLOR_PIECE_OUTLINE)
            shadow_rect = shadow.get_rect(center=(rect.centerx + 2, rect.centery + 2))
            surface.blit(shadow, shadow_rect)

            text_rect = text_surf.get_rect(center=rect.center)
            surface.blit(text_surf, text_rect)


def draw_sidebar(surface: pygame.Surface, chess_board: ChessBoard,
                 font: pygame.font.Font, small_font: pygame.font.Font) -> None:
    """Draw the right-hand info panel showing scores and captured pieces."""
    sx = LABEL_MARGIN + BOARD_PX
    sidebar_rect = pygame.Rect(sx, 0, SIDEBAR_WIDTH, WINDOW_H)
    pygame.draw.rect(surface, COLOR_SIDEBAR_BG, sidebar_rect)

    y = 20
    line_h = small_font.get_linesize() + 4

    for color_key, label in (("W", "White"), ("B", "Black")):
        player = chess_board.players[color_key]

        # Heading
        heading = font.render(label, True, COLOR_LABEL)
        surface.blit(heading, (sx + 10, y))
        y += heading.get_height() + 4

        # Score
        score_surf = small_font.render(f"Score: {player.points}", True, COLOR_LABEL)
        surface.blit(score_surf, (sx + 14, y))
        y += line_h

        # Active pieces count
        active_surf = small_font.render(f"Pieces: {len(player.pieces)}", True, COLOR_LABEL)
        surface.blit(active_surf, (sx + 14, y))
        y += line_h

        # Captured pieces
        if player.taken_pieces:
            cap_names = "  ".join(
                PIECE_GLYPHS.get(p.name, ("?", "?"))[0 if p.color == "W" else 1]
                for p in player.taken_pieces
            )
            cap_label = small_font.render("Captured:", True, COLOR_LABEL)
            surface.blit(cap_label, (sx + 14, y))
            y += line_h
            cap_surf = small_font.render(cap_names, True, COLOR_LABEL)
            surface.blit(cap_surf, (sx + 14, y))
            y += line_h

        y += 16   # spacer between players

    # Divider line
    mid_y = y - 8
    pygame.draw.line(surface, COLOR_LABEL,
                     (sx + 10, mid_y), (sx + SIDEBAR_WIDTH - 10, mid_y))


# ── Main UI entry point ───────────────────────────────────────────────────────
def run(chess_board: ChessBoard) -> None:
    """
    Launch a pygame window that displays the current board state.
    The window stays open until the user closes it.
    It re-reads chess_board.board on every frame, so it reflects any
    live changes made by the game engine.
    """
    pygame.init()
    pygame.display.set_caption("Chess")

    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    clock  = pygame.time.Clock()

    # Fonts — fall back gracefully if the system font lacks chess glyphs
    try:
        piece_font = pygame.font.SysFont("segoeuisymbol", int(TILE_SIZE * 0.72))
    except Exception:
        piece_font = pygame.font.SysFont("dejavusans",    int(TILE_SIZE * 0.72))

    label_font  = pygame.font.SysFont("segoeui", 18, bold=True)
    small_font  = pygame.font.SysFont("segoeui", 15)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        screen.fill(COLOR_BACKGROUND)
        draw_board(screen)
        draw_labels(screen, label_font)
        draw_pieces(screen, chess_board, piece_font)
        draw_sidebar(screen, chess_board, label_font, small_font)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    board = ChessBoard()
    run(board)