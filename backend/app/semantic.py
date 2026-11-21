"""Search a fixed evidence library with multilingual E5 embeddings on the backend."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray
    from onnxruntime import InferenceSession
    from tokenizers import Tokenizer


MODEL_ID = "Xenova/multilingual-e5-small"
MODEL_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
MODEL_URL = f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}"
MODEL_FILES = (
    ("tokenizer.json", 17_082_730, "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"),
    ("onnx/model_int8.onnx", 118_054_593, "4d24e2bc01a447951524466ef533e52944bf48509e6552810bcee1a2711cb02c"),
)
RESULT_LIMIT = 3
_LOAD_LOCK = Lock()
_RETRY_SECONDS = 60


class ModelUnavailable(RuntimeError):
    """The requested local model could not be prepared or run."""


@dataclass(frozen=True, slots=True)
class SemanticResult:
    title: str
    description: str
    url: str


@dataclass(frozen=True, slots=True)
class _SemanticIndex:
    session: InferenceSession
    tokenizer: Tokenizer
    passages: NDArray[np.float32]


_index: _SemanticIndex | None = None
_retry_after = 0.0


_EVIDENCE = (
    SemanticResult(
        "Δήμος Αθηναίων · Θερμικός χάρτης και κόκκινα κελιά",
        "Τα κόκκινα κελιά δείχνουν τις θερμότερες επιφάνειες της Αθήνας στον χάρτη. "
        "Το χρώμα βασίζεται στη μέση ημερήσια θερμοκρασία επιφάνειας Ιουνίου–Αυγούστου 2016–2020.",
        "https://opendata.cityofathens.gr/dataset/gis-athens-057aff6a-f337-11ee-b64b-0242ac120004",
    ),
    SemanticResult(
        "Athens Smart Neighbourhood · Μετρήσεις θερμοκρασίας αέρα",
        "Οι σταθμοί παρακολούθησης καταγράφουν θερμοκρασία αέρα με χρόνο μέτρησης ανά συσκευή. "
        "Οι ενδείξεις του σταθμού και ο ιστορικός χάρτης επιφάνειας μετρούν διαφορετικά μεγέθη.",
        "https://data.gov.gr/data-service/cityofathens-ds-415dd022213b",
    ),
    SemanticResult(
        "Copernicus · Ποσοστό δενδροκάλυψης",
        "Το πλέγμα του 2018 αποτυπώνει το ποσοστό της επιφάνειας που καλύπτουν οι κόμες των δέντρων. "
        "Χρησιμεύει για τον εντοπισμό θερμών θέσεων με περιορισμένη κάλυψη.",
        "https://doi.org/10.2909/486f77da-d605-423e-93a9-680760ab6791",
    ),
    SemanticResult(
        "AthensTrees · Καταγραφές νέων φυτεύσεων",
        "Ο δημοτικός χάρτης δείχνει καταγεγραμμένες φυτεύσεις. Η σημερινή επιβίωση των δέντρων, "
        "η σκίαση και ο ελεύθερος χώρος για νέες ρίζες επιβεβαιώνονται με αυτοψία.",
        "https://athenstrees.cityofathens.gr/",
    ),
    SemanticResult(
        "JRC–Eurostat · Πληθυσμιακή πυκνότητα",
        "Το πλέγμα 100 μέτρων εκτιμά την κατανομή των μόνιμων κατοίκων της απογραφής του 2021. "
        "Ο δείκτης βοηθά στην προτεραιοποίηση πυκνοκατοικημένων θέσεων.",
        "https://data.jrc.ec.europa.eu/dataset/98336641-fd1c-4992-8c7b-c470dd5eb81e",
    ),
    SemanticResult(
        "Μελέτη στο Μαρούσι · Ψύξη κάτω από ώριμα δέντρα",
        "Στο Μαρούσι μετρήθηκαν διαφορές 11,6–17,8 °C ανάμεσα σε σκιασμένες και ηλιόλουστες "
        "επιφάνειες, ανάλογα με το υλικό. Η εφαρμογή του εύρους απαιτεί συγκρίσιμη καλοκαιρινή σκίαση.",
        "https://doi.org/10.3390/land11112042",
    ),
    SemanticResult(
        "Μελέτη στην Κόρδοβα · Υφασμάτινα σκίαστρα",
        "Η θερμογραφική μελέτη βρήκε μέγιστες μειώσεις θερμοκρασίας 9,2 και 13,2 °C σε πλάκες "
        "γρανίτη για δύο τύπους σκιάστρου, κάτω από συγκεκριμένη καλοκαιρινή έκθεση.",
        "https://doi.org/10.1016/j.scs.2020.102458",
    ),
    SemanticResult(
        "Μελέτη στην Αθήνα · Φυτεμένο δώμα",
        "Σε μελέτη εντατικού φυτεμένου δώματος γραφείου η εξωτερική επιφάνεια ήταν έως 15 °C "
        "δροσερότερη από συμβατικό δώμα. Η εκτίμηση για σχολείο απαιτεί στοιχεία μόνωσης, "
        "υποστρώματος και άρδευσης.",
        "https://www.sciencedirect.com/science/article/pii/S0378778815003540",
    ),
    SemanticResult(
        "Ευρωπαϊκή Επιτροπή · Χρόνος απόσβεσης δημοτικής επένδυσης",
        "Ο χρόνος απόσβεσης δείχνει σε πόσα χρόνια ο Δήμος μπορεί να ανακτήσει τα χρήματα της παρέμβασης. "
        "Η οικονομική αξιολόγηση λαμβάνει υπόψη αρχικό κόστος, συντήρηση, επιβεβαιωμένη επιχορήγηση, "
        "τεκμηριωμένες εξοικονομήσεις και τον ορίζοντα υπολογισμού της καθαρής παρούσας αξίας.",
        "https://ec.europa.eu/regional_policy/sources/guides/vademecum_2127/vademecum_2127_en.pdf",
    ),
)


def _terms(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFD", text.casefold())
    no_accents = "".join(character for character in normalized if not unicodedata.combining(character))
    return set(re.findall(r"[^\W_\d]{4,}", no_accents)) - {"ειναι", "εχουν", "χρειαζεται"}


def keyword_search(query: str) -> list[SemanticResult]:
    """Find the same source records using accent-insensitive keyword matches."""
    words = _terms(query)
    matches = []
    for record in _EVIDENCE:
        title_words = _terms(record.title)
        evidence_words = _terms(record.description)
        score = 3 * len(words & title_words) + len(words & evidence_words)
        # Shared stems let searches match common Greek inflections such as δέντρα/δέντρων.
        for word in words - title_words - evidence_words:
            if any(word[:6] == term[:6] for term in title_words):
                score += 2
            elif any(word[:5] == term[:5] for term in title_words | evidence_words):
                score += 1
        if score:
            matches.append((score, record))
    matches.sort(key=lambda match: match[0], reverse=True)
    return [record for _, record in matches[:RESULT_LIMIT]]


def _cache_path() -> Path:
    override = os.getenv("ATHENSSHADE_MODEL_CACHE")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "raw" / "semantic-model" / MODEL_REVISION


def _model_file(cache: Path, remote_path: str, expected_size: int, expected_hash: str) -> Path:
    target = cache / Path(remote_path).name
    if target.is_file() and target.stat().st_size == expected_size:
        with target.open("rb") as existing:
            if hashlib.file_digest(existing, "sha256").hexdigest() == expected_hash:
                return target

    temp_path = None
    received = 0
    digest = hashlib.sha256()
    try:
        with NamedTemporaryFile(dir=cache, suffix=".part", delete=False) as staged:
            temp_path = Path(staged.name)
            with httpx.stream("GET", f"{MODEL_URL}/{remote_path}", follow_redirects=True, timeout=20) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    received += len(chunk)
                    if received > expected_size:
                        raise ModelUnavailable("Unexpected evidence model file size.")
                    digest.update(chunk)
                    staged.write(chunk)
        if received != expected_size or digest.hexdigest() != expected_hash:
            raise ModelUnavailable("The evidence model file failed integrity verification.")
        temp_path.replace(target)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return target


def _encode(
    session: InferenceSession,
    tokenizer: Tokenizer,
    texts: list[str],
) -> NDArray[np.float32]:
    import numpy as np

    batch = tokenizer.encode_batch(texts)
    attention = np.array([item.attention_mask for item in batch], dtype=np.int64)
    values = {
        "attention_mask": attention,
        "input_ids": np.array([item.ids for item in batch], dtype=np.int64),
        "token_type_ids": np.array([item.type_ids for item in batch], dtype=np.int64),
    }
    hidden = session.run(["last_hidden_state"], {item.name: values[item.name] for item in session.get_inputs()})[0]
    attended = attention[..., None].astype(hidden.dtype)
    pooled = (hidden * attended).sum(axis=1) / attended.sum(axis=1)
    return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)


def _build_index() -> _SemanticIndex:
    try:
        from onnxruntime import InferenceSession, SessionOptions
        from tokenizers import Tokenizer

        cache = _cache_path()
        cache.mkdir(parents=True, exist_ok=True)
        tokenizer_path, model_path = [_model_file(cache, *asset) for asset in MODEL_FILES]
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(max_length=512)
        tokenizer.enable_padding(pad_id=1, pad_token="<pad>")

        options = SessionOptions()
        options.intra_op_num_threads = 2
        session = InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
        passages = [f"passage: {record.title}. {record.description}" for record in _EVIDENCE]
        return _SemanticIndex(session, tokenizer, _encode(session, tokenizer, passages))
    except ModelUnavailable:
        raise
    except Exception as exc:
        raise ModelUnavailable("The local evidence model could not be loaded.") from exc


def _load_index() -> _SemanticIndex:
    global _index, _retry_after
    if _index is not None:
        return _index
    if not _LOAD_LOCK.acquire(blocking=False):
        raise ModelUnavailable("The local evidence model is being prepared.")
    try:
        if _index is not None:
            return _index
        if monotonic() < _retry_after:
            raise ModelUnavailable("The local evidence model will retry after a short delay.")
        try:
            _index = _build_index()
        except ModelUnavailable:
            _retry_after = monotonic() + _RETRY_SECONDS
            raise
        return _index
    finally:
        _LOAD_LOCK.release()


def semantic_search(query: str) -> list[SemanticResult]:
    """Rank verified passages locally. Only the model files are downloaded."""
    query = query.strip()
    if not query:
        return []
    try:
        index = _load_index()
        embedding = _encode(index.session, index.tokenizer, [f"query: {query}"])[0]
        scores = index.passages @ embedding
    except ModelUnavailable:
        raise
    except Exception as exc:
        raise ModelUnavailable("The local evidence model could not encode the question.") from exc
    ranked = sorted(range(len(_EVIDENCE)), key=scores.__getitem__, reverse=True)
    return [_EVIDENCE[position] for position in ranked[:RESULT_LIMIT]]


if __name__ == "__main__":
    semantic_search("Τι μετρά ο θερμικός χάρτης της Αθήνας;")
    print(f"{MODEL_ID} ready in {_cache_path()}")
