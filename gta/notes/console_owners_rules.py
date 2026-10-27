"""Description-level rules for console-owner flags (NIQ Slice items_extended).

Applied to the (merchant_name, description) aggregate pulled by q_desc in console_owners.sql.
Each description gets:
  explicit_ps5 / explicit_xsx   : the item IS a PS5 / Xbox Series X|S console (incl. bundles)
  inf_ps5 / inf_xsx             : item explicitly requires PS5 / Series X|S (games, DualSense,
                                  accessories, PS5-version PSN items, Series X|S MS Store items)
                                  -- strict: no last-gen (PS4 / Xbox One) and not multi-platform
  inf_ps5_xgen / inf_xsx_xgen   : same but the description also names PS4 / Xbox One (cross-gen)
  agn_ps / agn_xbox             : any PlayStation / Xbox ownership or usage signal (any gen)
"""
import warnings
import numpy as np
import pandas as pd

SEN, MSS = "Sony Entertainment Network", "Microsoft store"
MARKETPLACES = {"eBay", "Mercari", "StockX", "OfferUp", "Poshmark", "Whatnot", "TikTok", "Etsy", "Temu",
                "Facebook Marketplace", "Swappa", "Depop"}


def norm(s: pd.Series) -> pd.Series:
    s = s.fillna("").str.upper()
    s = s.str.replace(r"[®™©]", " ", regex=True).str.replace("?", " ", regex=False)
    return s.str.replace(r"\s+", " ", regex=True).str.strip()


PS5 = r"\bPS ?5\b|\bPS5|PLAYSTATION ?5\b|PLAYSTATION5|DUAL ?SENSE"
XBOX = r"\bXBOX"
XSX = r"XBOX ?SERIES|\bSERIES ?X\b|\bSERIES ?X ?[|/&]? ?S\b"          # only counted when XBOX also present
LASTGEN_PS = r"\bPS ?4\b|\bPS4|PLAYSTATION ?4|\bPS ?3\b|PLAYSTATION ?3|DUAL ?SHOCK|\bPS VITA|\bPSP\b"
LASTGEN_XB = r"XBOX ?ONE|XBOX ?360|\bXB1\b"
OTHER_PLAT = r"\bPC\b|WINDOWS|NINTENDO|SWITCH|\bSTEAM\b|\bMAC\b|IPHONE|ANDROID|\bIOS\b|META QUEST|OCULUS"

CONSOLE_WORD = r"\bCONSOLES?\b"
# A console item: platform term + 'console' or a bare model name, minus accessories / non-items.
CONSOLE_BARE = (r"^(SONY |MICROSOFT |SONY - |MICROSOFT - |NEW |BRAND NEW |\(SINGLE USE - RESTRICTED\) )*"
                r"(SONY )?(PLAYSTATION ?5|PS ?5|XBOX SERIES ?[XS])\b")
NOT_CONSOLE = (r"\bFOR (THE |YOUR |SONY |MICROSOFT )*(PS|PLAYSTATION|XBOX|SERIES)|COMPATIBLE|\bCOVERS?\b|\bSKINS?\b|"
               r"\bSTAND\b|VERTICAL|DISC DRIVE|PORTAL|REMOTE PLAYER|HEADSET|HEADPHONE|\bCASES?\b|\bBAG\b|"
               r"MOUNT|\bDOCK|\bFAN\b|COOLING|DECAL|STICKER|\bSSD\b|HARD DRIVE|EXPANSION|STORAGE|CABLE|"
               r"PROTECT|DUST|FACEPLATE|SHELL|\bPLATES?\b|REPLACEMENT|\bPARTS?\b|GIFT ?CARD|\bPOSA\b|PRIZE|"
               r"SWEEP|DISCOUNT|PROTECTION PLAN|WARRANTY|GEEK SQUAD|ASURION|ALLSTATE|TRADE.?IN|RENTAL|LEGO|\bTOY|"
               r"FRIDGE|CAKE|COSTUME|SHIRT|HOODIE|POSTER|CONSOLE EDITION|\(GAME|\(ADD-ON|BATTER|KEYBOARD|"
               r"WHEEL|ORGANIZER|SHELF|\bDESK|HOLDER|ACCESSOR|ADAPTER|REPAIR|HDMI|SUBSCRIPTION|MEMBERSHIP|"
               r"GAME ?PASS|EMPTY BOX|BOX ONLY|\bPHOTO|ORNAMENT|KEYCHAIN|FIGUR|BLANKET|PILLOW|LAMP|\bLED\b|"
               r"CHARGING STATION$|\bCHARGER\b|\bCHARGING (DOCK|STAND)|RETURN|RESTOCK|INSURANCE|"
               r"MOTHERBOARD|\bDRIVE\b|SOLID STATE|POWER SUPPLY|\bFOAM|\bPAD\b|SHAPED|CROCHET|\bBOOK\b|\bGUIDE\b|DIGITAL CODE|"
               r"PRE-?ORDER DEPOSIT|\bDEPOSIT|\bTRAY\b|\bRACK\b|GAME CONTROLLER$")
