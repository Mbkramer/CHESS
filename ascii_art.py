
# TILE ASCII
EMPTY_LIGHT = (
    "     \n"
    "     \n"
    "     \n"
    "     \n"
    "     "
)

EMPTY_DARK = (
    " ... \n"
    "     \n"
    " ... \n"
    "     \n"
    " ... "
)

# BLACK PIECES
BP = (
    " .-. \n"
    " |o| \n"
    " [|] \n"
    "/[ ]\\\n"
    "[___]"
)

BR = (
    "|T T|\n"
    "| | |\n"
    " [=] \n"
    "/[ ]\\\n"
    "[___]"
)

BN = (
    ".<<. \n"
    "|<<| \n"
    " [_] \n"
    "/[ ]\\\n"
    "[___]"
)

BB = (
    "  ^  \n"
    " [+] \n"
    " [+] \n"
    "/[ ]\\\n"
    "[___]"
)

BQ = (
    ".v.v.\n"
    "[www]\n"
    " [=] \n"
    "/[ ]\\\n"
    "[___]"
)

BK = (
    " +#+ \n"
    "[+#+]\n"
    " [=] \n"
    "/[ ]\\\n"
    "[___]"
)

# WHITE PIECES
WP = (
    " .-. \n"
    " |#| \n"
    " (#) \n"
    "\\(#)/\n"
    "(###)"
)

WR = (
    "|T#T|\n"
    "|#|#|\n"
    " (#) \n"
    "\\(#)/\n"
    "(###)"
)

WN = (
    ".<<. \n"
    "|##| \n"
    " (#) \n"
    "\\(#)/\n"
    "(###)"
)

WB = (
    "  ^  \n"
    " (#) \n"
    " (#) \n"
    "\\(#)/\n"
    "(###)"
)

WQ = (
    ".v.v.\n"
    "(###)\n"
    " (#) \n"
    "\\(#)/\n"
    "(###)"
)

WK = (
    " +#+ \n"
    "(+#+)\n"
    " (#) \n"
    "\\(#)/\n"
    "(###)"
)

ASCII_PIECES = {
    "EMPTY_LIGHT": EMPTY_LIGHT,
    "EMPTY_DARK":  EMPTY_DARK,
    "WP": WP, "WR": WR, "WN": WN, "WB": WB, "WQ": WQ, "WK": WK,
    "BP": BP, "BR": BR, "BN": BN, "BB": BB, "BQ": BQ, "BK": BK,
}