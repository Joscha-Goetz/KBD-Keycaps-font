#!/usr/bin/env python3
"""Erzeugt KbdFrame.ttf: gerahmte Tasten-Glyphen fuer kitty + render-markdown.

Aufruf:
    python3 make_kbd_font.py /usr/share/fonts/TTF/FiraCodeNerdFont-Regular.ttf

Belegung (Supplementary Private Use Area-B, kollidiert nicht mit Nerd Fonts):
    U+100001        linke Kante
    U+100002        rechte Kante
    U+100020-7E     ASCII 0x20-0x7E mit Rahmen   (Codepunkt = 0x100000 + ord(c))
    U+100100+i      EXTRA[i] mit Rahmen
"""
import argparse
import sys

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

BASE = 0x100000
LEFT = BASE + 0x01
RIGHT = BASE + 0x02
EXTRA = "–←↑→↓⌘⌥⌃⇧ÄÖÜäöüß"


def codepoint_for(ch):
    o = ord(ch)
    if 0x20 <= o <= 0x7E:
        return BASE + o
    return BASE + 0x100 + EXTRA.index(ch)


def rect(pen, x0, y0, x1, y1):
    pen.moveTo((x0, y0))
    pen.lineTo((x0, y1))
    pen.lineTo((x1, y1))
    pen.lineTo((x1, y0))
    pen.closePath()


def edge(pen, adv, x0, t, tb, top, bot, r):
    """Linke Kante: Strich bei x0, Ecken mit Radius r, Linien laufen bis adv."""
    ri = max(r - t, 1)
    pen.moveTo((adv, top))
    pen.lineTo((adv, top - t))
    pen.lineTo((x0 + r, top - t))
    pen.qCurveTo((x0 + t, top - t), (x0 + t, top - t - ri))
    pen.lineTo((x0 + t, bot + tb + ri))
    pen.qCurveTo((x0 + t, bot + tb), (x0 + r, bot + tb))
    pen.lineTo((adv, bot + tb))
    pen.lineTo((adv, bot))
    pen.lineTo((x0 + r, bot))
    pen.qCurveTo((x0, bot), (x0, bot + r))
    pen.lineTo((x0, top - r))
    pen.qCurveTo((x0, top), (x0 + r, top))
    pen.closePath()


class Mirror:
    """Spiegelt horizontal an der Zellmitte und dreht die Konturrichtung."""

    def __init__(self, pen, adv):
        self.pen, self.adv, self.ops = pen, adv, []

    def _m(self, p):
        return (self.adv - p[0], p[1])

    def moveTo(self, p):
        self.ops = [("m", [p])]

    def lineTo(self, p):
        self.ops.append(("l", [p]))

    def qCurveTo(self, *pts):
        self.ops.append(("q", list(pts)))

    def closePath(self):
        pts = [self.ops[0][1][0]]
        segs = []
        for kind, args in self.ops[1:]:
            segs.append((kind, pts[-1], args))
            pts.append(args[-1])
        self.pen.moveTo(self._m(pts[-1]))
        for kind, start, args in reversed(segs):
            if kind == "l":
                self.pen.lineTo(self._m(start))
            else:
                ctrl = [self._m(p) for p in reversed(args[:-1])]
                self.pen.qCurveTo(*ctrl, self._m(start))
        self.pen.closePath()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", help="Terminal-Schrift (.ttf), z.B. FiraCodeNerdFont-Regular.ttf")
    ap.add_argument("-o", "--output", default="KbdFrame.ttf")
    ap.add_argument("--scale", type=float, default=0.82, help="Groesse der Zeichen im Rahmen")
    ap.add_argument("--stroke", type=float, default=0.045, help="Strichstaerke relativ zur Em-Groesse")
    ap.add_argument("--inset", type=float, default=0.05, help="Abstand Rahmen zum Zellrand oben/unten")
    args = ap.parse_args()

    src = TTFont(args.base)
    upm = src["head"].unitsPerEm
    os2 = src["OS/2"]
    use_typo = bool(os2.fsSelection & (1 << 7))
    ascent = os2.sTypoAscender if use_typo else src["hhea"].ascent
    descent = os2.sTypoDescender if use_typo else src["hhea"].descent
    cmap = src.getBestCmap()
    gs = src.getGlyphSet()
    adv = src["hmtx"][cmap[ord("0")]][0]

    t = max(round(upm * args.stroke), 1)
    tb = 2 * t
    inset = round(upm * args.inset)
    top = ascent - inset
    bot = descent + inset
    r = round(adv * 0.3)
    x0 = round(adv * 0.6)
    cy = (top + bot) / 2

    chars = [chr(c) for c in range(0x20, 0x7F)] + list(EXTRA)
    missing = [c for c in chars if ord(c) not in cmap]
    if missing:
        sys.exit("Fehlende Zeichen in der Basisschrift: " + " ".join(missing))

    order = [".notdef", "kbd.left", "kbd.right"]
    glyphs = {}
    cmap_out = {LEFT: "kbd.left", RIGHT: "kbd.right"}

    glyphs[".notdef"] = TTGlyphPen(None).glyph()

    pen = TTGlyphPen(None)
    edge(pen, adv, x0, t, tb, top, bot, r)
    glyphs["kbd.left"] = pen.glyph()

    pen = TTGlyphPen(None)
    edge(Mirror(pen, adv), adv, x0, t, tb, top, bot, r)
    glyphs["kbd.right"] = pen.glyph()

    s = args.scale
    for ch in chars:
        name = "kbd.u%04X" % ord(ch)
        pen = TTGlyphPen(None)
        sg = gs[cmap[ord(ch)]]
        w = src["hmtx"][cmap[ord(ch)]][0]
        k = s * min(1.0, adv / w) if w else s
        dx = (adv - w * k) / 2
        dy = cy - cy * k
        rec = DecomposingRecordingPen(gs)
        sg.draw(rec)
        rec.replay(TransformPen(pen, (k, 0, 0, k, dx, dy)))
        rect(pen, 0, top - t, adv, top)
        rect(pen, 0, bot, adv, bot + tb)
        glyphs[name] = pen.glyph()
        order.append(name)
        cmap_out[codepoint_for(ch)] = name

    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap_out)
    fb.setupGlyf(glyphs)
    glyf = fb.font["glyf"]
    fb.setupHorizontalMetrics({n: (adv, getattr(glyf[n], "xMin", 0)) for n in order})
    fb.setupHorizontalHeader(ascent=src["hhea"].ascent, descent=src["hhea"].descent, lineGap=src["hhea"].lineGap)
    fb.setupNameTable({"familyName": "KbdFrame", "styleName": "Regular"})
    fb.setupOS2(
        version=4,
        sTypoAscender=os2.sTypoAscender,
        sTypoDescender=os2.sTypoDescender,
        sTypoLineGap=os2.sTypoLineGap,
        usWinAscent=os2.usWinAscent,
        usWinDescent=os2.usWinDescent,
        fsSelection=os2.fsSelection & (1 << 7) | 0x40,
        xAvgCharWidth=adv,
        panose=os2.panose,
    )
    fb.setupPost(isFixedPitch=1)
    fb.save(args.output)
    print(f"{args.output}: {len(order) - 1} Glyphen, Zellbreite {adv}/{upm}")


if __name__ == "__main__":
    main()