CONSOLE_BUNDLE_OK = r"CONSOLE (BUNDLE|WITH)|BUNDLE WITH|CONSOLE [-–] |CONSOLE$|CONSOLE \(|CONSOLE,"

JUNK = (r"GIFT ?CARD|\bPOSA\b|E-?GIFT|PRIZE|SWEEP|SHIRT|\bTEE\b|HOODIE|SWEATSHIRT|POSTER|LEGO|\bTOY|FRIDGE|CAKE|"
        r"COSTUME|ORNAMENT|KEYCHAIN|FIGURINE|BLANKET|PILLOW|\bMUG\b|SOCKS|PAJAMA|PYJAMA|BACKPACK|LUNCH|"
        r"PHONE CASE|IPHONE|SAMSUNG|\bPARTY\b|BALLOON|BIRTHDAY|DECORATION|\bWRAP|NECKLACE|EARRING|"
        r"CANDLE|SNEAKER|SHOE|SLIPPER|HAT\b|\bCAP\b|PATCH|PIN\b|STUFFED|PLUSH|PRINTABLE|SVG|DIGITAL DOWNLOAD|"
        r"COLORING|NOTEBOOK|STATIONERY|WALLPAPER|ART PRINT|CANVAS|\bFRAME|LAMP|NIGHT LIGHT|\bVUE\b|"
        r"PLAYSTATION VUE|GAMER ?TAG|RENTAL|REPAIR|WARRANTY|PROTECTION PLAN|INSURANCE|GEEK SQUAD|ASURION|"
        r"TRADE.?IN|EMPTY BOX|BOX ONLY|\bBOOK\b|STRATEGY GUIDE|NERF|SQUISHMALLOW")
PC_PASS = r"PC GAME ?PASS|GAME ?PASS FOR PC|FOR PC\b|\bPC\)|\(PC|WINDOWS"

PS_ANY = r"\bPS ?[2345]\b|\bPS[2345]|PLAYSTATION|DUAL ?SENSE|DUAL ?SHOCK|\bPSVR|\bPS VR|\bPSN\b|\bPS PLUS\b|\bPS VITA"
XB_ANY = r"\bXBOX"


def has(s: pd.Series, pat: str) -> pd.Series:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return s.str.contains(pat, regex=True)


