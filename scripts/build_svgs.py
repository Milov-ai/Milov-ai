#!/usr/bin/env python3
"""Deterministic SSOT generator and validator for Milov-ai GitHub profile SVGs (v2).

Pure Python 3 standard library. Zero external runtime dependencies, zero project leaks.
Modes:
  python scripts/build_svgs.py --write   Generate 4 dark/light SVG pairs (8 files) in ./assets/
  python scripts/build_svgs.py --check   Validate drift, XML/CSP, WCAG AA, bounds, README policy
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
README_PATH = ROOT / "README.md"

FONT_SANS = (
    "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif"
)
FONT_MONO = (
    "ui-monospace, SFMono-Regular, 'Cascadia Mono', Consolas, Menlo, 'Liberation Mono', monospace"
)

MAX_SVG_BYTES = 25_600
URL_ALLOWLIST: frozenset[str] = frozenset()

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#080F1E",
        "bg2": "#112040",
        "surface": "#0F1A30",
        "surface_alt": "#15233E",
        "pill": "#1B2740",
        "border": "rgba(148,163,184,0.34)",
        "inner_border": "#263B66",
        "grid": "#1E3A8A",
        "grid_opacity": "0.24",
        "rail_track": "#1E3A8A",
        "title": "#F8FAFC",
        "subtitle": "#CBD5E1",
        "muted": "#94A3B8",
        "blue": "#93C5FD",
        "blue_stroke": "#3B82F6",
        "blue_soft": "#172554",
        "emerald": "#34D399",
        "emerald_stroke": "#10B981",
        "emerald_soft": "#064E3B",
        "cyan": "#38BDF8",
        "cyan_stroke": "#06B6D4",
        "cyan_soft": "#0C354D",
        "violet": "#C4B5FD",
        "violet_stroke": "#8B5CF6",
        "violet_soft": "#2E1065",
        "amber": "#FBBF24",
        "amber_stroke": "#F59E0B",
        "amber_soft": "#451A03",
        "glow_opacity": "0.24",
    },
    "light": {
        "bg": "#F8FAFC",
        "bg2": "#EFF6FF",
        "surface": "#FFFFFF",
        "surface_alt": "#F1F5F9",
        "pill": "#FFFFFF",
        "border": "rgba(100,116,139,0.38)",
        "inner_border": "#CBD5E1",
        "grid": "#93C5FD",
        "grid_opacity": "0.28",
        "rail_track": "#CBD5E1",
        "title": "#0F172A",
        "subtitle": "#334155",
        "muted": "#475569",
        "blue": "#1D4ED8",
        "blue_stroke": "#2563EB",
        "blue_soft": "#DBEAFE",
        "emerald": "#047857",
        "emerald_stroke": "#059669",
        "emerald_soft": "#D1FAE5",
        "cyan": "#0369A1",
        "cyan_stroke": "#0284C7",
        "cyan_soft": "#E0F2FE",
        "violet": "#6D28D9",
        "violet_stroke": "#7C3AED",
        "violet_soft": "#EDE9FE",
        "amber": "#B45309",
        "amber_stroke": "#D97706",
        "amber_soft": "#FEF3C7",
        "glow_opacity": "0.14",
    },
}

WCAG_PAIRS: list[tuple[str, str]] = [
    ("title", "bg"),
    ("title", "bg2"),
    ("title", "surface"),
    ("title", "pill"),
    ("subtitle", "bg"),
    ("subtitle", "bg2"),
    ("subtitle", "surface"),
    ("muted", "bg"),
    ("muted", "surface"),
    ("blue", "bg"),
    ("blue", "surface"),
    ("blue", "pill"),
    ("blue", "blue_soft"),
    ("emerald", "bg"),
    ("emerald", "surface"),
    ("emerald", "pill"),
    ("emerald", "emerald_soft"),
    ("cyan", "bg"),
    ("cyan", "surface"),
    ("cyan", "pill"),
    ("cyan", "cyan_soft"),
    ("violet", "bg"),
    ("violet", "surface"),
    ("violet", "pill"),
    ("violet", "violet_soft"),
    ("amber", "bg"),
    ("amber", "surface"),
    ("amber", "pill"),
    ("amber", "amber_soft"),
]

# Conservative bounds: (svg_key, label, text, font_size, is_mono, box_w, x_start, max_right)
BOUND_CHECKS: list[tuple[str, str, str, float, bool, float, float, float]] = [
    ("hero", "status_pill", "RING -1 TO CLOUD · FULL-SPECTRUM ENGINEERING", 12.0, True, 368.0, 58.0, 426.0),
    ("hero", "headline", "Milov-ai // Systems · Data · AI", 30.0, False, 580.0, 34.0, 614.0),
    ("hero", "subtitle", "Hypervisors & RE · Rust Crypto · Distributed Data · Full-Stack & Mobile · AI", 13.5, False, 595.0, 34.0, 629.0),
    ("hero", "chip1", "RING -1 HV", 11.5, True, 92.0, 44.0, 140.0),
    ("hero", "chip2", "RUST CRYPTO", 11.5, True, 92.0, 158.0, 254.0),
    ("hero", "chip3", "DATA CLOUD", 11.5, True, 92.0, 272.0, 368.0),
    ("hero", "chip4", "FULL-STACK", 11.5, True, 92.0, 386.0, 482.0),
    ("hero", "chip5", "AI AGENTS", 11.5, True, 92.0, 500.0, 596.0),
    ("layers", "l5_1", "Python · scikit-learn · LLMs (Vercel AI SDK · OpenAI · Gemini · LiteLLM) · MCP", 11.5, True, 700.0, 92.0, 792.0),
    ("layers", "l4_1", "Apache Kafka (KRaft) · HDFS · MapReduce · PySpark (Batch+Stream) · Parquet · PG 17", 11.5, True, 700.0, 92.0, 792.0),
    ("layers", "l3_1", "TypeScript · Angular (RxJS · PWA) · React 19 · Next.js · Node (Express · Fastify)", 11.5, True, 700.0, 92.0, 792.0),
    ("layers", "l2_1", "Rust (Rayon · k256 · LTO Fat) · secp256k1 Jacobian · Pollard's Kangaroo O(√W)", 11.5, True, 700.0, 92.0, 792.0),
    ("layers", "l1_1", "C · C++17 · x64 MASM · WDK · AMD-V (SVM · VMCB · 4-Level NPT · VMMCALL · GIF=0)", 11.5, True, 700.0, 92.0, 792.0),
    ("matrix", "c1_1", "Angular · RxJS · PWA", 11.5, True, 214.0, 40.0, 254.0),
    ("matrix", "c2_1", "Node · Express · Fastify", 11.5, True, 214.0, 315.0, 529.0),
    ("matrix", "c3_1", "PostgreSQL · PL/pgSQL", 11.5, True, 214.0, 590.0, 804.0),
]

HERO_TEMPLATE = Template(
    """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 260" width="840" height="260" role="img" aria-label="Milov-ai — Ingeniería de Sistemas Ring -1, Criptografía Rust, Datos Distribuidos, Full-Stack y AI">
  <title>Milov-ai — Full-Spectrum Systems, Data &amp; AI Engineering</title>
  <defs>
    <linearGradient id="hBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="$bg"/>
      <stop offset="100%" stop-color="$bg2"/>
    </linearGradient>
    <linearGradient id="hAccent" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="$amber_stroke"/>
      <stop offset="25%" stop-color="$violet_stroke"/>
      <stop offset="50%" stop-color="$blue_stroke"/>
      <stop offset="75%" stop-color="$cyan_stroke"/>
      <stop offset="100%" stop-color="$emerald_stroke"/>
    </linearGradient>
    <linearGradient id="hSheen" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="$cyan_stroke" stop-opacity="0"/>
      <stop offset="50%" stop-color="$cyan_stroke" stop-opacity="0.10"/>
      <stop offset="100%" stop-color="$cyan_stroke" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="hHalo" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="$violet_stroke" stop-opacity="$glow_opacity"/>
      <stop offset="55%" stop-color="$blue_stroke" stop-opacity="0.09"/>
      <stop offset="100%" stop-color="$bg" stop-opacity="0"/>
    </radialGradient>
    <pattern id="hGrid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M 28 0 L 0 0 0 28" fill="none" stroke="$grid" stroke-width="0.7" opacity="$grid_opacity"/>
    </pattern>
    <clipPath id="hClip">
      <rect x="2" y="2" width="836" height="256" rx="14"/>
    </clipPath>
  </defs>
  <style>
    .spin-cw { animation: spinCW 30s linear infinite; transform-origin: 0px 0px; }
    .spin-ccw { animation: spinCCW 16s linear infinite; transform-origin: 0px 0px; }
    .spin-fast { animation: spinCW 10s linear infinite; transform-origin: 0px 0px; }
    .pulse-dot { animation: pulseFade 2.2s ease-in-out infinite; }
    .pulse-ring { animation: pulseRing 3.0s ease-in-out infinite; }
    .bus-flow { animation: dashFlow 3.2s linear infinite; }
    .bus-flow-rev { animation: dashFlowRev 4.4s linear infinite; }
    .scan-line { animation: scanSweep 9.5s ease-in-out infinite; }
    @keyframes spinCW { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    @keyframes spinCCW { from { transform: rotate(360deg); } to { transform: rotate(0deg); } }
    @keyframes pulseFade { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
    @keyframes pulseRing { 0%, 100% { opacity: 0.85; } 50% { opacity: 0.20; } }
    @keyframes dashFlow { from { stroke-dashoffset: 64; } to { stroke-dashoffset: 0; } }
    @keyframes dashFlowRev { from { stroke-dashoffset: 0; } to { stroke-dashoffset: 64; } }
    @keyframes scanSweep { 0%, 100% { transform: translateX(-180px); } 50% { transform: translateX(740px); } }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
  </style>
  <g clip-path="url(#hClip)">
    <rect x="2" y="2" width="836" height="256" rx="14" fill="url(#hBg)"/>
    <rect x="2" y="2" width="836" height="256" rx="14" fill="url(#hGrid)"/>
    <circle cx="724" cy="110" r="130" fill="url(#hHalo)"/>
    <rect class="scan-line" x="0" y="6" width="220" height="248" fill="url(#hSheen)"/>
    <rect x="2" y="2" width="836" height="4" fill="url(#hAccent)"/>
  </g>
  <rect x="2" y="2" width="836" height="256" rx="14" fill="none" stroke="$border" stroke-width="1.5"/>
  <path d="M 16 26 L 16 16 L 26 16 M 814 16 L 824 16 L 824 26 M 16 234 L 16 244 L 26 244 M 814 244 L 824 244 L 824 234" fill="none" stroke="$blue_stroke" stroke-width="1.4" opacity="0.55"/>
  <g transform="translate(34, 24)">
    <rect x="0" y="0" width="398" height="28" rx="14" fill="$pill" stroke="$inner_border" stroke-width="1"/>
    <circle class="pulse-ring" cx="17" cy="14" r="7" fill="$emerald_stroke" opacity="0.28"/>
    <circle class="pulse-dot" cx="17" cy="14" r="4" fill="$emerald"/>
    <text x="31" y="18.5" fill="$cyan" font-family="$font_mono" font-size="12" font-weight="700">RING -1 TO CLOUD · FULL-SPECTRUM ENGINEERING</text>
  </g>
  <text x="34" y="90" fill="$title" font-family="$font_sans" font-size="30" font-weight="800" letter-spacing="-0.4">Milov-ai <tspan fill="$violet" font-weight="600">//</tspan> <tspan fill="$subtitle" font-size="23" font-weight="600">Systems · Data · AI</tspan></text>
  <text x="34" y="119" fill="$subtitle" font-family="$font_sans" font-size="13.5" font-weight="500">Hypervisors &amp; RE · Rust Crypto · Distributed Data · Full-Stack &amp; Mobile · AI</text>
  <g font-family="$font_mono" font-size="11.5" font-weight="700">
    <rect x="34" y="142" width="106" height="34" rx="8" fill="$pill" stroke="$inner_border" stroke-width="1"/>
    <rect x="34" y="142" width="4" height="34" rx="2" fill="$amber_stroke"/>
    <text x="89" y="163" text-anchor="middle" fill="$amber">RING -1 HV</text>
    <rect x="148" y="142" width="106" height="34" rx="8" fill="$pill" stroke="$inner_border" stroke-width="1"/>
    <rect x="148" y="142" width="4" height="34" rx="2" fill="$violet_stroke"/>
    <text x="203" y="163" text-anchor="middle" fill="$violet">RUST CRYPTO</text>
    <rect x="262" y="142" width="106" height="34" rx="8" fill="$pill" stroke="$inner_border" stroke-width="1"/>
    <rect x="262" y="142" width="4" height="34" rx="2" fill="$blue_stroke"/>
    <text x="317" y="163" text-anchor="middle" fill="$blue">DATA CLOUD</text>
    <rect x="376" y="142" width="106" height="34" rx="8" fill="$pill" stroke="$inner_border" stroke-width="1"/>
    <rect x="376" y="142" width="4" height="34" rx="2" fill="$cyan_stroke"/>
    <text x="431" y="163" text-anchor="middle" fill="$cyan">FULL-STACK</text>
    <rect x="490" y="142" width="106" height="34" rx="8" fill="$pill" stroke="$inner_border" stroke-width="1"/>
    <rect x="490" y="142" width="4" height="34" rx="2" fill="$emerald_stroke"/>
    <text x="545" y="163" text-anchor="middle" fill="$emerald">AI AGENTS</text>
  </g>
  <g transform="translate(724, 110)">
    <g class="spin-cw">
      <circle cx="0" cy="0" r="66" fill="none" stroke="$inner_border" stroke-width="1.4" stroke-dasharray="4 6"/>
      <circle cx="66" cy="0" r="4.5" fill="$amber_stroke"/>
      <circle cx="-66" cy="0" r="3.5" fill="$emerald_stroke"/>
    </g>
    <g class="spin-ccw">
      <circle cx="0" cy="0" r="50" fill="none" stroke="$amber_stroke" stroke-width="2.4" stroke-dasharray="46 268" stroke-dashoffset="0"/>
      <circle cx="0" cy="0" r="50" fill="none" stroke="$violet_stroke" stroke-width="2.4" stroke-dasharray="46 268" stroke-dashoffset="-63"/>
      <circle cx="0" cy="0" r="50" fill="none" stroke="$blue_stroke" stroke-width="2.4" stroke-dasharray="46 268" stroke-dashoffset="-126"/>
      <circle cx="0" cy="0" r="50" fill="none" stroke="$cyan_stroke" stroke-width="2.4" stroke-dasharray="46 268" stroke-dashoffset="-189"/>
      <circle cx="0" cy="0" r="50" fill="none" stroke="$emerald_stroke" stroke-width="2.4" stroke-dasharray="46 268" stroke-dashoffset="-252"/>
    </g>
    <g class="spin-fast">
      <circle cx="0" cy="0" r="35" fill="none" stroke="$cyan_stroke" stroke-width="1.2" stroke-dasharray="14 10" opacity="0.80"/>
      <circle cx="0" cy="-35" r="3" fill="$violet_stroke"/>
    </g>
    <polygon points="0,-24 21,-12 21,12 0,24 -21,12 -21,-12" fill="$surface" stroke="$violet_stroke" stroke-width="1.6"/>
    <text x="0" y="5" text-anchor="middle" fill="$title" font-family="$font_mono" font-size="13" font-weight="800">x64</text>
  </g>
  <g>
    <line x1="34" y1="214" x2="806" y2="214" stroke="$rail_track" stroke-width="1.6"/>
    <path d="M 642 214 Q 628 214 628 200 L 628 150 Q 628 136 642 136 L 658 136" fill="none" stroke="$rail_track" stroke-width="1.4"/>
    <path class="bus-flow" d="M 34 214 L 806 214" fill="none" stroke="url(#hAccent)" stroke-width="2.4" stroke-dasharray="22 42"/>
    <path class="bus-flow-rev" d="M 642 214 Q 628 214 628 200 L 628 150 Q 628 136 642 136 L 658 136" fill="none" stroke="$violet_stroke" stroke-width="1.8" stroke-dasharray="10 22" opacity="0.85"/>
    <circle cx="34" cy="214" r="4" fill="$amber_stroke"/>
    <circle cx="290" cy="214" r="4" fill="$violet_stroke"/>
    <circle cx="548" cy="214" r="4" fill="$blue_stroke"/>
    <circle cx="806" cy="214" r="4" fill="$emerald_stroke"/>
    <text x="34" y="237" fill="$muted" font-family="$font_mono" font-size="11.5" font-weight="600">01 // RING -1 SILICON &amp; RE</text>
    <text x="290" y="237" fill="$muted" font-family="$font_mono" font-size="11.5" font-weight="600">02 // RUST &amp; DATA PIPELINES</text>
    <text x="548" y="237" fill="$muted" font-family="$font_mono" font-size="11.5" font-weight="600">03 // CLOUD, MOBILE &amp; AI</text>
  </g>
</svg>
"""
)

LAYERS_TEMPLATE = Template(
    """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 454" width="840" height="454" role="img" aria-label="Arquitectura vertical de 5 capas: desde Ring -1 Hypervisors y Reverse Engineering hasta Rust Cryptography, Full-Stack Mobile, Distributed Data y Applied AI">
  <title>Arquitectura Vertical de 5 Capas — Ring -1 a Cloud &amp; IA</title>
  <defs>
    <linearGradient id="lBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="$bg"/>
      <stop offset="100%" stop-color="$bg2"/>
    </linearGradient>
    <linearGradient id="lSpine" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="$emerald_stroke"/>
      <stop offset="25%" stop-color="$blue_stroke"/>
      <stop offset="50%" stop-color="$cyan_stroke"/>
      <stop offset="75%" stop-color="$violet_stroke"/>
      <stop offset="100%" stop-color="$amber_stroke"/>
    </linearGradient>
    <pattern id="lGrid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M 28 0 L 0 0 0 28" fill="none" stroke="$grid" stroke-width="0.65" opacity="$grid_opacity"/>
    </pattern>
    <clipPath id="lClip">
      <rect x="2" y="2" width="836" height="450" rx="14"/>
    </clipPath>
  </defs>
  <style>
    .l-flow { animation: lDash 2.8s linear infinite; }
    .l-flow-up { animation: lDashUp 3.2s linear infinite; }
    .l-pulse { animation: lPulse 2.2s ease-in-out infinite; }
    .l-b1 { animation: lPulse 1.8s ease-in-out infinite; }
    .l-b2 { animation: lPulse 1.8s ease-in-out 0.4s infinite; }
    .l-b3 { animation: lPulse 1.8s ease-in-out 0.8s infinite; }
    @keyframes lDash { from { stroke-dashoffset: 40; } to { stroke-dashoffset: 0; } }
    @keyframes lDashUp { from { stroke-dashoffset: 0; } to { stroke-dashoffset: 40; } }
    @keyframes lPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.30; } }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
  </style>
  <g clip-path="url(#lClip)">
    <rect x="2" y="2" width="836" height="450" rx="14" fill="url(#lBg)"/>
    <rect x="2" y="2" width="836" height="450" rx="14" fill="url(#lGrid)"/>
  </g>
  <rect x="2" y="2" width="836" height="450" rx="14" fill="none" stroke="$border" stroke-width="1.5"/>
  <circle class="l-pulse" cx="30" cy="29" r="4.5" fill="$emerald"/>
  <text x="44" y="33" fill="$emerald" font-family="$font_mono" font-size="11.5" font-weight="700">VERTICAL ENGINEERING ARCHITECTURE · 5 LAYERS</text>
  <text x="24" y="56" fill="$title" font-family="$font_sans" font-size="19" font-weight="800">Stack Técnico Completo · De Ring -1 a Cloud &amp; IA</text>
  <g>
    <line x1="44" y1="102" x2="44" y2="404" stroke="$rail_track" stroke-width="2.2"/>
    <path class="l-flow-up" d="M 44 102 L 44 404" fill="none" stroke="url(#lSpine)" stroke-width="2.6" stroke-dasharray="14 26"/>
    <line x1="58" y1="102" x2="74" y2="102" stroke="$emerald_stroke" stroke-width="1.6"/>
    <line x1="58" y1="178" x2="74" y2="178" stroke="$blue_stroke" stroke-width="1.6"/>
    <line x1="58" y1="254" x2="74" y2="254" stroke="$cyan_stroke" stroke-width="1.6"/>
    <line x1="58" y1="330" x2="74" y2="330" stroke="$violet_stroke" stroke-width="1.6"/>
    <line x1="58" y1="406" x2="74" y2="406" stroke="$amber_stroke" stroke-width="1.6"/>
  </g>
  <g>
    <rect x="24" y="88" width="40" height="28" rx="8" fill="$emerald_soft" stroke="$emerald_stroke" stroke-width="1.2"/>
    <text x="44" y="106" text-anchor="middle" fill="$emerald" font-family="$font_mono" font-size="11.5" font-weight="800">L5</text>
    <rect x="74" y="70" width="742" height="64" rx="10" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="74" y="70" width="5" height="64" rx="2.5" fill="$emerald_stroke"/>
    <text x="92" y="92" fill="$title" font-family="$font_sans" font-size="14" font-weight="700">Applied AI, Machine Learning &amp; Agent Orchestration</text>
    <path class="l-flow" d="M 744 88 L 754 88 L 759 80 L 765 95 L 771 84 L 777 88 L 796 88" fill="none" stroke="$emerald_stroke" stroke-width="1.8" stroke-dasharray="16 8"/>
    <text x="92" y="110" fill="$emerald" font-family="$font_mono" font-size="11.5" font-weight="600">Python · scikit-learn · LLMs (Vercel AI SDK · OpenAI · Gemini · LiteLLM) · MCP</text>
    <text x="92" y="126" fill="$subtitle" font-family="$font_mono" font-size="11">Modelado estadístico · MediaPipe CV · Faster-Whisper ASR · Playwright · Seguridad LLM</text>
  </g>
  <g>
    <rect x="24" y="164" width="40" height="28" rx="8" fill="$blue_soft" stroke="$blue_stroke" stroke-width="1.2"/>
    <text x="44" y="182" text-anchor="middle" fill="$blue" font-family="$font_mono" font-size="11.5" font-weight="800">L4</text>
    <rect x="74" y="146" width="742" height="64" rx="10" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="74" y="146" width="5" height="64" rx="2.5" fill="$blue_stroke"/>
    <text x="92" y="168" fill="$title" font-family="$font_sans" font-size="14" font-weight="700">Distributed Data Engineering &amp; Cloud Automation</text>
    <path class="l-flow" d="M 744 162 L 796 162" fill="none" stroke="$blue_stroke" stroke-width="2" stroke-dasharray="8 8"/>
    <path class="l-flow-up" d="M 744 170 L 796 170" fill="none" stroke="$amber_stroke" stroke-width="1.6" stroke-dasharray="6 6"/>
    <text x="92" y="186" fill="$blue" font-family="$font_mono" font-size="11.5" font-weight="600">Apache Kafka (KRaft) · HDFS · MapReduce · PySpark (Batch+Stream) · Parquet · PG 17</text>
    <text x="92" y="202" fill="$subtitle" font-family="$font_mono" font-size="11">Arquitectura Lambda · Calidad fail-fast · FastAPI · Redis · Docker GPU/CPU · FinOps</text>
  </g>
  <g>
    <rect x="24" y="240" width="40" height="28" rx="8" fill="$cyan_soft" stroke="$cyan_stroke" stroke-width="1.2"/>
    <text x="44" y="258" text-anchor="middle" fill="$cyan" font-family="$font_mono" font-size="11.5" font-weight="800">L3</text>
    <rect x="74" y="222" width="742" height="64" rx="10" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="74" y="222" width="5" height="64" rx="2.5" fill="$cyan_stroke"/>
    <text x="92" y="244" fill="$title" font-family="$font_sans" font-size="14" font-weight="700">Full-Stack Enterprise Web, GIS &amp; Native Mobile</text>
    <g transform="translate(756, 232)">
      <rect class="l-b1" x="0" y="6" width="6" height="10" rx="1.5" fill="$cyan_stroke"/>
      <rect class="l-b2" x="10" y="1" width="6" height="15" rx="1.5" fill="$cyan_stroke"/>
      <rect class="l-b3" x="20" y="4" width="6" height="12" rx="1.5" fill="$cyan_stroke"/>
      <rect class="l-b1" x="30" y="8" width="6" height="8" rx="1.5" fill="$cyan_stroke"/>
    </g>
    <text x="92" y="262" fill="$cyan" font-family="$font_mono" font-size="11.5" font-weight="600">TypeScript · Angular (RxJS · PWA) · React 19 · Next.js · Node (Express · Fastify)</text>
    <text x="92" y="278" fill="$subtitle" font-family="$font_mono" font-size="11">Socket.IO · PL/pgSQL · Supabase · AWS S3/SES · Stripe · D3/MapLibre · Capacitor Kotlin</text>
  </g>
  <g>
    <rect x="24" y="316" width="40" height="28" rx="8" fill="$violet_soft" stroke="$violet_stroke" stroke-width="1.2"/>
    <text x="44" y="334" text-anchor="middle" fill="$violet" font-family="$font_mono" font-size="11.5" font-weight="800">L2</text>
    <rect x="74" y="298" width="742" height="64" rx="10" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="74" y="298" width="5" height="64" rx="2.5" fill="$violet_stroke"/>
    <text x="92" y="320" fill="$title" font-family="$font_sans" font-size="14" font-weight="700">High-Performance Native Rust &amp; Applied Cryptography</text>
    <path class="l-flow" d="M 744 322 C 756 306, 768 326, 780 310 C 788 304, 792 314, 798 308" fill="none" stroke="$violet_stroke" stroke-width="1.8" stroke-dasharray="14 6"/>
    <text x="92" y="338" fill="$violet" font-family="$font_mono" font-size="11.5" font-weight="600">Rust (Rayon · k256 · LTO Fat) · secp256k1 Jacobian · Pollard's Kangaroo O(√W)</text>
    <text x="92" y="354" fill="$subtitle" font-family="$font_mono" font-size="11">Firma ECDSA determinista · Serialización binaria Wire-Format · Paralelismo multi-núcleo</text>
  </g>
  <g>
    <rect x="24" y="392" width="40" height="28" rx="8" fill="$amber_soft" stroke="$amber_stroke" stroke-width="1.2"/>
    <text x="44" y="410" text-anchor="middle" fill="$amber" font-family="$font_mono" font-size="11.5" font-weight="800">L1</text>
    <rect x="74" y="374" width="742" height="64" rx="10" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="74" y="374" width="5" height="64" rx="2.5" fill="$amber_stroke"/>
    <text x="92" y="396" fill="$title" font-family="$font_sans" font-size="14" font-weight="700">Ring -1 Hypervisors, Kernel Internals &amp; Reverse Engineering</text>
    <path class="l-flow-up" d="M 744 396 L 752 396 L 752 385 L 764 385 L 764 396 L 776 396 L 776 385 L 788 385 L 788 396 L 796 396" fill="none" stroke="$amber_stroke" stroke-width="1.8" stroke-dasharray="18 8"/>
    <text x="92" y="414" fill="$amber" font-family="$font_mono" font-size="11.5" font-weight="600">C · C++17 · x64 MASM · WDK · AMD-V (SVM · VMCB · 4-Level NPT · VMMCALL · GIF=0)</text>
    <text x="92" y="430" fill="$subtitle" font-family="$font_mono" font-size="11">fTPM 2.0 · PCIe ECAM · SMBIOS · Zero-CRT DX11/HLSL · PE64 RE (IDA · Capstone · Unicorn · Z3 · Frida)</text>
  </g>
