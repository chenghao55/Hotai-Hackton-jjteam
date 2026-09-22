"""E adapter for Module A's accepted-photo storage API."""

from abc import ABC, abstractmethod

from module_a import Photo, PhotoNotFoundError, PhotoType, get_photo, get_photo_info, save_photo


class PhotoStorageNotFoundError(LookupError):
    """Raised when an E storage lookup cannot find a Module A photo."""


class PhotoStorageService(ABC):
    """Stores an accepted image and returns its Module A photo ID."""

    @abstractmethod
    def save(self, image: bytes, photo_type: PhotoType, mime_type: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get(self, photo_id: str) -> tuple[bytes, Photo]:
        """Return the stored bytes together with Module A photo metadata."""
        raise NotImplementedError


class ModuleAPhotoStorageService(PhotoStorageService):
    """Delegates storage and ID generation to Module A."""

    def save(self, image: bytes, photo_type: PhotoType, mime_type: str) -> str:
        return save_photo(image, photo_type, mime_type)

    def get(self, photo_id: str) -> tuple[bytes, Photo]:
        try:
            info = get_photo_info(photo_id)
            return get_photo(photo_id), info
        except PhotoNotFoundError as exc:
            raise PhotoStorageNotFoundError("photo was not found") from exc


def get_photo_storage_service() -> PhotoStorageService:
    """FastAPI dependency for the accepted-photo storage adapter."""
    return ModuleAPhotoStorageService()