def classify(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    D = norm(d["DESCRIPTION"])
    m = d["MERCHANT_NAME"].fillna("")
    price = d["MED_PRICE"]
    d["IS_CANCEL"] = m.str.endswith(" Cancellation")
    d["IS_MARKETPLACE"] = m.isin(MARKETPLACES)
    junk = has(D, JUNK)
    ps5 = has(D, PS5)
    xbox = has(D, XBOX) | (m == MSS)
    xsx = has(D, XSX) & has(D, XBOX)
    lg_ps, lg_xb = has(D, LASTGEN_PS), has(D, LASTGEN_XB)
    other = has(D, OTHER_PLAT)
    gta6 = has(D, r"GRAND THEFT AUTO ?VI\b")

    # 1. explicit console
    conword = has(D, CONSOLE_WORD)
    bare = has(D, CONSOLE_BARE) & price.between(230, 1500)
    for_acc = has(D, r"\bFOR (THE |YOUR |SONY |MICROSOFT )*(PS|PLAYSTATION|XBOX|SERIES)|COMPATIBLE|\bDRIVE\b|EXPANSION")
    blocked = has(D, NOT_CONSOLE) & ~((has(D, CONSOLE_BUNDLE_OK) | has(D, r"GAMING CONSOLE|BUNDLE")) & price.ge(230) & ~for_acc)
    price_ok = price.isna() | price.eq(0) | price.between(150, 2000)
    explicit_base = (conword | bare) & ~blocked & price_ok & ~d["IS_CANCEL"]
    # Sony direct sells consoles as 'PlayStation 5 Console'; MS Store as bare 'Xbox Series X' / 'Xbox Series S'
    ps5_tok = has(D, r"\bPS ?5\b|\bPS5|PLAYSTATION ?5\b|PLAYSTATION5")
    d["EXPLICIT_PS5"] = explicit_base & ps5_tok & ~has(D, r"\bPS ?4 PRO|PLAYSTATION ?4")
    d["EXPLICIT_XSX"] = explicit_base & xsx & ~has(D, r"XBOX ONE (X|S)\b(?!.*SERIES)")
    both = d["EXPLICIT_PS5"] & d["EXPLICIT_XSX"]
    d.loc[both, ["EXPLICIT_PS5", "EXPLICIT_XSX"]] = False   # 'PS5 or Xbox Series' listings: ambiguous

    # 2. inferred (requires current gen)
    astro = (m == SEN) & has(D, r"ASTRO.?S PLAYROOM")            # PS5 pre-installed title
    inf_ok = ~junk & ~d["IS_CANCEL"] & ~d["EXPLICIT_PS5"] & ~d["EXPLICIT_XSX"] & ~(price < 0)
    ps5_c = (ps5 | astro) & ~xsx & ~(has(D, XBOX) & (m != SEN))
    xsx_c = xsx & ~ps5
    # 'headset for PS5 / PC / Switch' style multi-platform accessories; Sony first-party PS5 accessories
    # (DualSense, PULSE, Access controller) are often listed 'for PS5, PC, Mac' but are still PS5-led
    multi = other & ~m.isin([SEN, MSS]) & ~has(D, r"DUAL ?SENSE|\bPULSE\b|ACCESS CONTROLLER")
    d["INF_PS5"] = inf_ok & ps5_c & ~lg_ps & ~multi
    d["INF_XSX"] = inf_ok & xsx_c & ~lg_xb & ~multi
    d["INF_PS5_XGEN"] = inf_ok & ps5_c & ~multi                     # also allows 'PS4 & PS5'
    d["INF_XSX_XGEN"] = inf_ok & xsx_c & ~multi                     # also allows 'Xbox One & Series X|S'
    d["INF_PS5_MULTI"] = inf_ok & ps5 & ~d["INF_PS5_XGEN"]          # PS5 named alongside Xbox/PC etc.
    d["INF_XSX_MULTI"] = inf_ok & xsx & ~d["INF_XSX_XGEN"]
    d["SEN_FREE"] = (m == SEN) & price.fillna(0).eq(0)              # $0 PSN claims (PS Plus monthly games)

    # 3. model-agnostic
    agn_ok = ~junk & ~d["IS_CANCEL"] & ~m.isin(["NFL Game Pass"])
    d["AGN_PS"] = agn_ok & ((m == SEN) | has(D, PS_ANY)) & ~((m == MSS) & ~has(D, PS_ANY))
    d["AGN_XB"] = agn_ok & ((has(D, XB_ANY) & ~has(D, PC_PASS)) | xsx) & ~(m == SEN)
    # generic accessories that list every platform (e.g. 'headset for PS5, Xbox, PC, Switch') are weak
    d["AGN_MULTI"] = has(D, PS_ANY) & has(D, XB_ANY)
    d["IS_GTA6"] = gta6
    return d