</svg>
"""
)

DEEPDIVE_TEMPLATE = Template(
    """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 318" width="840" height="318" role="img" aria-label="Planos animados de sistemas profundos: arquitectura de hipervisor AMD-V Ring -1 e ingeniería inversa, motor criptográfico en Rust y flujos distribuidos Lambda">
  <title>Planos de Sistemas Profundos — Virtualización Ring -1, Rust y Pipelines</title>
  <defs>
    <linearGradient id="dBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="$bg"/>
      <stop offset="100%" stop-color="$bg2"/>
    </linearGradient>
    <linearGradient id="dBarL" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="$amber_stroke"/>
      <stop offset="100%" stop-color="$violet_stroke"/>
    </linearGradient>
    <linearGradient id="dBarR" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="$violet_stroke"/>
      <stop offset="50%" stop-color="$blue_stroke"/>
      <stop offset="100%" stop-color="$emerald_stroke"/>
    </linearGradient>
    <pattern id="dGrid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M 28 0 L 0 0 0 28" fill="none" stroke="$grid" stroke-width="0.65" opacity="$grid_opacity"/>
    </pattern>
    <clipPath id="dClip">
      <rect x="2" y="2" width="836" height="314" rx="14"/>
    </clipPath>
  </defs>
  <style>
    .d-flow { animation: dDash 2.6s linear infinite; }
    .d-flow-rev { animation: dDashRev 2.2s linear infinite; }
    .d-pulse { animation: dPulse 2.2s ease-in-out infinite; }
    @keyframes dDash { from { stroke-dashoffset: 36; } to { stroke-dashoffset: 0; } }
    @keyframes dDashRev { from { stroke-dashoffset: 0; } to { stroke-dashoffset: 36; } }
    @keyframes dPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.32; } }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
  </style>
  <g clip-path="url(#dClip)">
    <rect x="2" y="2" width="836" height="314" rx="14" fill="url(#dBg)"/>
    <rect x="2" y="2" width="836" height="314" rx="14" fill="url(#dGrid)"/>
  </g>
  <rect x="2" y="2" width="836" height="314" rx="14" fill="none" stroke="$border" stroke-width="1.5"/>
  <circle class="d-pulse" cx="30" cy="29" r="4.5" fill="$amber"/>
  <text x="44" y="33" fill="$amber" font-family="$font_mono" font-size="11.5" font-weight="700">DEEP SYSTEMS BLUEPRINTS · SILICON · CRYPTO · DATA</text>
  <text x="24" y="56" fill="$title" font-family="$font_sans" font-size="19" font-weight="800">Virtualización Ring -1, Criptografía Rust &amp; Datos Distribuidos</text>
  <g>
    <rect x="24" y="70" width="386" height="228" rx="11" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="24" y="70" width="386" height="3.5" rx="2" fill="url(#dBarL)"/>
    <text x="40" y="96" fill="$title" font-family="$font_sans" font-size="14.5" font-weight="700">Ring -1 Virtualization &amp; Binary RE</text>
    <rect x="308" y="80" width="88" height="22" rx="11" fill="$amber_soft" stroke="$amber_stroke" stroke-width="0.9"/>
    <text x="352" y="95" text-anchor="middle" fill="$amber" font-family="$font_mono" font-size="10.5" font-weight="700">AMD-V SVM</text>
    <line x1="62" y1="126" x2="62" y2="214" stroke="$rail_track" stroke-width="1.8"/>
    <path class="d-flow" d="M 62 126 L 62 214" fill="none" stroke="$amber_stroke" stroke-width="2.2" stroke-dasharray="7 11"/>
    <line x1="372" y1="126" x2="372" y2="214" stroke="$rail_track" stroke-width="1.8"/>
    <path class="d-flow-rev" d="M 372 126 L 372 214" fill="none" stroke="$violet_stroke" stroke-width="2.2" stroke-dasharray="7 11"/>
    <g font-family="$font_mono" font-size="10.5" font-weight="700">
      <rect x="78" y="112" width="278" height="28" rx="7" fill="$pill" stroke="$cyan_stroke" stroke-width="1"/>
      <text x="90" y="130" fill="$cyan">RING 3 <tspan fill="$subtitle" font-weight="500">C++17 · Zero-CRT DX11 / HLSL</tspan></text>
      <rect x="78" y="148" width="278" height="28" rx="7" fill="$pill" stroke="$violet_stroke" stroke-width="1"/>
      <text x="90" y="166" fill="$violet">RING 0 <tspan fill="$subtitle" font-weight="500">WDK Kernel · VMMCALL · PTEs</tspan></text>
      <rect x="78" y="184" width="278" height="28" rx="7" fill="$pill" stroke="$amber_stroke" stroke-width="1.1"/>
      <text x="90" y="202" fill="$amber">RING -1 <tspan fill="$subtitle" font-weight="500">SVM · VMCB · 4-Level NPT</tspan></text>
    </g>
    <g font-family="$font_mono" font-size="10.5" font-weight="700">
      <rect x="38" y="226" width="172" height="26" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="50" y="243" fill="$amber">GIF=0 <tspan fill="$subtitle" font-weight="500">Host CR3 aislado</tspan></text>
      <rect x="220" y="226" width="174" height="26" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="232" y="243" fill="$violet">fTPM 2.0 <tspan fill="$subtitle" font-weight="500">PCIe · SMBIOS</tspan></text>
      <rect x="38" y="258" width="172" height="26" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="50" y="275" fill="$cyan">x64 MASM <tspan fill="$subtitle" font-weight="500">SEH · PE64</tspan></text>
      <rect x="220" y="258" width="174" height="26" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="232" y="275" fill="$emerald">IDA · Z3 <tspan fill="$subtitle" font-weight="500">Frida · Unicorn</tspan></text>
    </g>
  </g>
  <g>
    <rect x="430" y="70" width="386" height="228" rx="11" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="430" y="70" width="386" height="3.5" rx="2" fill="url(#dBarR)"/>
    <text x="446" y="96" fill="$title" font-family="$font_sans" font-size="14.5" font-weight="700">Rust Crypto &amp; Distributed Pipelines</text>
    <rect x="702" y="80" width="100" height="22" rx="11" fill="$violet_soft" stroke="$violet_stroke" stroke-width="0.9"/>
    <text x="752" y="95" text-anchor="middle" fill="$violet" font-family="$font_mono" font-size="10.5" font-weight="700">HPC · DATA</text>
    <line x1="484" y1="132" x2="762" y2="132" stroke="$rail_track" stroke-width="1.8"/>
    <path class="d-flow" d="M 484 132 L 762 132" fill="none" stroke="$violet_stroke" stroke-width="2.2" stroke-dasharray="8 10"/>
    <g font-family="$font_mono" font-size="10" font-weight="700" text-anchor="middle">
      <rect x="444" y="112" width="80" height="40" rx="7" fill="$pill" stroke="$violet_stroke" stroke-width="1.1"/>
      <text x="484" y="130" fill="$violet">Rust</text>
      <text x="484" y="144" fill="$muted" font-size="9">Rayon LTO</text>
      <rect x="536" y="112" width="80" height="40" rx="7" fill="$pill" stroke="$violet_stroke" stroke-width="1.1"/>
      <text x="576" y="130" fill="$violet">secp256k1</text>
      <text x="576" y="144" fill="$muted" font-size="9">Jacobian</text>
      <rect x="628" y="112" width="80" height="40" rx="7" fill="$pill" stroke="$amber_stroke" stroke-width="1.1"/>
      <text x="668" y="130" fill="$amber">Kangaroo</text>
      <text x="668" y="144" fill="$muted" font-size="9">O(√W)</text>
      <rect x="720" y="112" width="82" height="40" rx="7" fill="$pill" stroke="$emerald_stroke" stroke-width="1.1"/>
      <text x="761" y="130" fill="$emerald">ECDSA</text>
      <text x="761" y="144" fill="$muted" font-size="9">Wire TX</text>
    </g>
    <line x1="484" y1="186" x2="762" y2="186" stroke="$rail_track" stroke-width="1.8"/>
    <path class="d-flow" d="M 484 186 L 762 186" fill="none" stroke="$blue_stroke" stroke-width="2.2" stroke-dasharray="8 10"/>
    <g font-family="$font_mono" font-size="10" font-weight="700" text-anchor="middle">
      <rect x="444" y="166" width="80" height="40" rx="7" fill="$pill" stroke="$blue_stroke" stroke-width="1.1"/>
      <text x="484" y="184" fill="$blue">Kafka</text>
      <text x="484" y="198" fill="$muted" font-size="9">KRaft 4.x</text>
      <rect x="536" y="166" width="80" height="40" rx="7" fill="$pill" stroke="$blue_stroke" stroke-width="1.1"/>
      <text x="576" y="184" fill="$blue">HDFS</text>
      <text x="576" y="198" fill="$muted" font-size="9">MapReduce</text>
      <rect x="628" y="166" width="80" height="40" rx="7" fill="$pill" stroke="$cyan_stroke" stroke-width="1.1"/>
      <text x="668" y="184" fill="$cyan">PySpark</text>
      <text x="668" y="198" fill="$muted" font-size="9">Parquet</text>
      <rect x="720" y="166" width="82" height="40" rx="7" fill="$pill" stroke="$emerald_stroke" stroke-width="1.1"/>
      <text x="761" y="184" fill="$emerald">PG 17</text>
      <text x="761" y="198" fill="$muted" font-size="9">AI / API</text>
    </g>
    <g font-family="$font_mono" font-size="10.5" font-weight="700">
      <rect x="444" y="226" width="172" height="26" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="456" y="243" fill="$violet">249K/s <tspan fill="$subtitle" font-weight="500">Rust 12-Core</tspan></text>
      <rect x="626" y="226" width="176" height="26" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="638" y="243" fill="$blue">Lambda <tspan fill="$subtitle" font-weight="500">Batch+Speed</tspan></text>
      <rect x="444" y="258" width="172" height="26" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="456" y="275" fill="$emerald">MCP <tspan fill="$subtitle" font-weight="500">Multi-Agent</tspan></text>
      <rect x="626" y="258" width="176" height="26" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="638" y="275" fill="$cyan">Docker <tspan fill="$subtitle" font-weight="500">GPU · Cloud</tspan></text>
    </g>
  </g>
