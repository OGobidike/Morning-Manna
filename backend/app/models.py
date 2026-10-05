

### Oh boi was this complicated the first timee
"""Database tables for Morning Manna, written as SQLAlchemy models."""

# Tools from SQLAlchemy for describing columns and rules
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint

# Tools for writing tables as Python classes (the SQLAlchemy 2.0 style)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """The parent of every table. Keeps a record of them."""


class Translation(Base):
    """One Bible translation, such as the World English Bible."""

    __tablename__ = "translations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short code, e.g. "WEB" or "KJV". No two translations may share one.
    code: Mapped[str] = mapped_column(String(10), unique=True)
    # Full name, e.g. "World English Bible"
    name: Mapped[str] = mapped_column(String(100))
    # Licence, e.g. "Public domain"
    license: Mapped[str] = mapped_column(String(100))


class Book(Base):
    """One book of the Bible, such as Genesis Exodus or John."""

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short code, e.g. "GEN" for Genesis
    code: Mapped[str] = mapped_column(String(10), unique=True)
    # Full name, e.g. "Genesis"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # "OT" (Old Testament) or "NT" (New Testament)
    testament: Mapped[str] = mapped_column(String(10))
    # Position in the Bible: 1 = Genesis ... 66 = Revelation. Each position is used once.
    canonical_order: Mapped[int] = mapped_column(unique=True)


class Verse(Base):
    """One verse in one translation, such as John 3:16 in the KJV."""

    __tablename__ = "verses"
    # Unique constraint: no two verses may have the same translation, book, chapter, and verse.
    __table_args__ = (UniqueConstraint("translation_id", "book_id", "chapter", "verse"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Which translation this wording comes from (points to translations.id)
    translation_id: Mapped[int] = mapped_column(ForeignKey("translations.id"))
    # Which book this verse is in (points to books.id)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    # Position within the book, e.g. chapter 3, verse 16
    chapter: Mapped[int]
    verse: Mapped[int]
    # The words of the verse. Text has no length limit.
    text: Mapped[str] = mapped_column(Text)
