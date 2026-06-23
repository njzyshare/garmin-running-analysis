#!/usr/bin/env python3
"""
Garmin Connect authentication helper.
Handles login and stores session tokens.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
import argparse

try:
    from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError
except ImportError:
    print("❌ garminconnect library not installed", file=sys.stderr)
    print("Install with: pip3 install garminconnect", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
#  Monkey-patch: 修复 garminconnect 库对中国区 (garmin.cn) 的支持
#
#  问题根源: garminconnect 的策略链中, 策略3 (widget+cffi) 会尝试用
#  diauth.garmin.com 交换 DI token → 失败 → 回落 JWT_WEB 也失败 →
#  抛出 GarminConnectAuthenticationError("JWT_WEB cookie not set")。
#  这个异常被策略链误判为"凭证错误", 导致策略4/5 (portal 流程) 根本
#  没有机会执行——而 portal 流程用的是 connect.garmin.cn/app, 对中国区
#  是正确可用的。
#
#  修复方案: 在 _establish_session 中, 当 JWT_WEB cookie 未设置时,
#  抛出 GarminConnectConnectionError (可继续) 而非
#  GarminConnectAuthenticationError (终止链)。
# ---------------------------------------------------------------------------

def _patch_garmin_client():
    """Apply CN-aware patches to garminconnect's client module."""
    import garminconnect.client as garmin_client_mod

    # --- Patch 1: JWT_WEB fallback 不终止策略链 ---
    orig_establish = garmin_client_mod.Client._establish_session

    def patched_establish(self, ticket, sess=None, service_url=None):
        try:
            return orig_establish(self, ticket, sess, service_url)
        except GarminConnectAuthenticationError as e:
            err_str = str(e)
            # "JWT_WEB cookie not set" 不是凭证错误, 不应终止链
            if "JWT_WEB" in err_str:
                raise GarminConnectConnectionError(
                    f"JWT_WEB fallback failed (non-fatal): {e}"
                ) from e
            raise

    garmin_client_mod.Client._establish_session = patched_establish

    # --- Patch 2: CN DI token endpoint ---
    # 当 domain 是 garmin.cn 时, DI 交换应该用 garmin.cn 的 endpoint
    orig_exchange = garmin_client_mod.Client._exchange_service_ticket

    def patched_exchange(self, ticket, service_url=None):
        if self.domain == "garmin.cn":
            # 对于中国区, 先尝试 CN 的 DI endpoint
            import garminconnect.client as mod
            cn_di_url = "https://diauth.garmin.cn/di-oauth2-service/oauth/token"
            svc_url = service_url or mod.IOS_SERVICE_URL

            for client_id in garmin_client_mod.DI_CLIENT_IDS:
                try:
                    r = self._http_post(
                        cn_di_url,
                        headers=garmin_client_mod._native_headers({
                            "Authorization": garmin_client_mod._build_basic_auth(client_id),
                            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Cache-Control": "no-cache",
                        }),
                        data={
                            "client_id": client_id,
                            "service_ticket": ticket,
                            "grant_type": garmin_client_mod.DI_GRANT_TYPE,
                            "service_url": svc_url,
                        },
                        timeout=30,
                    )
                    if r.status_code == 429:
                        continue
                    if r.ok:
                        import base64
                        data = r.json()
                        self.di_token = data["access_token"]
                        self.di_refresh_token = data.get("refresh_token")
                        self.di_client_id = (
                            self._extract_client_id_from_jwt(self.di_token) or client_id
                        )
                        return  # DI token success!
                except Exception:
                    continue

        # 兜底: 用原始方法 (国际 endpoint)
        return orig_exchange(self, ticket, service_url)

    garmin_client_mod.Client._exchange_service_ticket = patched_exchange

    # --- Patch 3: CN service URLs for JWT_WEB fallback ---
    # 当 domain 是 garmin.cn 时, JWT_WEB 回退应该用 garmin.cn 的地址
    # (这已经通过 service_url 参数传递了正确的 portal_service_url,
    #  但 mobile 策略的 service_url 是硬编码的, 需要额外处理)
    return True


# 应用 monkey-patch
_patch_garmin_client()


TOKEN_DIR = Path.home() / ".garmin-health-analysis" / "tokens"
CONFIG_FILE = Path.home() / ".garmin-health-analysis" / "config.json"


def load_config():
    """Load credentials from config file."""
    if not CONFIG_FILE.exists():
        return None
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Failed to load config: {e}", file=sys.stderr)
        return None


