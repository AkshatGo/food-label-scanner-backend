from gridfs import GridFS

from .mongodb import db


fs = GridFS(db)


def save_image(image_bytes: bytes, filename: str, content_type: str):
    """
    Store uploaded image in MongoDB GridFS.
    """
    file_id = fs.put(
        image_bytes,
        filename=filename,
        metadata={"content_type": content_type},
    )

    return file_id


def save_pdf(pdf_bytes: bytes, filename: str):
    return fs.put(pdf_bytes, filename=filename, metadata={"content_type": "application/pdf"})


def get_image(file_id):
    """
    Retrieve image from GridFS.
    """
    return fs.get(file_id)


def get_file(file_id):
    return fs.get(file_id)


def delete_file(file_id):
    """Remove a file from GridFS after a failed scan insert."""
    fs.delete(file_id)