</svg>
"""
)

MATRIX_TEMPLATE = Template(
    """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 278" width="840" height="278" role="img" aria-label="Topología Full-Stack, Cloud y Móvil: Clientes Angular React Mobile conectados a APIs Node FastAPI Real-Time y capa Data Cloud AI">
  <title>Topología Full-Stack, Cloud y Móvil</title>
  <defs>
    <linearGradient id="mBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="$bg"/>
      <stop offset="100%" stop-color="$bg2"/>
    </linearGradient>
    <pattern id="mGrid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M 28 0 L 0 0 0 28" fill="none" stroke="$grid" stroke-width="0.65" opacity="$grid_opacity"/>
    </pattern>
    <clipPath id="mClip">
      <rect x="2" y="2" width="836" height="274" rx="14"/>
    </clipPath>
  </defs>
  <style>
    .m-flow { animation: mDash 2.4s linear infinite; }
    .m-flow-rev { animation: mDashRev 2.8s linear infinite; }
    .m-pulse { animation: mPulse 2.3s ease-in-out infinite; }
    @keyframes mDash { from { stroke-dashoffset: 32; } to { stroke-dashoffset: 0; } }
    @keyframes mDashRev { from { stroke-dashoffset: 0; } to { stroke-dashoffset: 32; } }
    @keyframes mPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
  </style>
  <g clip-path="url(#mClip)">
    <rect x="2" y="2" width="836" height="274" rx="14" fill="url(#mBg)"/>
    <rect x="2" y="2" width="836" height="274" rx="14" fill="url(#mGrid)"/>
  </g>
  <rect x="2" y="2" width="836" height="274" rx="14" fill="none" stroke="$border" stroke-width="1.5"/>
  <circle class="m-pulse" cx="30" cy="29" r="4.5" fill="$cyan"/>
  <text x="44" y="33" fill="$cyan" font-family="$font_mono" font-size="11.5" font-weight="700">FULL-STACK · CLOUD · MOBILE TOPOLOGY</text>
  <text x="24" y="56" fill="$title" font-family="$font_sans" font-size="19" font-weight="800">Ingeniería Web Empresarial, Tiempo Real &amp; Móvil Nativo</text>
  <g>
    <line x1="266" y1="142" x2="299" y2="142" stroke="$rail_track" stroke-width="2"/>
    <path class="m-flow" d="M 266 142 L 299 142" fill="none" stroke="$cyan_stroke" stroke-width="2.2" stroke-dasharray="6 10"/>
    <line x1="266" y1="196" x2="299" y2="196" stroke="$rail_track" stroke-width="2"/>
    <path class="m-flow-rev" d="M 266 196 L 299 196" fill="none" stroke="$blue_stroke" stroke-width="2.2" stroke-dasharray="6 10"/>
    <line x1="541" y1="142" x2="574" y2="142" stroke="$rail_track" stroke-width="2"/>
    <path class="m-flow" d="M 541 142 L 574 142" fill="none" stroke="$blue_stroke" stroke-width="2.2" stroke-dasharray="6 10"/>
    <line x1="541" y1="196" x2="574" y2="196" stroke="$rail_track" stroke-width="2"/>
    <path class="m-flow-rev" d="M 541 196 L 574 196" fill="none" stroke="$emerald_stroke" stroke-width="2.2" stroke-dasharray="6 10"/>
  </g>
  <g>
    <rect x="24" y="72" width="242" height="186" rx="11" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="24" y="72" width="242" height="3.5" rx="2" fill="$cyan_stroke"/>
    <text x="40" y="99" fill="$cyan" font-family="$font_mono" font-size="12" font-weight="700">01 · CLIENTS &amp; MOBILE</text>
    <g font-family="$font_mono" font-size="11.5" font-weight="600">
      <rect x="38" y="114" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="50" y="132" fill="$title">Angular · RxJS · PWA</text>
      <rect x="38" y="148" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="50" y="166" fill="$title">React 19 · Next.js · Vite</text>
      <rect x="38" y="182" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="50" y="200" fill="$title">D3 · XYFlow · MapLibre</text>
      <rect x="38" y="216" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="50" y="234" fill="$cyan">Capacitor · Android Kotlin</text>
    </g>
  </g>
  <g>
    <rect x="299" y="72" width="242" height="186" rx="11" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="299" y="72" width="242" height="3.5" rx="2" fill="$blue_stroke"/>
    <text x="315" y="99" fill="$blue" font-family="$font_mono" font-size="12" font-weight="700">02 · APIS &amp; REAL-TIME</text>
    <g font-family="$font_mono" font-size="11.5" font-weight="600">
      <rect x="313" y="114" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="325" y="132" fill="$title">Node · Express · Fastify</text>
      <rect x="313" y="148" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="325" y="166" fill="$title">Socket.IO · OpenAPI · Knex</text>
      <rect x="313" y="182" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="325" y="200" fill="$title">Python · FastAPI · Redis</text>
      <rect x="313" y="216" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="325" y="234" fill="$blue">Stripe · JWT · RBAC · E2E</text>
    </g>
  </g>
  <g>
    <rect x="574" y="72" width="242" height="186" rx="11" fill="$surface" stroke="$inner_border" stroke-width="1.2"/>
    <rect x="574" y="72" width="242" height="3.5" rx="2" fill="$emerald_stroke"/>
    <text x="590" y="99" fill="$emerald" font-family="$font_mono" font-size="12" font-weight="700">03 · DATA, CLOUD &amp; AI</text>
    <g font-family="$font_mono" font-size="11.5" font-weight="600">
      <rect x="588" y="114" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="600" y="132" fill="$title">PostgreSQL · PL/pgSQL</text>
      <rect x="588" y="148" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="600" y="166" fill="$title">Supabase · RLS · Edge Fn</text>
      <rect x="588" y="182" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="600" y="200" fill="$title">AWS S3/SES · Docker GPU</text>
      <rect x="588" y="216" width="214" height="28" rx="6" fill="$surface_alt" stroke="$inner_border" stroke-width="0.9"/>
      <text x="600" y="234" fill="$emerald">LLMs · MCP · Playwright</text>
    </g>
  </g>
