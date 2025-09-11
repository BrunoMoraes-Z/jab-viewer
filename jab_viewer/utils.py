import os
from typing import Optional

from dotenv import load_dotenv

ENV_DLL_KEY = 'RC_JAVA_ACCESS_BRIDGE_DLL'


def load_env(env_path: Optional[str] = None) -> None:
    if env_path and os.path.isfile(env_path):
        load_dotenv(env_path, override=False)
    else:
        # Try to load .env at project root and package root
        for candidate in [
            os.path.join(os.getcwd(), '.env'),
            os.path.join(os.path.dirname(__file__), '.env'),
        ]:
            if os.path.isfile(candidate):
                load_dotenv(candidate, override=False)


def ensure_wab_env(dll_path: Optional[str] = None) -> Optional[str]:
    """Ensure the WindowsAccessBridge DLL path is available in env.

    Returns the DLL path in use, or None if not set.
    """
    if dll_path:
        os.environ[ENV_DLL_KEY] = dll_path
        return dll_path

    current = os.environ.get(ENV_DLL_KEY)
    if current and os.path.isfile(os.path.normpath(current)):
        return current

    # Try common default locations
    candidates = [
        r'C:\\Program Files\\Java\\jre\\bin\\WindowsAccessBridge-64.dll',
        r'C:\\Program Files\\Java\\jdk\\bin\\WindowsAccessBridge-64.dll',
        r'C:\\Program Files\\Java\\jdk-17\\bin\\WindowsAccessBridge-64.dll',
        r'C:\\Program Files\\Java\\jdk-21\\bin\\WindowsAccessBridge-64.dll',
    ]
    for c in candidates:
        if os.path.isfile(c):
            os.environ[ENV_DLL_KEY] = c
            return c

    return None
