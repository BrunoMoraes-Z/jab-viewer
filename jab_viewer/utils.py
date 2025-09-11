import os
from typing import Optional

ENV_DLL_KEY = 'RC_JAVA_ACCESS_BRIDGE_DLL'


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
