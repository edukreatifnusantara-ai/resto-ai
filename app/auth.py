"""Authentication module for Resto AI Web Portals (Dashboard & KDS).

Protected by password 'juara' by JUARA MANAGEMENT ENTERPRISE.
"""

import hmac
import hashlib
import os
import secrets
from typing import Optional
from fastapi import Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

AUTH_COOKIE_NAME = "juara_session"
DEFAULT_WEB_PASSWORD = "juara"


def is_web_auth_enabled() -> bool:
    """Returns True if web UI password protection is enabled."""
    val = os.getenv("RESTO_WEB_AUTH_ENABLED", "false").lower().strip()
    return val in {"true", "1", "yes"}


def get_web_password() -> str:
    return os.getenv("RESTO_WEB_PASSWORD", DEFAULT_WEB_PASSWORD)


def get_secret_key() -> bytes:
    key = os.getenv("RESTO_API_TOKEN") or "juara-secret-salt-ndelik-2026"
    return key.encode("utf-8")


def generate_session_token() -> str:
    """Creates a cryptographically signed session token."""
    payload = "juara_authenticated_user"
    sig = hmac.new(get_secret_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session_token(token: Optional[str]) -> bool:
    """Verifies HMAC signature of the session token."""
    if not token or "." not in token:
        return False
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False
    payload, sig = parts
    expected_sig = hmac.new(get_secret_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return secrets.compare_digest(sig, expected_sig)


def is_authenticated(request: Request) -> bool:
    """Checks whether the request is authenticated via cookie or internal token."""
    # 1. Check API token header (used by internal services, tests, curl)
    api_token = request.headers.get("X-RESTO-API-TOKEN", "")
    expected_token = os.getenv("RESTO_API_TOKEN", "")
    if expected_token and api_token and secrets.compare_digest(api_token, expected_token):
        return True

    # 2. Check browser session cookie
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if verify_session_token(cookie):
        return True

    return False


def render_login_page(next_path: str = "/dashboard", error_msg: Optional[str] = None) -> str:
    """Renders the modern, enterprise login screen."""
    error_banner = ""
    if error_msg:
        error_banner = f"""
        <div class="mb-6 p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-3 animate-bounce">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-rose-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>{error_msg}</span>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sistem Akses Enterprise - Warung Ndelik</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800;900&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <script>
      tailwind.config = {{
        theme: {{
          extend: {{
            fontFamily: {{
              sans: ['"Plus Jakarta Sans"', 'sans-serif'],
              display: ['"Space Grotesk"', 'sans-serif'],
            }}
          }}
        }}
      }}
    </script>
    <style>
        body {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: #07090e;
        }}
        .brand-gradient {{
            background: linear-gradient(135deg, #f59e0b 0%, #ea580c 50%, #dc2626 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .glow-box {{
            box-shadow: 0 0 50px -10px rgba(234, 88, 12, 0.25);
        }}
        .grid-bg {{
            background-image: radial-gradient(rgba(255, 255, 255, 0.07) 1px, transparent 1px);
            background-size: 28px 28px;
        }}
    </style>
</head>
<body class="min-h-screen text-slate-100 flex flex-col justify-between grid-bg relative selection:bg-orange-500 selection:text-white">

    <!-- Ambient Glow Orbs -->
    <div class="fixed top-0 left-1/2 -translate-x-1/2 w-[600px] h-[350px] bg-gradient-to-b from-orange-600/20 via-amber-500/10 to-transparent blur-[120px] pointer-events-none -z-10"></div>
    <div class="fixed bottom-0 right-0 w-[400px] h-[300px] bg-red-600/10 blur-[100px] pointer-events-none -z-10"></div>

    <!-- Header bar -->
    <header class="w-full px-6 py-6 max-w-6xl mx-auto flex items-center justify-between">
        <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-amber-500 via-orange-600 to-red-600 flex items-center justify-center font-black text-white text-base shadow-lg shadow-orange-500/30">
                WN
            </div>
            <div class="text-xs font-semibold tracking-wider text-slate-400 uppercase">
                Warung Ndelik • Live Ops
            </div>
        </div>
        <div class="flex items-center gap-2">
            <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                Sistem Terlindungi
            </span>
        </div>
    </header>

    <!-- Main Container -->
    <main class="w-full max-w-lg mx-auto px-6 py-8 flex flex-col items-center">

        <!-- Top Big Branding: by JUARA MANAGEMENT ENTERPRISE -->
        <div class="text-center mb-8 w-full">
            <div class="inline-block mb-3 px-4 py-1 rounded-full bg-gradient-to-r from-orange-500/10 via-amber-500/10 to-orange-500/10 border border-orange-500/30 text-[11px] font-extrabold tracking-widest text-amber-400 uppercase">
                ENTERPRISE OPERATIONAL PORTAL
            </div>
            <h1 class="font-display text-2xl sm:text-3xl md:text-4xl font-extrabold tracking-tight text-white mb-2 leading-tight">
                by <span class="bg-gradient-to-r from-amber-400 via-orange-500 to-red-500 bg-clip-text text-transparent font-black">JUARA MANAGEMENT ENTERPRISE</span>
            </h1>
            <p class="text-slate-400 text-sm font-medium">
                Pusat Kendali Keuangan, Laporan Eksekutif & Layar Dapur (KDS)
            </p>
        </div>

        <!-- Glassmorphism Card -->
        <div class="w-full bg-slate-900/80 backdrop-blur-xl border border-slate-800 rounded-3xl p-8 sm:p-10 glow-box relative">
            {error_banner}

            <form action="/login" method="POST" class="space-y-6">
                <input type="hidden" name="next" value="{next_path}">

                <div>
                    <label for="password" class="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-2">
                        Password Akses Sistem
                    </label>
                    <div class="relative">
                        <div class="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-500">
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                            </svg>
                        </div>
                        <input
                            type="password"
                            id="password"
                            name="password"
                            required
                            autofocus
                            placeholder="Ketik password akses..."
                            class="w-full pl-12 pr-12 py-3.5 bg-slate-950/70 border border-slate-700/80 rounded-2xl text-white placeholder-slate-500 text-base focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition shadow-inner font-medium"
                        >
                        <button
                            type="button"
                            onclick="togglePassword()"
                            class="absolute inset-y-0 right-0 pr-4 flex items-center text-slate-500 hover:text-slate-300 transition"
                            tabindex="-1"
                        >
                            <svg id="eye-icon" xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                        </button>
                    </div>
                    <p class="text-[12px] text-slate-500 mt-2 flex items-center gap-1.5">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Masukkan password resmi untuk membuka portal
                    </p>
                </div>

                <button
                    type="submit"
                    class="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-orange-500 via-amber-600 to-red-600 hover:from-orange-600 hover:via-amber-700 hover:to-red-700 text-white font-extrabold text-base tracking-wide shadow-lg shadow-orange-600/30 hover:shadow-orange-600/50 hover:scale-[1.01] active:scale-[0.99] transition duration-200 flex items-center justify-center gap-2 cursor-pointer"
                >
                    <span>Buka Akses Sistem</span>
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                </button>
            </form>

            <div class="mt-8 pt-6 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
                <span>Warung Ndelik Modern ERP</span>
                <span class="text-amber-500 font-bold">Akses 24/7 Terpusat</span>
            </div>
        </div>

        <!-- Quick Links Indicator -->
        <div class="mt-6 flex flex-wrap items-center justify-center gap-4 text-xs text-slate-500">
            <span class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full bg-orange-500"></span> Dashboard Keuangan
            </span>
            <span class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full bg-amber-500"></span> Layar Dapur KDS
            </span>
            <span class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full bg-emerald-500"></span> POS & Integrasi WA
            </span>
        </div>
    </main>

    <!-- Footer -->
    <footer class="w-full py-6 text-center text-xs text-slate-600 border-t border-slate-900">
        <p class="font-medium">
            &copy; 2026 <strong class="text-slate-400">JUARA MANAGEMENT ENTERPRISE</strong>. Hak Cipta Dilindungi.
        </p>
    </footer>

    <script>
        function togglePassword() {{
            const input = document.getElementById('password');
            if (input.type === 'password') {{
                input.type = 'text';
            }} else {{
                input.type = 'password';
            }}
        }}
    </script>
</body>
</html>
"""