def login(email, password, region="cn"):
    """Perform login and save tokens using garminconnect's tokenstore.
    
    Args:
        email: Garmin account email
        password: Garmin account password
        region: "cn" for 中国区 (connect.garmin.cn), "intl" for 国际区 (connect.garmin.com)
    """
    is_cn = (region == "cn")
    region_label = "中国区" if is_cn else "国际区"
    try:
        print(f"🔐 Logging in ({region_label})...", file=sys.stderr)
        
        # Create token directory
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        tokenstore = str(TOKEN_DIR)
        
        # Create client and login (don't pass tokenstore on first login)
        client = Garmin(email, password, is_cn=is_cn)
        result = client.login()  # Initial login without tokenstore
        
        # Save tokens using the internal client (newer garminconnect uses client.client, not garth)
        client.client.dump(tokenstore)
        print(f"✅ Tokens saved to {tokenstore}", file=sys.stderr)
        
        # Test the connection (no PII logged)
        try:
            prof = client.client.connectapi("/userprofile-service/socialProfile")
        except Exception:
            try:
                client.get_user_summary(datetime.now().strftime("%Y-%m-%d"))
            except Exception:
                pass
        
        print("✅ Login successful!", file=sys.stderr)
        
        # Make tokenstore directory secure
        TOKEN_DIR.chmod(0o700)
        
        return True
        
    except GarminConnectAuthenticationError as e:
        print(f"❌ Authentication failed: {e}", file=sys.stderr)
        print("Check your email/password and try again.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Login error: {e}", file=sys.stderr)
        return False


def get_client(region=None):
    """Get authenticated Garmin client, using saved tokens if available.
    
    Args:
        region: "cn" for 中国区, "intl" for 国际区. If None, read from config.json.
    """
    tokenstore = str(TOKEN_DIR)
    
    if not TOKEN_DIR.exists():
        return None
    
    # Determine region
    if region is None:
        config = load_config()
        region = config.get("region", "cn") if config else "cn"
    is_cn = (region == "cn")
    
    try:
        # Try to use saved tokens
        client = Garmin(is_cn=is_cn)
        client.login(tokenstore=tokenstore)
        
        # Test if tokens still work
        client.get_user_summary(datetime.now().strftime("%Y-%m-%d"))
        return client
        
    except Exception as e:
        print(f"⚠️  Saved tokens expired or invalid: {e}", file=sys.stderr)
        return None


def check_status():
    """Check if we have valid authentication."""
    tokenstore = str(TOKEN_DIR)
    
    if not TOKEN_DIR.exists():
        print("❌ Not authenticated", file=sys.stderr)
        print("Run: python3 scripts/garmin_auth.py login", file=sys.stderr)
        return False
    
    print(f"✅ Token store found at {tokenstore}", file=sys.stderr)
    
    # Test if they work
    client = get_client()
    if client:
        try:
            client.get_user_summary(datetime.now().strftime("%Y-%m-%d"))
            print("✅ Authentication valid!", file=sys.stderr)
            return True
        except Exception as e:
            print(f"⚠️  Tokens may be expired: {e}", file=sys.stderr)
            return False
    
    print("❌ Authentication invalid. Please login again.", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description="Garmin Connect authentication")
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # Login command
    login_parser = subparsers.add_parser("login", help="Login to Garmin Connect")
    login_parser.add_argument("--email", help="Garmin account email (or set via env/config)")
    login_parser.add_argument("--password", help="Garmin account password (or set via env/config)")
    
    # Status command
    subparsers.add_parser("status", help="Check authentication status")
    
    args = parser.parse_args()
    
    if args.command == "login":
        email = args.email
        password = args.password
        region = "cn"  # default
        
        # Priority: CLI args > config.json > environment variables
        config = load_config()
        if config:
            email = email or config.get("email")
            password = password or config.get("password")
            region = config.get("region", "cn")
        
        if not email or not password:
            email = email or os.getenv("GARMIN_EMAIL")
            password = password or os.getenv("GARMIN_PASSWORD")
        
        if not email or not password:
            print("❌ Email and password required", file=sys.stderr)
            print("Set via:", file=sys.stderr)
            print("  1. CLI: --email and --password", file=sys.stderr)
            print("  2. Config: create ~/.garmin-health-analysis/config.json", file=sys.stderr)
            print("     (copy from skill's config.example.json as template)", file=sys.stderr)
            print("  3. Env vars: GARMIN_EMAIL and GARMIN_PASSWORD", file=sys.stderr)
            sys.exit(1)
        
        success = login(email, password, region=region)
        sys.exit(0 if success else 1)
    
    elif args.command == "status":
        success = check_status()
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
