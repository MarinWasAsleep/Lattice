"""The three modes of Lattice: Dither, Glyph and Glitch.

They share the engine that lives at the top of the package and nothing else — a mode never
imports another, which is what lets each one be understood, tested and replaced on its own.
"""
