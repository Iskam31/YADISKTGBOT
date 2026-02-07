"""Token encryption using Fernet symmetric encryption.

Provides secure encryption and decryption of OAuth tokens before storing in database.
"""

from cryptography.fernet import Fernet, InvalidToken
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TokenEncryption:
    """Handles encryption and decryption of sensitive tokens.

    Uses Fernet symmetric encryption (AES 128 in CBC mode with HMAC).
    """

    def __init__(self, encryption_key: str):
        """Initialize encryption with a key.

        Args:
            encryption_key: Base64-encoded Fernet key (use Fernet.generate_key())

        Raises:
            ValueError: If encryption key is invalid
        """
        if not encryption_key:
            raise ValueError("Encryption key cannot be empty")

        try:
            self._fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
            logger.info("Token encryption initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise ValueError(f"Invalid encryption key: {e}")

    def encrypt(self, token: str) -> str:
        """Encrypt a token.

        Args:
            token: Plain text token to encrypt

        Returns:
            Encrypted token as base64 string

        Raises:
            ValueError: If token is empty
        """
        if not token:
            raise ValueError("Token cannot be empty")

        try:
            encrypted_bytes = self._fernet.encrypt(token.encode())
            encrypted_str = encrypted_bytes.decode()
            logger.debug("Token encrypted successfully")
            return encrypted_str
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt(self, encrypted_token: str) -> str:
        """Decrypt a token.

        Args:
            encrypted_token: Encrypted token (base64 string)

        Returns:
            Decrypted plain text token

        Raises:
            ValueError: If token is empty or invalid
        """
        if not encrypted_token:
            raise ValueError("Encrypted token cannot be empty")

        try:
            decrypted_bytes = self._fernet.decrypt(encrypted_token.encode())
            decrypted_str = decrypted_bytes.decode()
            logger.debug("Token decrypted successfully")
            return decrypted_str
        except InvalidToken:
            logger.error("Invalid or corrupted encrypted token")
            raise ValueError("Invalid encrypted token - cannot decrypt")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key.

        Returns:
            Base64-encoded key as string

        Example:
            key = TokenEncryption.generate_key()
            # Save this key to environment variable ENCRYPTION_KEY
        """
        key = Fernet.generate_key()
        return key.decode()


# Global encryption instance
_encryption: Optional[TokenEncryption] = None


def init_encryption(encryption_key: str) -> None:
    """Initialize global encryption instance.

    Args:
        encryption_key: Base64-encoded Fernet key

    Raises:
        ValueError: If key is invalid
    """
    global _encryption
    _encryption = TokenEncryption(encryption_key)
    logger.info("Global encryption instance initialized")


def get_encryption() -> TokenEncryption:
    """Get global encryption instance.

    Returns:
        TokenEncryption instance

    Raises:
        RuntimeError: If encryption not initialized
    """
    if _encryption is None:
        raise RuntimeError("Encryption not initialized. Call init_encryption() first.")
    return _encryption
