"""E adapter for Module A's accepted-photo storage API."""

from abc import ABC, abstractmethod

from module_a import PhotoType, save_photo


class PhotoStorageService(ABC):
    """Stores an accepted image and returns its Module A photo ID."""

    @abstractmethod
    def save(self, image: bytes, photo_type: PhotoType, mime_type: str) -> str:
        raise NotImplementedError


class ModuleAPhotoStorageService(PhotoStorageService):
    """Delegates storage and ID generation to Module A."""

    def save(self, image: bytes, photo_type: PhotoType, mime_type: str) -> str:
        return save_photo(image, photo_type, mime_type)


def get_photo_storage_service() -> PhotoStorageService:
    """FastAPI dependency for the accepted-photo storage adapter."""
    return ModuleAPhotoStorageService()
