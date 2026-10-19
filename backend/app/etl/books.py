

"""The 66 books of the Bible, in canonical order, with their chapter counts."""

from typing import NamedTuple


class BookInfo(NamedTuple):
    """Facts about one book that never change."""

    code: str  # Short code, e.g. "GEN"
    name: str  # Display name, e.g. "Genesis"
    testament: str  # "OT" (Old Testament) or "NT" (New Testament)
    chapters: int  # How many chapters the book has


# Position in this list = canonical order (Genesis is 1, Revelation is 66)
BOOKS = [
    BookInfo("GEN", "Genesis", "OT", 50),
    BookInfo("EXO", "Exodus", "OT", 40),
    BookInfo("LEV", "Leviticus", "OT", 27),
    BookInfo("NUM", "Numbers", "OT", 36),
    BookInfo("DEU", "Deuteronomy", "OT", 34),
    BookInfo("JOS", "Joshua", "OT", 24),
    BookInfo("JDG", "Judges", "OT", 21),
    BookInfo("RUT", "Ruth", "OT", 4),
    BookInfo("1SA", "1 Samuel", "OT", 31),
    BookInfo("2SA", "2 Samuel", "OT", 24),
    BookInfo("1KI", "1 Kings", "OT", 22),
    BookInfo("2KI", "2 Kings", "OT", 25),
    BookInfo("1CH", "1 Chronicles", "OT", 29),
    BookInfo("2CH", "2 Chronicles", "OT", 36),
    BookInfo("EZR", "Ezra", "OT", 10),
    BookInfo("NEH", "Nehemiah", "OT", 13),
    BookInfo("EST", "Esther", "OT", 10),
    BookInfo("JOB", "Job", "OT", 42),
    BookInfo("PSA", "Psalms", "OT", 150),
    BookInfo("PRO", "Proverbs", "OT", 31),
    BookInfo("ECC", "Ecclesiastes", "OT", 12),
    BookInfo("SNG", "Song of Solomon", "OT", 8),
    BookInfo("ISA", "Isaiah", "OT", 66),
    BookInfo("JER", "Jeremiah", "OT", 52),
    BookInfo("LAM", "Lamentations", "OT", 5),
    BookInfo("EZK", "Ezekiel", "OT", 48),
    BookInfo("DAN", "Daniel", "OT", 12),
    BookInfo("HOS", "Hosea", "OT", 14),
    BookInfo("JOL", "Joel", "OT", 3),
    BookInfo("AMO", "Amos", "OT", 9),
    BookInfo("OBA", "Obadiah", "OT", 1),
    BookInfo("JON", "Jonah", "OT", 4),
    BookInfo("MIC", "Micah", "OT", 7),
    BookInfo("NAM", "Nahum", "OT", 3),
    BookInfo("HAB", "Habakkuk", "OT", 3),
    BookInfo("ZEP", "Zephaniah", "OT", 3),
    BookInfo("HAG", "Haggai", "OT", 2),
    BookInfo("ZEC", "Zechariah", "OT", 14),
    BookInfo("MAL", "Malachi", "OT", 4),
    BookInfo("MAT", "Matthew", "NT", 28),
    BookInfo("MRK", "Mark", "NT", 16),
    BookInfo("LUK", "Luke", "NT", 24),
    BookInfo("JHN", "John", "NT", 21),
    BookInfo("ACT", "Acts", "NT", 28),
    BookInfo("ROM", "Romans", "NT", 16),
    BookInfo("1CO", "1 Corinthians", "NT", 16),
    BookInfo("2CO", "2 Corinthians", "NT", 13),
    BookInfo("GAL", "Galatians", "NT", 6),
    BookInfo("EPH", "Ephesians", "NT", 6),
    BookInfo("PHP", "Philippians", "NT", 4),
    BookInfo("COL", "Colossians", "NT", 4),
    BookInfo("1TH", "1 Thessalonians", "NT", 5),
    BookInfo("2TH", "2 Thessalonians", "NT", 3),
    BookInfo("1TI", "1 Timothy", "NT", 6),
    BookInfo("2TI", "2 Timothy", "NT", 4),
    BookInfo("TIT", "Titus", "NT", 3),
    BookInfo("PHM", "Philemon", "NT", 1),
    BookInfo("HEB", "Hebrews", "NT", 13),
    BookInfo("JAS", "James", "NT", 5),
    BookInfo("1PE", "1 Peter", "NT", 5),
    BookInfo("2PE", "2 Peter", "NT", 3),
    BookInfo("1JN", "1 John", "NT", 5),
    BookInfo("2JN", "2 John", "NT", 1),
    BookInfo("3JN", "3 John", "NT", 1),
    BookInfo("JUD", "Jude", "NT", 1),
    BookInfo("REV", "Revelation", "NT", 22),
]