</svg>
"""
)

SPECS: list[tuple[str, Template, str]] = [
    ("hero", HERO_TEMPLATE, "0 0 840 260"),
    ("stack-layers", LAYERS_TEMPLATE, "0 0 840 454"),
    ("systems-deepdive", DEEPDIVE_TEMPLATE, "0 0 840 318"),
    ("engineering-matrix", MATRIX_TEMPLATE, "0 0 840 278"),
]


def render_svg(template: Template, theme_name: str) -> str:
    tokens = dict(THEMES[theme_name])
    tokens["font_sans"] = FONT_SANS
    tokens["font_mono"] = FONT_MONO
    return template.substitute(tokens).replace("\r\n", "\n")


def relative_luminance(hex_color: str) -> float:
    hx = hex_color.lstrip("#")
    rgb = [int(hx[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = sorted([relative_luminance(fg), relative_luminance(bg)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def write_all() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for stem, tmpl, _ in SPECS:
        for theme in ("dark", "light"):
            out = ASSETS_DIR / f"{stem}-{theme}.svg"
            content = render_svg(tmpl, theme)
            out.write_bytes(content.encode("utf-8"))
            print(f"WROTE {out.relative_to(ROOT)} ({len(content.encode('utf-8'))} bytes)")


def check_all() -> list[str]:
    errors: list[str] = []

    for theme_name, palette in THEMES.items():
        for fg_key, bg_key in WCAG_PAIRS:
            ratio = contrast_ratio(palette[fg_key], palette[bg_key])
            if ratio < 4.5:
                errors.append(
                    f"WCAG_AA_FAIL: {theme_name} {fg_key}({palette[fg_key]}) vs {bg_key}({palette[bg_key]}) = {ratio:.2f}:1 < 4.5:1"
                )

    for svg_key, label, text, font_size, is_mono, box_w, x_start, max_right in BOUND_CHECKS:
        factor = 0.64 if is_mono else 0.56
        est_w = len(text) * font_size * factor
        if est_w > box_w:
            errors.append(
                f"BOUNDS_FAIL: {svg_key}.{label} est_width={est_w:.1f}px > box_w={box_w:.1f}px ({text!r})"
            )
        if x_start + est_w > max_right:
            errors.append(
                f"COLLISION_FAIL: {svg_key}.{label} x_end={x_start + est_w:.1f}px > max_right={max_right:.1f}px"
            )

    forbidden_svg_patterns = [
        r"<script\b",
        r"<foreignObject\b",
        r"@import\b",
        r"<animate\w*\b",
        r"<filter\b",
        r"<metadata\b",
        r"<!--",
        r"\bon[a-z]+\s*=",
        r"javascript:",
    ]
    expected_files: set[str] = set()
    for stem, tmpl, expected_vb in SPECS:
        for theme in ("dark", "light"):
            fname = f"{stem}-{theme}.svg"
            expected_files.add(fname)
            path = ASSETS_DIR / fname
            expected = render_svg(tmpl, theme).encode("utf-8")
            if not path.exists():
                errors.append(f"MISSING_SVG: {path.relative_to(ROOT)}")
                continue
            actual = path.read_bytes()
            if hashlib.sha256(actual).hexdigest() != hashlib.sha256(expected).hexdigest():
                errors.append(f"DRIFT_FAIL: {path.relative_to(ROOT)} differs from generator output")
            if len(actual) > MAX_SVG_BYTES:
                errors.append(f"SIZE_FAIL: {path.relative_to(ROOT)} is {len(actual)}B > {MAX_SVG_BYTES}B")
            if b"\r\n" in actual:
                errors.append(f"EOL_FAIL: {path.relative_to(ROOT)} contains CRLF")
            text_svg = actual.decode("utf-8")
            try:
                root_el = ET.fromstring(text_svg)
            except ET.ParseError as exc:
                errors.append(f"XML_FAIL: {path.relative_to(ROOT)}: {exc}")
                continue
            if root_el.attrib.get("viewBox") != expected_vb:
                errors.append(f"VIEWBOX_FAIL: {fname} expected {expected_vb!r}, got {root_el.attrib.get('viewBox')!r}")
            if root_el.attrib.get("role") != "img":
                errors.append(f"ROLE_FAIL: {fname} missing role='img'")
            title_el = root_el.find("{http://www.w3.org/2000/svg}title")
            if title_el is None or not (title_el.text or "").strip():
                errors.append(f"TITLE_FAIL: {fname} missing non-empty <title>")
            if "prefers-reduced-motion: reduce" not in text_svg:
                errors.append(f"A11Y_FAIL: {fname} missing prefers-reduced-motion rule")
            for pat in forbidden_svg_patterns:
                if re.search(pat, text_svg, re.IGNORECASE):
                    errors.append(f"CSP_FAIL: {fname} matched forbidden pattern {pat}")
            for url in re.findall(r"https?://[^\s'\"<>]+", text_svg):
                if url != "http://www.w3.org/2000/svg":
                    errors.append(f"EXTERNAL_URL_FAIL: {fname} contains {url}")

    if ASSETS_DIR.exists():
        actual_files = {p.name for p in ASSETS_DIR.iterdir() if p.is_file()}
        extra = actual_files - expected_files
        if extra:
            errors.append(f"STALE_ASSETS: unexpected files in ./assets/: {sorted(extra)}")

    if not README_PATH.exists():
        errors.append("MISSING_README: README.md does not exist")
        return errors

    readme = README_PATH.read_text(encoding="utf-8")
    if "\r\n" in readme:
        errors.append("README_EOL_FAIL: README.md contains CRLF")

    for url in re.findall(r"https?://[^\s\)\"'>`]+", readme):
        cleaned = url.rstrip(".,;")
        if cleaned not in URL_ALLOWLIST:
            errors.append(f"ALLOWLIST_FAIL: README.md contains non-allowlisted URL {cleaned}")

    for bad_pat, label in [
        (r"[A-Za-z]:\\", "local Windows path"),
        (r"/Users/|/home/|/mnt/", "local Unix path"),
        (r"<table\b", "HTML layout table"),
        (r"\balign\s*=", "HTML align attribute"),
        (r"#gh-(dark|light)-mode-only", "deprecated GitHub theme hash"),
        (r"<!--", "HTML comment"),
    ]:
        if re.search(bad_pat, readme, re.IGNORECASE):
            errors.append(f"README_POLICY_FAIL: matched {label} ({bad_pat})")

    existing_assets = {p.name for p in ASSETS_DIR.iterdir() if p.is_file()} if ASSETS_DIR.exists() else set()
    pictures = re.findall(r"<picture>.*?</picture>", readme, re.DOTALL)
    if len(pictures) != len(SPECS):
        errors.append(f"PICTURE_COUNT_FAIL: expected {len(SPECS)} <picture> blocks, found {len(pictures)}")

    for idx, pic in enumerate(pictures, 1):
        dark_src = re.findall(r'<source\s+media="\(prefers-color-scheme:\s*dark\)"\s+srcset="([^"]+)"', pic)
        light_src = re.findall(r'<source\s+media="\(prefers-color-scheme:\s*light\)"\s+srcset="([^"]+)"', pic)
        img_tag = re.findall(r"<img\s+([^>]+)>", pic)
        if len(dark_src) != 1 or len(light_src) != 1 or len(img_tag) != 1:
            errors.append(f"PICTURE_STRUCT_FAIL: block #{idx} malformed")
            continue
        if re.search(r"\bheight\s*=", img_tag[0]):
            errors.append(f"PICTURE_HEIGHT_FAIL: block #{idx} <img> must not hardcode height")
        alt_m = re.search(r'alt="([^"]+)"', img_tag[0])
        src_m = re.search(r'src="([^"]+)"', img_tag[0])
        if not alt_m or len(alt_m.group(1).strip()) < 10:
            errors.append(f"PICTURE_ALT_FAIL: block #{idx} missing descriptive alt (>=10 chars)")
        refs = dark_src + light_src + ([src_m.group(1)] if src_m else [])
        for rel in refs:
            if not re.fullmatch(r"\./assets/[a-z0-9-]+\.svg", rel):
                errors.append(f"ASSET_PATH_FAIL: invalid relative path {rel!r}")
            else:
                fname = rel.split("/")[-1]
                if fname not in existing_assets:
                    errors.append(f"ASSET_CASE_MISSING: {rel} not found (case-sensitive) in ./assets/")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and validate Milov-ai profile SVGs.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="Generate dark/light SVGs into ./assets/")
    group.add_argument("--check", action="store_true", help="Validate SVGs and README.md")
    args = parser.parse_args()

    if args.write:
        write_all()
        return 0

    errs = check_all()
    if errs:
        for e in errs:
            print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    print(
        f"[PASS] All {len(SPECS) * 2} SVGs, WCAG AA pairs ({len(WCAG_PAIRS) * 2}), bounds ({len(BOUND_CHECKS)}), CSP and zero-URL README policy verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
